from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.codes import PermissionCode
from core.permissions.scopes import PermissionScope
from dependencies.authorization import require_permission
from dependencies.company import CurrentCompanyContext
from dependencies.database import get_session
from schemas.map import (
    MapAddressObjectBoundsResponse,
    MapBuildingFeatureCollection,
    MapTileSessionResponse,
)
from schemas.map_markers import MapMarkerCreate, MapMarkerResponse, MapMarkerUpdate
from services.map import (
    MapAddressObjectNotFoundError,
    MapTilesNotConfiguredError,
    MapViewportTooLargeError,
    create_map_tile_session,
    get_map_address_object_bounds,
    get_map_buildings,
)
from services.map_markers import (
    MapMarkerBuildingNotFoundError,
    MapMarkerNotFoundError,
    create_marker,
    delete_marker,
    get_marker,
    get_markers,
    update_marker,
)


router = APIRouter(prefix="/map", tags=["Map"])

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
        company_id=context.company.id,
        west=west,
        south=south,
        east=east,
        north=north,
    )


@router.post(
    "/markers",
    response_model=MapMarkerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_map_marker_endpoint(
    data: MapMarkerCreate,
    context: MapManageContext,
    session: DatabaseSession,
) -> MapMarkerResponse:
    try:
        return await create_marker(
            session, company_id=context.company.id, data=data
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
            session, company_id=context.company.id, marker_id=marker_id
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
    context: MapManageContext,
    session: DatabaseSession,
) -> MapMarkerResponse:
    try:
        return await update_marker(
            session,
            company_id=context.company.id,
            marker_id=marker_id,
            data=data,
        )
    except MapMarkerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Map marker not found",
        ) from exc
    except MapMarkerBuildingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found",
        ) from exc


@router.delete("/markers/{marker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_map_marker_endpoint(
    marker_id: int,
    context: MapManageContext,
    session: DatabaseSession,
) -> Response:
    try:
        await delete_marker(
            session, company_id=context.company.id, marker_id=marker_id
        )
    except MapMarkerNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Map marker not found",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
