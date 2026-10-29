from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.codes import PermissionCode
from core.permissions.scopes import PermissionScope
from core.map_domain import MapOperationError
from dependencies.authorization import require_permission
from dependencies.company import CurrentCompanyContext
from dependencies.database import get_session
from dependencies.map_filters import map_filters
from schemas.map_workspace import MapFilter
from schemas.map import (
    MapAddressObjectBoundsResponse,
    MapBuildingFeatureCollection,
    MapTileSessionResponse,
)
from schemas.map_markers import MapMarkerCreate, MapMarkerResponse, MapMarkerUpdate
from schemas.map_connections import MapConnectionCreate, MapConnectionUpdate, MapConnectionResponse, MapStylePresetCreate, MapStylePresetUpdate, MapStylePresetResponse
from services import map_connections as graph
from schemas.map_connections import MapConnectionSplit, MapConnectionSplitResponse
from schemas.map_connections import MapConnectionPlace, MapRouteObjectResponse, MapInstallationBoundary, MapRouteObjectDetach
from services.authorization import AuthorizationService
from services.map import (
    MapAddressObjectNotFoundError,
    MapTilesNotConfiguredError,
    MapViewportTooLargeError,
    create_map_tile_session,
    get_map_address_object_bounds,
    get_map_buildings,
)
from services.map_markers import (
    MapMarkerSyncConflictError,
    MapMarkerBuildingNotFoundError,
    MapMarkerNotFoundError,
    create_marker,
    delete_marker,
    get_marker,
    get_markers,
    update_marker,
)


class MapRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def wrapped(request):
            try:
                return await handler(request)
            except MapOperationError as exc:
                raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        return wrapped


router = APIRouter(prefix="/map", tags=["Map"], route_class=MapRoute)

MapReadContext = Annotated[
    CurrentCompanyContext,
    Depends(
        require_permission(
            PermissionCode.ADDRESSES_READ,
            minimum_scope=PermissionScope.COMPANY,
        )
    ),
]
MapManageContext = Annotated[
    CurrentCompanyContext,
    Depends(
        require_permission(
            PermissionCode.ADDRESSES_MANAGE,
            minimum_scope=PermissionScope.COMPANY,
        )
    ),
]
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
MapFilters = Annotated[MapFilter, Depends(map_filters)]


async def actor(session, context):
    manage = await AuthorizationService(session).has_permission(
        company_id=context.company.id,
        company_membership_id=context.membership.id,
        permission=PermissionCode.ADDRESSES_MANAGE,
        minimum_scope=PermissionScope.COMPANY,
    )
    return {"company_id": context.company.id, "user_id": context.user.id, "can_manage": manage}


@router.get("/session", response_model=MapTileSessionResponse)
async def create_tile_session_endpoint(
    _: MapReadContext,
) -> MapTileSessionResponse:
    try:
        return create_map_tile_session()
    except MapTilesNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Map tiles are not configured",
        ) from exc


@router.get("/buildings", response_model=MapBuildingFeatureCollection)
async def get_map_buildings_endpoint(
    _: MapReadContext,
    session: DatabaseSession,
    west: Annotated[Decimal, Query(ge=-180, le=180)],
    south: Annotated[Decimal, Query(ge=-90, le=90)],
    east: Annotated[Decimal, Query(ge=-180, le=180)],
    north: Annotated[Decimal, Query(ge=-90, le=90)],
    filters: MapFilters,
) -> MapBuildingFeatureCollection:
    if west >= east or south >= north:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Viewport bounds must satisfy west < east "
                "and south < north"
            ),
        )
    try:
        return await get_map_buildings(
            session,
            company_id=_.company.id,
            filters=filters,
            west=west,
            south=south,
            east=east,
            north=north,
        )
    except MapViewportTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Too many buildings in viewport; zoom in and try again",
        ) from exc


@router.get(
    "/address-objects/{address_object_id}/bounds",
    response_model=MapAddressObjectBoundsResponse,
)
async def get_map_address_object_bounds_endpoint(
    address_object_id: int,
    _: MapReadContext,
    session: DatabaseSession,
) -> MapAddressObjectBoundsResponse:
    try:
        return await get_map_address_object_bounds(
            session,
            address_object_id=address_object_id,
        )
    except MapAddressObjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address object not found",
        ) from exc


