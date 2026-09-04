from sqlalchemy.ext.asyncio import AsyncSession

from models.organizational_units import (
    OrganizationalUnit,
)

from repositories.company import (
    get_company_by_id,
)

from repositories.organizational_units import (
    create_organizational_unit,
    get_company_organizational_units,
    get_organizational_unit_by_id,
)

from schemas.organizational_units import (
    OrganizationalUnitCreate,
    OrganizationalUnitUpdate,
)


class CompanyNotFoundError(Exception):
    pass


class OrganizationalUnitNotFoundError(Exception):
    pass


class ParentOrganizationalUnitNotFoundError(Exception):
    pass


class ParentOrganizationalUnitWrongCompanyError(
    Exception
):
    pass


class OrganizationalUnitHierarchyCycleError(
    Exception
):
    pass


async def _validate_parent_change(
    *,
    session: AsyncSession,
    unit: OrganizationalUnit,
    parent_id: int | None,
) -> None:
    if parent_id is None:
        return

    if parent_id == unit.id:
        raise OrganizationalUnitHierarchyCycleError

    parent = await get_organizational_unit_by_id(
        session,
        parent_id,
    )

    if parent is None:
        raise ParentOrganizationalUnitNotFoundError

    if parent.company_id != unit.company_id:
        raise ParentOrganizationalUnitWrongCompanyError

    visited: set[int] = set()

    current: OrganizationalUnit | None = parent

    while current is not None:
        if current.id == unit.id:
            raise OrganizationalUnitHierarchyCycleError

        if current.id in visited:
            raise OrganizationalUnitHierarchyCycleError

        visited.add(current.id)

        if current.parent_id is None:
            break

        current = await get_organizational_unit_by_id(
            session,
            current.parent_id,
        )


async def list_organizational_units(
    session: AsyncSession,
    company_id: int,
) -> list[OrganizationalUnit]:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    return await get_company_organizational_units(
        session,
        company_id,
    )


async def create_new_organizational_unit(
    session: AsyncSession,
    company_id: int,
    data: OrganizationalUnitCreate,
) -> OrganizationalUnit:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    if data.parent_id is not None:
        parent = await get_organizational_unit_by_id(
            session,
            data.parent_id,
        )

        if parent is None:
            raise ParentOrganizationalUnitNotFoundError

        if parent.company_id != company_id:
            raise ParentOrganizationalUnitWrongCompanyError

    unit = await create_organizational_unit(
        session,
        company_id=company_id,
        parent_id=data.parent_id,
        name=data.name,
        type=data.type,
    )

    await session.commit()
    await session.refresh(unit)

    return unit


async def get_organizational_unit(
    session: AsyncSession,
    *,
    company_id: int,
    unit_id: int,
) -> OrganizationalUnit:
    unit = await get_organizational_unit_by_id(
        session,
        unit_id,
    )

    if (
        unit is None
        or unit.company_id != company_id
    ):
        raise OrganizationalUnitNotFoundError

    return unit


async def update_organizational_unit(
    session: AsyncSession,
    *,
    company_id: int,
    unit_id: int,
    data: OrganizationalUnitUpdate,
) -> OrganizationalUnit:
    unit = await get_organizational_unit(
        session,
        company_id=company_id,
        unit_id=unit_id,
    )

    update_data = data.model_dump(
        exclude_unset=True,
    )

    if "parent_id" in update_data:
        await _validate_parent_change(
            session=session,
            unit=unit,
            parent_id=update_data["parent_id"],
        )

    for field, value in update_data.items():
        setattr(
            unit,
            field,
            value,
        )

    await session.commit()
    await session.refresh(unit)

    return unit