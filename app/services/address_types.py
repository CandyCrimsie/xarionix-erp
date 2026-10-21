import re

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


_CYRILLIC_TRANSLITERATION = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
})


def address_type_code_base(name: str, category: str) -> str:
    transliterated = name.casefold().translate(_CYRILLIC_TRANSLITERATION)
    slug = re.sub(r"[^a-z0-9]+", "_", transliterated).strip("_")
    if not slug:
        slug = category
    prefix = f"custom_{category}_"
    return f"{prefix}{slug}"[:50].rstrip("_")


async def _next_generated_code(
    session: AsyncSession,
    *,
    name: str,
    category: str,
) -> str:
    base = address_type_code_base(name, category)
    candidate = base
    suffix = 2
    while await get_address_type_by_code(session, candidate) is not None:
        suffix_text = f"_{suffix}"
        candidate = f"{base[:50 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


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
    generated_code = data.code is None
    for _attempt in range(100):
        code = data.code or await _next_generated_code(
            session,
            name=data.name,
            category=data.category.value,
        )
        address_type = AddressType(
            code=code,
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
            if not generated_code:
                raise AddressTypeDuplicateError from exc

    raise AddressTypeDuplicateError


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
