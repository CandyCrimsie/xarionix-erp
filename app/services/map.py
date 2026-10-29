from __future__ import annotations

import base64
import hashlib
import time
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import config
from repositories.addresses import (
    get_address_object_building_bounds,
    get_address_object_record,
    list_building_records_in_bounds,
)
from schemas.map import (
    MapAddressObjectBoundsResponse,
    MapBounds,
    MapBuildingFeature,
    MapBuildingFeatureCollection,
    MapBuildingProperties,
    MapPointGeometry,
    MapTileSessionResponse,
)


class MapTilesNotConfiguredError(Exception):
    pass


class MapViewportTooLargeError(Exception):
    pass


class MapAddressObjectNotFoundError(Exception):
    pass


def create_map_tile_session(
    *,
    now: int | None = None,
) -> MapTileSessionResponse:
    if (
        not config.MAP_TILES_ENABLED
        or len(config.MAP_TILES_SIGNING_SECRET) < 24
    ):
        raise MapTilesNotConfiguredError

    current_time = int(time.time()) if now is None else now
    expires_at = current_time + config.MAP_TILE_SESSION_TTL_SECONDS
    payload = f"{expires_at} map-tiles {config.MAP_TILES_SIGNING_SECRET}".encode()
    signature = (
        base64.urlsafe_b64encode(hashlib.md5(payload).digest())
        .decode()
        .rstrip("=")
    )
    return MapTileSessionResponse(
        tile_url_template=(
            "/map/tiles/{z}/{x}/{y}.png"
            f"?expires={expires_at}&signature={signature}"
        ),
        expires_at=expires_at,
        default_latitude=config.MAP_DEFAULT_LATITUDE,
        default_longitude=config.MAP_DEFAULT_LONGITUDE,
        default_zoom=config.MAP_DEFAULT_ZOOM,
    )


async def get_map_buildings(
    session: AsyncSession,
    *,
    west: Decimal,
    south: Decimal,
    east: Decimal,
    north: Decimal,
    company_id: int | None = None,
    filters=None,
) -> MapBuildingFeatureCollection:
    from services.map_layers import map_predicates
    records = await list_building_records_in_bounds(
        session,
        west=west,
        south=south,
        east=east,
        north=north,
        limit=config.MAP_MAX_BUILDINGS_PER_VIEWPORT + 1,
        predicates=await map_predicates(session, company_id=company_id, kind="building", filters=filters),
    )
    if len(records) > config.MAP_MAX_BUILDINGS_PER_VIEWPORT:
        raise MapViewportTooLargeError

    return MapBuildingFeatureCollection(
        features=[
            MapBuildingFeature(
                id=record.building.id,
                geometry=MapPointGeometry(
                    coordinates=(
                        float(record.building.longitude),
                        float(record.building.latitude),
                    )
                ),
                properties=MapBuildingProperties(
                    id=record.building.id,
                    address_object_id=record.building.address_object_id,
                    number=record.building.number,
                    corpus=record.building.corpus,
                    structure=record.building.structure,
                    full_address=record.full_address,
                ),
            )
            for record in records
        ]
    )


async def get_map_address_object_bounds(
    session: AsyncSession,
    *,
    address_object_id: int,
) -> MapAddressObjectBoundsResponse:
    if await get_address_object_record(session, address_object_id) is None:
        raise MapAddressObjectNotFoundError
    bounds = await get_address_object_building_bounds(
        session,
        address_object_id=address_object_id,
    )
    if bounds is None:
        return MapAddressObjectBoundsResponse(bounds=None, building_count=0)
    return MapAddressObjectBoundsResponse(
        bounds=MapBounds(
            west=float(bounds.west),
            south=float(bounds.south),
            east=float(bounds.east),
            north=float(bounds.north),
        ),
        building_count=bounds.building_count,
    )