@router.get("/markers", response_model=list[MapMarkerResponse])
async def list_map_markers_endpoint(
    context: MapReadContext,
    session: DatabaseSession,
    filters: MapFilters,
    west: Annotated[Decimal | None, Query(ge=-180, le=180)] = None,
    south: Annotated[Decimal | None, Query(ge=-90, le=90)] = None,
    east: Annotated[Decimal | None, Query(ge=-180, le=180)] = None,
    north: Annotated[Decimal | None, Query(ge=-90, le=90)] = None,
) -> list[MapMarkerResponse]:
    bounds = (west, south, east, north)
    if any(value is not None for value in bounds):
        if any(value is None for value in bounds):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="All viewport bounds must be supplied together",
            )
        if west >= east or south >= north:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Viewport bounds must satisfy west < east and south < north",
            )
    return await get_markers(
        session,
        **await actor(session, context),
        west=west,
        south=south,
        east=east,
        north=north,
        filters=filters,
    )


@router.post(
    "/markers",
    response_model=MapMarkerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_map_marker_endpoint(
    data: MapMarkerCreate,
    context: MapReadContext,
    session: DatabaseSession,
) -> MapMarkerResponse:
    try:
        return await create_marker(
            session, **await actor(session, context), data=data
        )
    except MapMarkerBuildingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found",
        ) from exc


@router.get("/markers/{marker_id}", response_model=MapMarkerResponse)
async def get_map_marker_endpoint(
    marker_id: int,
    context: MapReadContext,
    session: DatabaseSession,
) -> MapMarkerResponse:
    try:
        return await get_marker(
            session, **await actor(session, context), marker_id=marker_id
        )
    except MapMarkerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Map marker not found",
        ) from exc


@router.patch("/markers/{marker_id}", response_model=MapMarkerResponse)
async def update_map_marker_endpoint(
    marker_id: int,
    data: MapMarkerUpdate,
    context: MapReadContext,
    session: DatabaseSession,
) -> MapMarkerResponse:
    try:
        return await update_marker(
            session,
            **await actor(session, context),
            marker_id=marker_id,
            data=data,
        )
    except MapMarkerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Map marker not found",
        ) from exc
    except MapMarkerSyncConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except MapMarkerBuildingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found",
        ) from exc


@router.delete("/markers/{marker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_map_marker_endpoint(
    marker_id: int,
    context: MapReadContext,
    session: DatabaseSession,
    expected_version: Annotated[int | None, Query(gt=0)] = None,
) -> Response:
    try:
        await delete_marker(
            session, **await actor(session, context), marker_id=marker_id, expected_version=expected_version
        )
    except MapMarkerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Map marker not found",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/endpoints")
