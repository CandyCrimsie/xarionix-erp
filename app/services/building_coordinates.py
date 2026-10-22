"""One physical building point shared by explicitly synchronized annotations.

Callers lock the building before changing it, then update markers in the same
transaction. Only coordinates are shared across companies, never marker data.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.buildings import Building
from models.map_markers import MapMarker


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
    # Clearing either coordinate makes the house unavailable on the map. Keep
    # annotations at their last point, but explicitly stop synchronization.
    values = (
        {"latitude": building.latitude, "longitude": building.longitude}
        if building.latitude is not None and building.longitude is not None
        else {"sync_building_coordinates": False}
    )
    await session.execute(
        update(MapMarker)
        .where(
            MapMarker.building_id == building.id,
            MapMarker.sync_building_coordinates.is_(True),
        )
        .values(**values)
    )
