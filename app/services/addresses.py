from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.address_normalization import normalize_address_value
from models.address_objects import AddressObject
from models.buildings import Building
from models.entrances import Entrance
from models.locations import Location
from repositories.addresses import (
    AddressObjectRecord,
    BuildingRecord,
    address_object_has_children_or_buildings,
    building_has_entrances_or_locations,
    entrance_has_locations,
    get_address_object_record,
    get_address_type,
    get_building,
    get_building_record,
    get_entrance,
    get_location,
    list_address_object_records,
    list_all_address_object_records,
    list_building_records,
    list_entrances,
    list_locations,
    location_has_equipment,
    search_building_records,
)
from schemas.addresses import (
    AddressObjectCreate,
    AddressObjectResponse,
    AddressObjectTreeResponse,
    AddressObjectUpdate,
    AddressSearchResponse,
    BuildingCreate,
    BuildingResponse,
    BuildingUpdate,
    EntranceCreate,
    EntranceUpdate,
    LocationCreate,
    LocationUpdate,
)
from services.address_hierarchy import (
    validate_address_object_hierarchy,
    validate_building_parent,
)


class AddressObjectNotFoundError(Exception):
    pass


class AddressTypeNotFoundError(Exception):
    pass


class DuplicateAddressObjectError(Exception):
    pass


class AddressObjectNotEmptyError(Exception):
    pass


class BuildingNotFoundError(Exception):
    pass


class DuplicateBuildingError(Exception):
    pass


class BuildingNotEmptyError(Exception):
    pass


class EntranceNotFoundError(Exception):
    pass


class DuplicateEntranceError(Exception):
    pass


class EntranceNotEmptyError(Exception):
    pass


class LocationNotFoundError(Exception):
    pass


class LocationEntranceMismatchError(Exception):
    pass


class LocationNotEmptyError(Exception):
    pass


def address_object_response(
    record: AddressObjectRecord,
) -> AddressObjectResponse:
    address_object = record.address_object
    address_type = record.address_type
    return AddressObjectResponse(
        id=address_object.id,
        parent_id=address_object.parent_id,
        type_id=address_type.id,
        type_code=address_type.code,
        type_category=address_type.category,
        type_name=address_type.name,
        type_short_name=address_type.short_name,
        name=address_object.name,
        created_at=address_object.created_at,
        updated_at=address_object.updated_at,
    )


def building_response(record: BuildingRecord) -> BuildingResponse:
    building = record.building
    return BuildingResponse(
        id=building.id,
        address_object_id=building.address_object_id,
        number=building.number,
        corpus=building.corpus,
        structure=building.structure,
        latitude=building.latitude,
        longitude=building.longitude,
        full_address=record.full_address,
        created_at=building.created_at,
        updated_at=building.updated_at,
    )


async def get_address_objects(
    session: AsyncSession,
    *,
    parent_id: int | None,
) -> list[AddressObjectResponse]:
    if parent_id is not None and await get_address_object_record(
        session,
        parent_id,
    ) is None:
        raise AddressObjectNotFoundError
    return [
        address_object_response(record)
        for record in await list_address_object_records(
            session,
            parent_id=parent_id,
        )
    ]


async def get_address_object(
    session: AsyncSession,
    address_object_id: int,
) -> AddressObjectResponse:
    record = await get_address_object_record(session, address_object_id)
    if record is None:
        raise AddressObjectNotFoundError
    return address_object_response(record)


async def get_address_object_tree(
    session: AsyncSession,
) -> list[AddressObjectTreeResponse]:
    records = await list_all_address_object_records(session)
    nodes = {
        record.address_object.id: AddressObjectTreeResponse(
            **address_object_response(record).model_dump(),
            children=[],
        )
        for record in records
    }
    roots: list[AddressObjectTreeResponse] = []
    for record in records:
        node = nodes[record.address_object.id]
        parent_id = record.address_object.parent_id
        if parent_id is None:
            roots.append(node)
        elif parent_id in nodes:
            nodes[parent_id].children.append(node)
    return roots


