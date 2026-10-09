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


ROOT_CATEGORIES = {
    AddressTypeCategory.COUNTRY,
    AddressTypeCategory.REGION,
    AddressTypeCategory.LOCALITY,
}


ALLOWED_CHILD_CATEGORIES = {
    AddressTypeCategory.COUNTRY: {
        AddressTypeCategory.REGION,
        AddressTypeCategory.LOCALITY,
    },
    AddressTypeCategory.REGION: {
        AddressTypeCategory.AREA,
        AddressTypeCategory.LOCALITY,
    },
    AddressTypeCategory.LOCALITY: {
        AddressTypeCategory.AREA,
        AddressTypeCategory.LOCALITY,
        AddressTypeCategory.THOROUGHFARE,
    },
    AddressTypeCategory.AREA: {
        AddressTypeCategory.AREA,
        AddressTypeCategory.LOCALITY,
        AddressTypeCategory.THOROUGHFARE,
    },
    AddressTypeCategory.THOROUGHFARE: set(),
}


def _validate_transition(
    parent_category: AddressTypeCategory | None,
    child_category: AddressTypeCategory,
) -> None:
    if parent_category is None:
        if child_category not in ROOT_CATEGORIES:
            raise InvalidAddressHierarchyTransitionError
        return

    if child_category not in ALLOWED_CHILD_CATEGORIES[parent_category]:
        raise InvalidAddressHierarchyTransitionError


async def validate_address_object_hierarchy(
    session: AsyncSession,
    *,
    address_type: AddressType,
    parent_id: int | None,
    moving_object_id: int | None = None,
) -> None:
    parent_category: AddressTypeCategory | None = None
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

        parent_category = parent_record.address_type.category

    _validate_transition(parent_category, address_type.category)

    if moving_object_id is None:
        return

    for child_record in await list_address_object_records(
        session,
        parent_id=moving_object_id,
    ):
        _validate_transition(
            address_type.category,
            child_record.address_type.category,
        )

    if (
        address_type.category != AddressTypeCategory.THOROUGHFARE
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
    if record.address_type.category != AddressTypeCategory.THOROUGHFARE:
        raise InvalidAddressHierarchyTransitionError
