from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from services.map import (
    MapAddressObjectNotFoundError,
    MapTilesNotConfiguredError,
    MapViewportTooLargeError,
    create_map_tile_session,
    get_map_address_object_bounds,
    get_map_buildings,
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
