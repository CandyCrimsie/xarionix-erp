import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import (
    Select,
    Text,
    case,
    cast,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.address_search import (
    AddressSearchQuery,
    FUZZY_MIN_TOKEN_LENGTH,
    FUZZY_SIMILARITY_THRESHOLD,
)
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


@dataclass(slots=True, frozen=True)
class AddressSearchRecord:
    kind: str
    full_address: str
    address_object: AddressObjectRecord | None = None
    building: BuildingRecord | None = None


@dataclass(slots=True, frozen=True)
class AddressObjectBuildingBounds:
    west: Decimal
    south: Decimal
    east: Decimal
    north: Decimal
    building_count: int


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
            cast(AddressObject.normalized_name, Text).label(
                "normalized_leaf_name"
            ),
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
            cast(child_object.c.normalized_name, Text),
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


async def list_building_records_in_bounds(
    session: AsyncSession,
    *,
    west: Decimal,
    south: Decimal,
    east: Decimal,
    north: Decimal,
    limit: int,
) -> list[BuildingRecord]:
    """Return at most ``limit`` geocoded buildings in a viewport.

    The caller intentionally asks for one row more than the public limit, so
    it can reject an over-wide viewport instead of silently returning a
    partial and therefore misleading map.
    """
    result = await session.execute(
        _building_record_select()
        .where(
            Building.latitude.is_not(None),
            Building.longitude.is_not(None),
            Building.longitude >= west,
            Building.longitude <= east,
            Building.latitude >= south,
            Building.latitude <= north,
        )
        .order_by(Building.id)
        .limit(limit)
    )
    return _building_records(result.all())


async def get_address_object_building_bounds(
    session: AsyncSession,
    *,
    address_object_id: int,
) -> AddressObjectBuildingBounds | None:
    descendants = (
        select(AddressObject.id)
        .where(AddressObject.id == address_object_id)
        .cte(name="map_address_descendants", recursive=True)
    )
    child = AddressObject.__table__.alias("map_address_child")
    descendants = descendants.union_all(
        select(child.c.id).where(child.c.parent_id == descendants.c.id)
    )
    result = await session.execute(
        select(
            func.min(Building.longitude),
            func.min(Building.latitude),
            func.max(Building.longitude),
            func.max(Building.latitude),
            func.count(Building.id),
        )
        .join(
            descendants,
            descendants.c.id == Building.address_object_id,
        )
        .where(
            Building.latitude.is_not(None),
            Building.longitude.is_not(None),
        )
    )
    west, south, east, north, count = result.one()
    if not count:
        return None
    return AddressObjectBuildingBounds(
        west=west,
        south=south,
        east=east,
        north=north,
        building_count=count,
    )


def _search_token_match(searchable_names, searchable_leaf_name, token: str):
    escaped_token = re.escape(token)
    exact_word = searchable_names.regexp_match(rf"(^| ){escaped_token}($| )")
    exact_leaf = searchable_leaf_name == token
    word_prefix = searchable_names.regexp_match(rf"(^| ){escaped_token}")
    leaf_prefix = searchable_leaf_name.startswith(token)
    substring = searchable_names.contains(token)
    similarity = func.word_similarity(token, searchable_names)
    fuzzy = (
        similarity >= FUZZY_SIMILARITY_THRESHOLD
        if len(token) >= FUZZY_MIN_TOKEN_LENGTH and token.isalpha()
        else literal(False)
    )
    score = case(
        (exact_leaf, 50.0),
        (exact_word, 40.0),
        (leaf_prefix, 30.0),
        (word_prefix, 24.0),
        (substring, 10.0),
        (fuzzy, similarity * 8.0),
        else_=0.0,
    )
    return or_(substring, fuzzy), score


async def search_address_records(
    session: AsyncSession,
    *,
    query: AddressSearchQuery,
    limit: int,
    offset: int,
) -> tuple[list[AddressSearchRecord], int]:
    paths = _address_paths_cte()
    searchable_names = func.replace(paths.c.normalized_path, "ё", "е")
    searchable_leaf_name = func.replace(
        paths.c.normalized_leaf_name,
        "ё",
        "е",
    )
    name_filters = []
    name_relevance = literal(0.0)
    for token in query.name_tokens:
        token_filter, token_score = _search_token_match(
            searchable_names,
            searchable_leaf_name,
            token,
        )
        name_filters.append(token_filter)
        name_relevance += token_score

    candidates = []
    has_building_parts = any(
        (query.house_number, query.corpus, query.structure)
    )
    if query.name_tokens and not has_building_parts:
        complete_leaf_query = " ".join(query.name_tokens)
        object_relevance = name_relevance + case(
            (searchable_leaf_name == complete_leaf_query, 120.0),
            (searchable_leaf_name.startswith(complete_leaf_query), 60.0),
            else_=0.0,
        )
        candidates.append(
            select(
                literal("address_object").label("kind"),
                paths.c.object_id.label("entity_id"),
                paths.c.display_path.label("full_address"),
                paths.c.normalized_path.label("sort_path"),
                object_relevance.label("relevance"),
                literal(0).label("kind_order"),
            ).where(*name_filters)
        )

    building_filters = list(name_filters)
    building_relevance = name_relevance
    if query.house_number is not None:
        building_filters.append(Building.normalized_number == query.house_number)
        building_relevance += 120.0
    if query.corpus is not None:
        building_filters.append(Building.normalized_corpus == query.corpus)
        building_relevance += 50.0
    else:
        building_relevance += case(
            (Building.normalized_corpus == "", 2.0), else_=0.0
        )
    if query.structure is not None:
        building_filters.append(Building.normalized_structure == query.structure)
        building_relevance += 45.0
    else:
        building_relevance += case(
            (Building.normalized_structure == "", 4.0), else_=0.0
        )

    if building_filters:
        candidates.append(
            select(
                literal("building").label("kind"),
                Building.id.label("entity_id"),
                _building_full_address(paths).label("full_address"),
                func.concat(
                    paths.c.normalized_path,
                    " ",
                    Building.normalized_number,
                    " ",
                    Building.normalized_corpus,
                    " ",
                    Building.normalized_structure,
                ).label("sort_path"),
                building_relevance.label("relevance"),
                literal(1).label("kind_order"),
            )
            .join(paths, paths.c.object_id == Building.address_object_id)
            .where(*building_filters)
        )
    if not candidates:
        return [], 0

    combined = (
        union_all(*candidates).cte("address_search_candidates")
        if len(candidates) > 1
        else candidates[0].cte("address_search_candidates")
    )
    total_result = await session.execute(
        select(func.count()).select_from(combined)
    )
    page_result = await session.execute(
        select(
            combined.c.kind,
            combined.c.entity_id,
            combined.c.full_address,
        )
        .order_by(
            combined.c.relevance.desc(),
            combined.c.kind_order,
            combined.c.sort_path,
            combined.c.entity_id,
        )
        .limit(limit)
        .offset(offset)
    )
    page = page_result.all()
    object_ids = [row.entity_id for row in page if row.kind == "address_object"]
    building_ids = [row.entity_id for row in page if row.kind == "building"]

    object_records: dict[int, AddressObjectRecord] = {}
    if object_ids:
        object_result = await session.execute(
            select(AddressObject, AddressType)
            .join(AddressType, AddressType.id == AddressObject.type_id)
            .where(AddressObject.id.in_(object_ids))
        )
        object_records = {
            address_object.id: AddressObjectRecord(address_object, address_type)
            for address_object, address_type in object_result.all()
        }
    buildings: dict[int, Building] = {}
    if building_ids:
        building_result = await session.execute(
            select(Building).where(Building.id.in_(building_ids))
        )
        buildings = {
            building.id: building for building in building_result.scalars()
        }

    records: list[AddressSearchRecord] = []
    for row in page:
        if row.kind == "address_object":
            object_record = object_records.get(row.entity_id)
            if object_record is not None:
                records.append(AddressSearchRecord(
                    kind=row.kind,
                    full_address=row.full_address,
                    address_object=object_record,
                ))
        else:
            building = buildings.get(row.entity_id)
            if building is not None:
                records.append(AddressSearchRecord(
                    kind=row.kind,
                    full_address=row.full_address,
                    building=BuildingRecord(building, row.full_address),
                ))
    return records, total_result.scalar_one()


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
