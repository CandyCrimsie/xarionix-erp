from dataclasses import dataclass

from sqlalchemy import (
    Select,
    Text,
    case,
    cast,
    func,
    literal,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from models.address_objects import AddressObject
from models.address_types import (
    AddressType,
    AddressTypeCategory,
)
from models.buildings import Building
from models.entrances import Entrance
from models.equipment import Equipment
from models.locations import Location


@dataclass(slots=True, frozen=True)
class AddressObjectRecord:
    address_object: AddressObject
    address_type: AddressType


@dataclass(slots=True, frozen=True)
class BuildingRecord:
    building: Building
    full_address: str


async def list_address_types(
    session: AsyncSession,
) -> list[AddressType]:
    result = await session.execute(
        select(AddressType).order_by(
            AddressType.sort_order,
            AddressType.name,
            AddressType.id,
        )
    )
    return list(result.scalars().all())


async def get_address_type(
    session: AsyncSession,
    address_type_id: int,
) -> AddressType | None:
    return await session.get(AddressType, address_type_id)


async def get_address_type_by_code(
    session: AsyncSession,
    code: str,
) -> AddressType | None:
    result = await session.execute(
        select(AddressType).where(AddressType.code == code)
    )
    return result.scalar_one_or_none()


async def list_address_object_records(
    session: AsyncSession,
    *,
    parent_id: int | None,
) -> list[AddressObjectRecord]:
    parent_filter = (
        AddressObject.parent_id.is_(None)
        if parent_id is None
        else AddressObject.parent_id == parent_id
    )
    result = await session.execute(
        select(AddressObject, AddressType)
        .join(AddressType, AddressType.id == AddressObject.type_id)
        .where(parent_filter)
        .order_by(
            AddressType.sort_order,
            AddressObject.normalized_name,
            AddressObject.id,
        )
    )
    return [
        AddressObjectRecord(address_object=row[0], address_type=row[1])
        for row in result.all()
    ]


async def list_all_address_object_records(
    session: AsyncSession,
) -> list[AddressObjectRecord]:
    result = await session.execute(
        select(AddressObject, AddressType)
        .join(AddressType, AddressType.id == AddressObject.type_id)
        .order_by(
            AddressType.sort_order,
            AddressObject.normalized_name,
            AddressObject.id,
        )
    )
    return [
        AddressObjectRecord(address_object=row[0], address_type=row[1])
        for row in result.all()
    ]


async def get_address_object_record(
    session: AsyncSession,
    address_object_id: int,
) -> AddressObjectRecord | None:
    result = await session.execute(
        select(AddressObject, AddressType)
        .join(AddressType, AddressType.id == AddressObject.type_id)
        .where(AddressObject.id == address_object_id)
    )
    row = result.one_or_none()
    if row is None:
        return None
    return AddressObjectRecord(address_object=row[0], address_type=row[1])


async def get_address_object_descendant_ids(
    session: AsyncSession,
    address_object_id: int,
) -> set[int]:
    descendants = (
        select(AddressObject.id)
        .where(AddressObject.parent_id == address_object_id)
        .cte(name="address_descendants", recursive=True)
    )
    descendants = descendants.union_all(
        select(AddressObject.id).join(
            descendants,
            AddressObject.parent_id == descendants.c.id,
        )
    )
    result = await session.execute(select(descendants.c.id))
    return set(result.scalars().all())


async def address_type_is_used(
    session: AsyncSession,
    address_type_id: int,
) -> bool:
    result = await session.execute(
        select(AddressObject.id)
        .where(AddressObject.type_id == address_type_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def address_object_has_children_or_buildings(
    session: AsyncSession,
    address_object_id: int,
) -> bool:
    child = await session.execute(
        select(AddressObject.id)
        .where(AddressObject.parent_id == address_object_id)
        .limit(1)
    )
    if child.scalar_one_or_none() is not None:
        return True
    building = await session.execute(
        select(Building.id)
        .where(Building.address_object_id == address_object_id)
        .limit(1)
    )
    return building.scalar_one_or_none() is not None


def _address_paths_cte():
    segment = case(
        (
            AddressType.category.in_(
                (
                    AddressTypeCategory.COUNTRY,
                    AddressTypeCategory.REGION,
                    AddressTypeCategory.LOCALITY,
                )
            ),
            AddressObject.name,
        ),
        else_=func.concat(
            func.coalesce(AddressType.short_name, AddressType.name),
            " ",
            AddressObject.name,
        ),
    )
    paths = (
        select(
            AddressObject.id.label("object_id"),
            cast(segment, Text).label("display_path"),
            cast(AddressObject.normalized_name, Text).label("normalized_path"),
        )
        .join(AddressType, AddressType.id == AddressObject.type_id)
        .where(AddressObject.parent_id.is_(None))
        .cte(name="address_paths", recursive=True)
    )
    parent_path = paths.alias("parent_path")
    child_object = AddressObject.__table__.alias("child_object")
    child_type = AddressType.__table__.alias("child_type")
    child_segment = case(
        (
            child_type.c.category.in_(
                (
                    AddressTypeCategory.COUNTRY.value,
                    AddressTypeCategory.REGION.value,
                    AddressTypeCategory.LOCALITY.value,
                )
            ),
            child_object.c.name,
        ),
        else_=func.concat(
            func.coalesce(child_type.c.short_name, child_type.c.name),
            " ",
            child_object.c.name,
        ),
    )
    return paths.union_all(
        select(
            child_object.c.id,
            func.concat(
                parent_path.c.display_path,
                ", ",
                child_segment,
            ),
            func.concat(
                parent_path.c.normalized_path,
                " ",
                child_object.c.normalized_name,
            ),
        )
        .select_from(child_object)
        .join(
            parent_path,
            child_object.c.parent_id == parent_path.c.object_id,
        )
        .join(child_type, child_type.c.id == child_object.c.type_id)
    )


def _building_full_address(paths) -> object:
    return func.concat(
        paths.c.display_path,
        ", д. ",
        Building.number,
        case(
            (Building.corpus.is_not(None), func.concat(", корп. ", Building.corpus)),
            else_=literal(""),
        ),
        case(
            (
                Building.structure.is_not(None),
                func.concat(", стр. ", Building.structure),
            ),
            else_=literal(""),
        ),
    )


def _building_record_select() -> Select:
    paths = _address_paths_cte()
    return (
        select(
            Building,
            _building_full_address(paths).label("full_address"),
        )
        .join(paths, paths.c.object_id == Building.address_object_id)
    )


def _building_records(rows) -> list[BuildingRecord]:
    return [
        BuildingRecord(building=row[0], full_address=row[1])
        for row in rows
    ]


async def list_building_records(
    session: AsyncSession,
    *,
    address_object_id: int,
) -> list[BuildingRecord]:
    result = await session.execute(
        _building_record_select()
        .where(Building.address_object_id == address_object_id)
        .order_by(
            Building.normalized_number,
            Building.normalized_corpus,
            Building.normalized_structure,
            Building.id,
        )
    )
    return _building_records(result.all())


async def get_building_record(
    session: AsyncSession,
    building_id: int,
) -> BuildingRecord | None:
    result = await session.execute(
        _building_record_select().where(Building.id == building_id)
    )
    row = result.one_or_none()
    if row is None:
        return None
    return BuildingRecord(building=row[0], full_address=row[1])


async def search_building_records(
    session: AsyncSession,
    *,
    tokens: list[str],
    limit: int,
    offset: int,
) -> tuple[list[BuildingRecord], int]:
    paths = _address_paths_cte()
    searchable = func.concat(
        paths.c.normalized_path,
        " ",
        Building.normalized_number,
        " дом ",
        Building.normalized_corpus,
        " корпус ",
        Building.normalized_structure,
        " строение",
    )
    filters = [searchable.contains(token) for token in tokens]
    base = (
        select(Building.id)
        .join(paths, paths.c.object_id == Building.address_object_id)
        .where(*filters)
    )
    total_result = await session.execute(
        select(func.count()).select_from(base.subquery())
    )
    result = await session.execute(
        select(
            Building,
            _building_full_address(paths).label("full_address"),
        )
        .join(paths, paths.c.object_id == Building.address_object_id)
        .where(*filters)
        .order_by(paths.c.normalized_path, Building.normalized_number)
        .limit(limit)
        .offset(offset)
    )
    return _building_records(result.all()), total_result.scalar_one()


async def get_building(
    session: AsyncSession,
    building_id: int,
) -> Building | None:
    return await session.get(Building, building_id)


async def building_has_entrances_or_locations(
    session: AsyncSession,
    building_id: int,
) -> bool:
    entrance = await session.execute(
        select(Entrance.id)
        .where(Entrance.building_id == building_id)
        .limit(1)
    )
    if entrance.scalar_one_or_none() is not None:
        return True
    location = await session.execute(
        select(Location.id)
        .where(Location.building_id == building_id)
        .limit(1)
    )
    return location.scalar_one_or_none() is not None


async def list_entrances(
    session: AsyncSession,
    building_id: int,
) -> list[Entrance]:
    result = await session.execute(
        select(Entrance)
        .where(Entrance.building_id == building_id)
        .order_by(Entrance.normalized_number, Entrance.id)
    )
    return list(result.scalars().all())


async def get_entrance(
    session: AsyncSession,
    entrance_id: int,
) -> Entrance | None:
    return await session.get(Entrance, entrance_id)


async def entrance_has_locations(
    session: AsyncSession,
    entrance_id: int,
) -> bool:
    result = await session.execute(
        select(Location.id)
        .where(Location.entrance_id == entrance_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def list_locations(
    session: AsyncSession,
    *,
    company_id: int,
    building_id: int,
) -> list[Location]:
    result = await session.execute(
        select(Location)
        .where(
            Location.company_id == company_id,
            Location.building_id == building_id,
        )
        .order_by(Location.entrance_id, Location.floor, Location.name, Location.id)
    )
    return list(result.scalars().all())


async def get_location(
    session: AsyncSession,
    *,
    company_id: int,
    location_id: int,
) -> Location | None:
    result = await session.execute(
        select(Location).where(
            Location.id == location_id,
            Location.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()


async def location_has_equipment(
    session: AsyncSession,
    location_id: int,
) -> bool:
    result = await session.execute(
        select(Equipment.id)
        .where(Equipment.location_id == location_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