async def create_address_object(
    session: AsyncSession,
    data: AddressObjectCreate,
) -> AddressObjectResponse:
    address_type = await get_address_type(session, data.type_id)
    if address_type is None:
        raise AddressTypeNotFoundError
    await validate_address_object_hierarchy(
        session,
        address_type=address_type,
        parent_id=data.parent_id,
    )
    address_object = AddressObject(
        parent_id=data.parent_id,
        type_id=data.type_id,
        name=data.name,
        normalized_name=normalize_address_value(data.name),
    )
    session.add(address_object)
    try:
        await session.commit()
        await session.refresh(address_object)
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateAddressObjectError from exc
    record = await get_address_object_record(session, address_object.id)
    assert record is not None
    return address_object_response(record)


async def update_address_object(
    session: AsyncSession,
    address_object_id: int,
    data: AddressObjectUpdate,
) -> AddressObjectResponse:
    record = await get_address_object_record(session, address_object_id)
    if record is None:
        raise AddressObjectNotFoundError
    values = data.model_dump(exclude_unset=True)
    type_id = values.get("type_id", record.address_object.type_id)
    parent_id = values.get("parent_id", record.address_object.parent_id)
    address_type = await get_address_type(session, type_id)
    if address_type is None:
        raise AddressTypeNotFoundError
    await validate_address_object_hierarchy(
        session,
        address_type=address_type,
        parent_id=parent_id,
        moving_object_id=address_object_id,
    )
    for field, value in values.items():
        setattr(record.address_object, field, value)
    if "name" in values:
        record.address_object.normalized_name = normalize_address_value(
            values["name"]
        )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateAddressObjectError from exc
    updated = await get_address_object_record(session, address_object_id)
    assert updated is not None
    return address_object_response(updated)


async def delete_address_object(
    session: AsyncSession,
    address_object_id: int,
) -> None:
    record = await get_address_object_record(session, address_object_id)
    if record is None:
        raise AddressObjectNotFoundError
    if await address_object_has_children_or_buildings(session, address_object_id):
        raise AddressObjectNotEmptyError
    await session.delete(record.address_object)
    await session.commit()


async def get_buildings(
    session: AsyncSession,
    address_object_id: int,
) -> list[BuildingResponse]:
    if await get_address_object_record(session, address_object_id) is None:
        raise AddressObjectNotFoundError
    return [
        building_response(record)
        for record in await list_building_records(
            session,
            address_object_id=address_object_id,
        )
    ]


async def get_building_response(
    session: AsyncSession,
    building_id: int,
) -> BuildingResponse:
    record = await get_building_record(session, building_id)
    if record is None:
        raise BuildingNotFoundError
    return building_response(record)


def _apply_building_values(
    building: Building,
    values: dict,
) -> None:
    for field, value in values.items():
        setattr(building, field, value)
    if "number" in values:
        building.normalized_number = normalize_address_value(values["number"])
    if "corpus" in values:
        building.normalized_corpus = normalize_address_value(values["corpus"] or "")
    if "structure" in values:
        building.normalized_structure = normalize_address_value(
            values["structure"] or ""
        )


async def create_building(
    session: AsyncSession,
    data: BuildingCreate,
) -> BuildingResponse:
    await validate_building_parent(session, data.address_object_id)
    building = Building(
        address_object_id=data.address_object_id,
        number=data.number,
        normalized_number=normalize_address_value(data.number),
        corpus=data.corpus,
        normalized_corpus=normalize_address_value(data.corpus or ""),
        structure=data.structure,
        normalized_structure=normalize_address_value(data.structure or ""),
        latitude=data.latitude,
        longitude=data.longitude,
    )
    session.add(building)
    try:
        await session.commit()
        await session.refresh(building)
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateBuildingError from exc
    record = await get_building_record(session, building.id)
    assert record is not None
    return building_response(record)


async def update_building(
    session: AsyncSession,
    building_id: int,
    data: BuildingUpdate,
) -> BuildingResponse:
    building = await get_building(session, building_id)
    if building is None:
        raise BuildingNotFoundError
    values = data.model_dump(exclude_unset=True)
    address_object_id = values.get(
        "address_object_id",
        building.address_object_id,
    )
    await validate_building_parent(session, address_object_id)
    _apply_building_values(building, values)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateBuildingError from exc
    record = await get_building_record(session, building_id)
    assert record is not None
    return building_response(record)


async def delete_building(
    session: AsyncSession,
    building_id: int,
) -> None:
    building = await get_building(session, building_id)
    if building is None:
        raise BuildingNotFoundError
    if await building_has_entrances_or_locations(session, building_id):
        raise BuildingNotEmptyError
    await session.delete(building)
    await session.commit()


