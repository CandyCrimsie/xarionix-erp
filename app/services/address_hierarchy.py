from sqlalchemy.ext.asyncio import AsyncSession

from models.address_types import (
    AddressType,
    AddressTypeCategory,
)
from repositories.addresses import (
    get_address_object_descendant_ids,
    get_address_object_record,
    list_address_object_records,
    list_building_records,
)


class AddressHierarchyError(Exception):
    pass


class AddressHierarchyCycleError(AddressHierarchyError):
    pass


class InvalidAddressHierarchyTransitionError(AddressHierarchyError):
    pass


class AddressParentNotFoundError(AddressHierarchyError):
    pass


ROOT_CATEGORIES = frozenset({
    AddressTypeCategory.COUNTRY,
    AddressTypeCategory.REGION,
    AddressTypeCategory.LOCALITY,
})


# Known system types use explicit rules. This prevents a city, settlement or
# village from silently accepting another ordinary locality just because both
# share the broad ``locality`` category.
SYSTEM_TYPE_CHILD_CATEGORIES: dict[
    str,
    frozenset[AddressTypeCategory],
] = {
    "country": frozenset({
        AddressTypeCategory.REGION,
        AddressTypeCategory.LOCALITY,
    }),
    "region": frozenset({
        AddressTypeCategory.AREA,
        AddressTypeCategory.LOCALITY,
    }),
    "city": frozenset({
        AddressTypeCategory.AREA,
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "settlement": frozenset({
        AddressTypeCategory.AREA,
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "village": frozenset({
        AddressTypeCategory.AREA,
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "district": frozenset({
        AddressTypeCategory.AREA,
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "municipal_district": frozenset({
        AddressTypeCategory.AREA,
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "microdistrict": frozenset({
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "quarter": frozenset({
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "snt_territory": frozenset({
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "tsn_territory": frozenset({
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "dnt_territory": frozenset({
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "industrial_zone": frozenset({
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "territory": frozenset({
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    "street": frozenset(),
    "avenue": frozenset(),
    "lane": frozenset(),
}


# User-defined types still need predictable semantics. Category fallback is
# deliberately stricter than the historical rules: locality nesting is never
# implicit, and only the dedicated territory category may contain buildings.
CUSTOM_TYPE_CHILD_CATEGORIES: dict[
    AddressTypeCategory,
    frozenset[AddressTypeCategory],
] = {
    AddressTypeCategory.COUNTRY: frozenset({
        AddressTypeCategory.REGION,
        AddressTypeCategory.LOCALITY,
    }),
    AddressTypeCategory.REGION: frozenset({
        AddressTypeCategory.AREA,
        AddressTypeCategory.LOCALITY,
    }),
    AddressTypeCategory.LOCALITY: frozenset({
        AddressTypeCategory.AREA,
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    AddressTypeCategory.AREA: frozenset({
        AddressTypeCategory.AREA,
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    AddressTypeCategory.TERRITORY: frozenset({
        AddressTypeCategory.TERRITORY,
        AddressTypeCategory.THOROUGHFARE,
    }),
    AddressTypeCategory.THOROUGHFARE: frozenset(),
}


BUILDING_PARENT_CATEGORIES = frozenset({
    AddressTypeCategory.TERRITORY,
    AddressTypeCategory.THOROUGHFARE,
})


def allowed_child_categories(
    parent_type: AddressType,
) -> frozenset[AddressTypeCategory]:
    return SYSTEM_TYPE_CHILD_CATEGORIES.get(
        parent_type.code,
        CUSTOM_TYPE_CHILD_CATEGORIES[parent_type.category],
    )


def address_type_allows_buildings(address_type: AddressType) -> bool:
    return address_type.category in BUILDING_PARENT_CATEGORIES


def _validate_transition(
    parent_type: AddressType | None,
    child_type: AddressType,
) -> None:
    if parent_type is None:
        if child_type.category not in ROOT_CATEGORIES:
            raise InvalidAddressHierarchyTransitionError
        return

    if child_type.category not in allowed_child_categories(parent_type):
        raise InvalidAddressHierarchyTransitionError


async def validate_address_object_hierarchy(
    session: AsyncSession,
    *,
    address_type: AddressType,
    parent_id: int | None,
    moving_object_id: int | None = None,
) -> None:
    parent_type: AddressType | None = None
    if parent_id is not None:
        if parent_id == moving_object_id:
            raise AddressHierarchyCycleError

        parent_record = await get_address_object_record(session, parent_id)
        if parent_record is None:
            raise AddressParentNotFoundError

        if moving_object_id is not None:
            descendants = await get_address_object_descendant_ids(
                session,
                moving_object_id,
            )
            if parent_id in descendants:
                raise AddressHierarchyCycleError

        parent_type = parent_record.address_type

    _validate_transition(parent_type, address_type)

    if moving_object_id is None:
        return

    for child_record in await list_address_object_records(
        session,
        parent_id=moving_object_id,
    ):
        _validate_transition(
            address_type,
            child_record.address_type,
        )

    if (
        not address_type_allows_buildings(address_type)
        and await list_building_records(
            session,
            address_object_id=moving_object_id,
        )
    ):
        raise InvalidAddressHierarchyTransitionError


async def validate_building_parent(
    session: AsyncSession,
    address_object_id: int,
) -> None:
    record = await get_address_object_record(session, address_object_id)
    if record is None:
        raise AddressParentNotFoundError
    if not address_type_allows_buildings(record.address_type):
        raise InvalidAddressHierarchyTransitionError
