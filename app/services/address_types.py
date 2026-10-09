from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.address_types import SYSTEM_ADDRESS_TYPES
from models.address_types import AddressType
from repositories.addresses import (
    address_type_is_used,
    get_address_type,
    get_address_type_by_code,
    list_address_types,
)
from schemas.addresses import (
    AddressTypeCreate,
    AddressTypeUpdate,
)


class AddressTypeNotFoundError(Exception):
    pass


class AddressTypeDuplicateError(Exception):
    pass


class SystemAddressTypeProtectedError(Exception):
    pass


class AddressTypeInUseError(Exception):
    pass


async def sync_system_address_types(
    session: AsyncSession,
) -> None:
    for definition in SYSTEM_ADDRESS_TYPES:
        existing = await get_address_type_by_code(
            session,
            definition.code,
        )
        if existing is not None:
            continue

        session.add(
            AddressType(
                code=definition.code,
                category=definition.category,
                name=definition.name,
                short_name=definition.short_name,
                sort_order=definition.sort_order,
                is_system=True,
            )
        )

    await session.commit()


async def get_address_types(
    session: AsyncSession,
) -> list[AddressType]:
    return await list_address_types(session)


async def create_address_type(
    session: AsyncSession,
    data: AddressTypeCreate,
) -> AddressType:
    address_type = AddressType(
        code=data.code,
        category=data.category,
        name=data.name,
        short_name=data.short_name,
        sort_order=data.sort_order,
        is_system=False,
    )
    session.add(address_type)
    try:
        await session.commit()
        await session.refresh(address_type)
        return address_type
    except IntegrityError as exc:
        await session.rollback()
        raise AddressTypeDuplicateError from exc


async def update_address_type(
    session: AsyncSession,
    address_type_id: int,
    data: AddressTypeUpdate,
) -> AddressType:
    address_type = await get_address_type(session, address_type_id)
    if address_type is None:
        raise AddressTypeNotFoundError
    if address_type.is_system:
        raise SystemAddressTypeProtectedError

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(address_type, field, value)

    await session.commit()
    await session.refresh(address_type)
    return address_type


async def delete_address_type(
    session: AsyncSession,
    address_type_id: int,
) -> None:
    address_type = await get_address_type(session, address_type_id)
    if address_type is None:
        raise AddressTypeNotFoundError
    if address_type.is_system:
        raise SystemAddressTypeProtectedError
    if await address_type_is_used(session, address_type_id):
        raise AddressTypeInUseError

    await session.delete(address_type)
    await session.commit()