async def get_entrances(
    session: AsyncSession,
    building_id: int,
) -> list[Entrance]:
    if await get_building(session, building_id) is None:
        raise BuildingNotFoundError
    return await list_entrances(session, building_id)


async def create_entrance(
    session: AsyncSession,
    building_id: int,
    data: EntranceCreate,
) -> Entrance:
    if await get_building(session, building_id) is None:
        raise BuildingNotFoundError
    entrance = Entrance(
        building_id=building_id,
        number=data.number,
        normalized_number=normalize_address_value(data.number),
    )
    session.add(entrance)
    try:
        await session.commit()
        await session.refresh(entrance)
        return entrance
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateEntranceError from exc


async def update_entrance(
    session: AsyncSession,
    entrance_id: int,
    data: EntranceUpdate,
) -> Entrance:
    entrance = await get_entrance(session, entrance_id)
    if entrance is None:
        raise EntranceNotFoundError
    entrance.number = data.number
    entrance.normalized_number = normalize_address_value(data.number)
    try:
        await session.commit()
        await session.refresh(entrance)
        return entrance
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateEntranceError from exc


async def delete_entrance(
    session: AsyncSession,
    entrance_id: int,
) -> None:
    entrance = await get_entrance(session, entrance_id)
    if entrance is None:
        raise EntranceNotFoundError
    if await entrance_has_locations(session, entrance_id):
        raise EntranceNotEmptyError
    await session.delete(entrance)
    await session.commit()


async def get_locations(
    session: AsyncSession,
    *,
    company_id: int,
    building_id: int,
) -> list[Location]:
    if await get_building(session, building_id) is None:
        raise BuildingNotFoundError
    return await list_locations(
        session,
        company_id=company_id,
        building_id=building_id,
    )


async def _validate_location_links(
    session: AsyncSession,
    *,
    building_id: int,
    entrance_id: int | None,
) -> None:
    if await get_building(session, building_id) is None:
        raise BuildingNotFoundError
    if entrance_id is None:
        return
    entrance = await get_entrance(session, entrance_id)
    if entrance is None:
        raise EntranceNotFoundError
    if entrance.building_id != building_id:
        raise LocationEntranceMismatchError


async def create_location(
    session: AsyncSession,
    *,
    company_id: int,
    data: LocationCreate,
) -> Location:
    await _validate_location_links(
        session,
        building_id=data.building_id,
        entrance_id=data.entrance_id,
    )
    location = Location(company_id=company_id, **data.model_dump())
    session.add(location)
    await session.commit()
    await session.refresh(location)
    return location


async def update_location(
    session: AsyncSession,
    *,
    company_id: int,
    location_id: int,
    data: LocationUpdate,
) -> Location:
    location = await get_location(
        session,
        company_id=company_id,
        location_id=location_id,
    )
    if location is None:
        raise LocationNotFoundError
    values = data.model_dump(exclude_unset=True)
    building_id = values.get("building_id", location.building_id)
    entrance_id = values.get("entrance_id", location.entrance_id)
    await _validate_location_links(
        session,
        building_id=building_id,
        entrance_id=entrance_id,
    )
    for field, value in values.items():
        setattr(location, field, value)
    await session.commit()
    await session.refresh(location)
    return location


async def delete_location(
    session: AsyncSession,
    *,
    company_id: int,
    location_id: int,
) -> None:
    location = await get_location(
        session,
        company_id=company_id,
        location_id=location_id,
    )
    if location is None:
        raise LocationNotFoundError
    if await location_has_equipment(session, location_id):
        raise LocationNotEmptyError
    await session.delete(location)
    await session.commit()


async def search_addresses(
    session: AsyncSession,
    *,
    query: str,
    limit: int,
    offset: int,
) -> AddressSearchResponse:
    normalized = normalize_address_value(query)
    tokens = [token for token in normalized.split(" ") if token]
    if not tokens:
        return AddressSearchResponse(
            items=[], total=0, limit=limit, offset=offset
        )
    records, total = await search_building_records(
        session,
        tokens=tokens,
        limit=limit,
        offset=offset,
    )
    return AddressSearchResponse(
        items=[building_response(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )
