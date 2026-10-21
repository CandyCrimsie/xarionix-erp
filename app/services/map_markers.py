from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from models.map_markers import MapMarker
from repositories.addresses import get_building
from repositories.map_markers import get_map_marker, list_map_markers
from schemas.map_markers import MapMarkerCreate, MapMarkerResponse, MapMarkerUpdate


class MapMarkerNotFoundError(Exception):
    pass


class MapMarkerBuildingNotFoundError(Exception):
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


async def _validate_building(session: AsyncSession, building_id: int | None) -> None:
    if building_id is not None and await get_building(session, building_id) is None:
        raise MapMarkerBuildingNotFoundError


async def create_marker(
    session: AsyncSession,
    *,
    company_id: int,
    data: MapMarkerCreate,
) -> MapMarkerResponse:
    await _validate_building(session, data.building_id)
    marker = MapMarker(company_id=company_id, **data.model_dump())
    session.add(marker)
    await session.commit()
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
    if "building_id" in values:
        await _validate_building(session, values["building_id"])
    for field_name, value in values.items():
        setattr(marker, field_name, value)
    await session.commit()
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
