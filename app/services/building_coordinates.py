"""The building is the only coordinate store for its represents markers.

Connection endpoints are resolved when read; moving a point never rewrites
every attached line or overwrites its intermediate vertices.
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.buildings import Building
from models.map_markers import MapMarker
from models.map_connections import MapConnection


async def lock_building(session: AsyncSession, building_id: int) -> Building | None:
    return (await lock_buildings(session, {building_id})).get(building_id)


async def lock_buildings(session: AsyncSession, building_ids: set[int]) -> dict[int, Building]:
    if not building_ids:
        return {}
    result = await session.execute(
        select(Building)
        .where(Building.id.in_(building_ids))
        .order_by(Building.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return {building.id: building for building in result.scalars()}


async def synchronize_building_markers(
    session: AsyncSession, building: Building
) -> None:
    # Compatibility hook for the address service. No coordinate copies exist.
    await set_building_position(session, building, latitude=building.latitude, longitude=building.longitude)


async def set_building_position(session, building, *, latitude, longitude):
    from services.map_route_objects import guard_endpoint_position
    await guard_endpoint_position(session, "building", building.id, latitude, longitude)
    building.latitude = latitude if longitude is not None else None
    building.longitude = longitude if latitude is not None else None
    await session.flush()


async def detach_deleted_building(session, building) -> bool:
    dependency = await session.scalar(select(MapConnection.id).where(or_(
        MapConnection.source_building_id == building.id,
        MapConnection.target_building_id == building.id,
    )).limit(1))
    if dependency:
        return False
    markers = (await session.scalars(select(MapMarker).where(
        MapMarker.building_id == building.id
    ).order_by(MapMarker.id).with_for_update())).all()
    for marker in markers:
        if marker.building_link_role == "represents":
            marker.latitude, marker.longitude = building.latitude, building.longitude
        marker.building_link_role = "none"
        marker.building_id = None
        marker.version += 1
    await session.flush()
    return True
