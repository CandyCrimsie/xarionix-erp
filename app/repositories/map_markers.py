from decimal import Decimal

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.map_domain import visible_to
from models.buildings import Building
from models.map_markers import MapMarker
from repositories.addresses import _address_paths_cte, _building_full_address


def marker_position_columns():
    return (
        case((MapMarker.building_link_role == "represents", Building.latitude), else_=MapMarker.latitude),
        case((MapMarker.building_link_role == "represents", Building.longitude), else_=MapMarker.longitude),
    )


def marker_records_query():
    paths = _address_paths_cte()
    return select(MapMarker, Building, _building_full_address(paths)).outerjoin(
        Building, Building.id == MapMarker.building_id
    ).outerjoin(paths, paths.c.object_id == Building.address_object_id)


async def list_map_markers(session: AsyncSession, *, company_id: int, user_id: int,
                           west: Decimal | None = None, south: Decimal | None = None,
                           east: Decimal | None = None, north: Decimal | None = None,
                           limit: int = 5001, predicates=()):
    query = marker_records_query().where(*visible_to(MapMarker, company_id, user_id), *predicates)
    if None not in (west, south, east, north):
        lat, lng = marker_position_columns()
        query = query.where(lng >= west, lng <= east, lat >= south, lat <= north)
    return (await session.execute(query.order_by(MapMarker.id).limit(limit))).all()


async def get_map_marker(session: AsyncSession, *, company_id: int, marker_id: int, user_id: int = 0):
    return await session.scalar(select(MapMarker).where(
        MapMarker.id == marker_id, *visible_to(MapMarker, company_id, user_id)
    ).execution_options(populate_existing=True))