async def search_map_endpoints(context: MapReadContext, session: DatabaseSession,
    q: Annotated[str, Query(max_length=200)] = "", limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    return await graph.search_endpoints(session, company_id=context.company.id, user_id=context.user.id, query=q, limit=limit, offset=offset)


@router.get("/buildings/{building_id}/marker", response_model=MapMarkerResponse | None)
async def building_marker(building_id: int, context: MapReadContext, session: DatabaseSession):
    from sqlalchemy import select
    from models.map_markers import MapMarker
    marker_id = await session.scalar(select(MapMarker.id).where(MapMarker.company_id == context.company.id, MapMarker.building_id == building_id, MapMarker.building_link_role == "represents"))
    return await get_marker(session, **await actor(session, context), marker_id=marker_id) if marker_id else None


@router.get("/connections", response_model=list[MapConnectionResponse])
async def list_connections(context: MapReadContext, session: DatabaseSession,
    filters: MapFilters,
    west: Annotated[Decimal | None, Query(ge=-180, le=180)] = None,
    south: Annotated[Decimal | None, Query(ge=-90, le=90)] = None,
    east: Annotated[Decimal | None, Query(ge=-180, le=180)] = None,
    north: Annotated[Decimal | None, Query(ge=-90, le=90)] = None,
    endpoint_kind: Annotated[str | None, Query(pattern="^(building|marker)$")] = None,
    endpoint_id: Annotated[int | None, Query(gt=0)] = None):
    bounds = None
    if any(value is not None for value in (west, south, east, north)):
        if any(value is None for value in (west, south, east, north)) or west >= east or south >= north:
            raise HTTPException(status_code=422, detail="All valid viewport bounds must be supplied together")
        bounds = {"west": west, "south": south, "east": east, "north": north}
    if (endpoint_kind is None) != (endpoint_id is None):
        raise HTTPException(status_code=422, detail="Endpoint kind and ID are required together")
    return await graph.get_connections(session, **await actor(session, context), bounds=bounds, endpoint_kind=endpoint_kind, endpoint_id=endpoint_id, filters=filters)


@router.post("/connections", response_model=MapConnectionResponse, status_code=201)
async def create_connection(data: MapConnectionCreate, context: MapReadContext, session: DatabaseSession):
    return await graph.save_connection(session, **await actor(session, context), data=data)


@router.get("/connections/{connection_id}", response_model=MapConnectionResponse)
async def connection_detail(connection_id: int, context: MapReadContext, session: DatabaseSession):
    return await graph.get_connection(session, **await actor(session, context), connection_id=connection_id)


@router.patch("/connections/{connection_id}", response_model=MapConnectionResponse)
async def change_connection(connection_id: int, data: MapConnectionUpdate, context: MapReadContext, session: DatabaseSession):
    return await graph.save_connection(session, **await actor(session, context), data=data, connection_id=connection_id)


@router.post("/connections/{connection_id}/split", response_model=MapConnectionSplitResponse, status_code=201)
async def split_connection(connection_id: int, data: MapConnectionSplit, context: MapReadContext, session: DatabaseSession):
    return await graph.split_connection(session, **await actor(session, context), data=data, connection_id=connection_id)


@router.post("/connections/{connection_id}/route-objects", response_model=MapRouteObjectResponse, status_code=201)
async def place_route_object(connection_id: int, data: MapConnectionPlace, context: MapReadContext, session: DatabaseSession):
    return await graph.place_route_object(session, **await actor(session, context), data=data, connection_id=connection_id)


@router.post("/connections/{connection_id}/installation-boundaries", response_model=MapConnectionResponse)
async def installation_boundary(connection_id: int, data: MapInstallationBoundary, context: MapReadContext, session: DatabaseSession):
    return await graph.set_installation_boundary(session, **await actor(session, context), data=data, connection_id=connection_id)


@router.post("/connections/{connection_id}/route-objects/{marker_id}/detach", response_model=MapRouteObjectResponse)
async def detach_route_object(connection_id: int, marker_id: int, data: MapRouteObjectDetach, context: MapReadContext, session: DatabaseSession):
    return await graph.detach_route_object(session, **await actor(session, context), data=data, connection_id=connection_id, marker_id=marker_id)


@router.delete("/connections/{connection_id}", status_code=204)
async def remove_connection(connection_id: int, context: MapReadContext, session: DatabaseSession, expected_version: Annotated[int | None, Query(gt=0)] = None):
    await graph.delete_connection(session, **await actor(session, context), connection_id=connection_id, expected_version=expected_version)
    return Response(status_code=204)


@router.get("/marker-styles", response_model=list[MapStylePresetResponse])
async def list_marker_styles(context: MapReadContext, session: DatabaseSession):
    return await graph.list_presets(session, company_id=context.company.id, user_id=context.user.id)


@router.post("/marker-styles", response_model=MapStylePresetResponse, status_code=201)
async def create_marker_style(data: MapStylePresetCreate, context: MapReadContext, session: DatabaseSession):
    return await graph.save_preset(session, company_id=context.company.id, user_id=context.user.id, data=data)


@router.get("/marker-styles/{preset_id}", response_model=MapStylePresetResponse)
async def marker_style_detail(preset_id: int, context: MapReadContext, session: DatabaseSession):
    return await graph.get_preset(session, company_id=context.company.id, user_id=context.user.id, preset_id=preset_id)


@router.patch("/marker-styles/{preset_id}", response_model=MapStylePresetResponse)
async def change_marker_style(preset_id: int, data: MapStylePresetUpdate, context: MapReadContext, session: DatabaseSession):
    return await graph.save_preset(session, company_id=context.company.id, user_id=context.user.id, data=data, preset_id=preset_id)


@router.delete("/marker-styles/{preset_id}", status_code=204)
async def remove_marker_style(preset_id: int, context: MapReadContext, session: DatabaseSession):
    await graph.delete_preset(session, company_id=context.company.id, user_id=context.user.id, preset_id=preset_id)
    return Response(status_code=204)
