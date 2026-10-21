from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.map_markers import MapMarker


async def list_map_markers(
    session: AsyncSession,
    *,
    company_id: int,
    west: Decimal | None = None,
    south: Decimal | None = None,
    east: Decimal | None = None,
    north: Decimal | None = None,
    limit: int = 5000,
) -> list[MapMarker]:
    query = select(MapMarker).where(MapMarker.company_id == company_id)
    if None not in (west, south, east, north):
        query = query.where(
            MapMarker.longitude >= west,
            MapMarker.longitude <= east,
            MapMarker.latitude >= south,
            MapMarker.latitude <= north,
        )
    result = await session.execute(query.order_by(MapMarker.id).limit(limit))
    return list(result.scalars().all())


async def get_map_marker(
    session: AsyncSession,
    *,
    company_id: int,
    marker_id: int,
) -> MapMarker | None:
    result = await session.execute(
        select(MapMarker).where(
            MapMarker.id == marker_id,
            MapMarker.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()
