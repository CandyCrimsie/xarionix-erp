from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from models.buildings import Building
from models.map_markers import MapMarker
from repositories.map_markers import get_map_marker, list_map_markers
from schemas.map_markers import MapMarkerCreate, MapMarkerResponse, MapMarkerUpdate
from services.building_coordinates import (
    lock_building,
    lock_buildings,
    synchronize_building_markers,
)


class MapMarkerNotFoundError(Exception):
    pass


class MapMarkerBuildingNotFoundError(Exception):
    pass


class MapMarkerSyncConflictError(Exception):
    pass


async def get_markers(
    session: AsyncSession,
    *,
    company_id: int,
    west: Decimal | None = None,
    south: Decimal | None = None,
    east: Decimal | None = None,
    north: Decimal | None = None,
) -> list[MapMarkerResponse]:
    return [
        MapMarkerResponse.model_validate(marker)
        for marker in await list_map_markers(
            session,
            company_id=company_id,
            west=west,
            south=south,
            east=east,
            north=north,
        )
    ]


async def get_marker(
    session: AsyncSession,
    *,
    company_id: int,
    marker_id: int,
) -> MapMarkerResponse:
    marker = await get_map_marker(
        session, company_id=company_id, marker_id=marker_id
    )
    if marker is None:
        raise MapMarkerNotFoundError
    return MapMarkerResponse.model_validate(marker)


async def _validate_building(
    session: AsyncSession, building_id: int | None
) -> Building | None:
    building = await lock_building(session, building_id) if building_id is not None else None
    if building_id is not None and building is None:
        raise MapMarkerBuildingNotFoundError
    return building


async def create_marker(
    session: AsyncSession,
    *,
    company_id: int,
    data: MapMarkerCreate,
) -> MapMarkerResponse:
    building = await _validate_building(session, data.building_id)
    marker = MapMarker(company_id=company_id, **data.model_dump())
    session.add(marker)
    try:
        if marker.sync_building_coordinates:
            assert building is not None
            building.latitude = marker.latitude
            building.longitude = marker.longitude
            await session.flush()
            await synchronize_building_markers(session, building)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    await session.refresh(marker)
    return MapMarkerResponse.model_validate(marker)


async def update_marker(
    session: AsyncSession,
    *,
    company_id: int,
    marker_id: int,
    data: MapMarkerUpdate,
) -> MapMarkerResponse:
    marker = await get_map_marker(
        session, company_id=company_id, marker_id=marker_id
    )
    if marker is None:
        raise MapMarkerNotFoundError
    values = data.model_dump(exclude_unset=True)
    previous_building_id = marker.building_id
    building_id = values.get("building_id", previous_building_id)
    # Lock both sides in ID order for concurrent A -> B / B -> A relinks.
    buildings = await lock_buildings(
        session, {id_ for id_ in (previous_building_id, building_id) if id_ is not None}
    )
    building = buildings.get(building_id)
    if building_id is not None and building is None:
        raise MapMarkerBuildingNotFoundError
    # Building -> marker is also the lock order used by address edits, avoiding
    # deadlocks. Recheck the link after acquiring locks instead of using stale
    # state from a concurrent relink.
    await session.refresh(marker, with_for_update=True)
    if marker.building_id != previous_building_id:
        await session.rollback()
        raise MapMarkerSyncConflictError("Marker link changed; reload the marker")
    if building_id is None:
        if values.get("sync_building_coordinates"):
            await session.rollback()
            raise MapMarkerSyncConflictError("Building is required for coordinate synchronization")
        values["sync_building_coordinates"] = False
    enable_sync = values.get("sync_building_coordinates") and not marker.sync_building_coordinates
    try:
        for field_name, value in values.items():
            setattr(marker, field_name, value)
        if marker.sync_building_coordinates and (
            enable_sync
            or building_id != previous_building_id
            or {"latitude", "longitude"} & values.keys()
        ):
            assert building is not None
            building.latitude = marker.latitude
            building.longitude = marker.longitude
            await session.flush()
            await synchronize_building_markers(session, building)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    await session.refresh(marker)
    return MapMarkerResponse.model_validate(marker)


async def delete_marker(
    session: AsyncSession,
    *,
    company_id: int,
    marker_id: int,
) -> None:
    marker = await get_map_marker(
        session, company_id=company_id, marker_id=marker_id
    )
    if marker is None:
        raise MapMarkerNotFoundError
    await session.delete(marker)
    await session.commit()
