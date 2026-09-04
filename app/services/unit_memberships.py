from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.unit_memberships import UnitMembership

from repositories.company_memberships import (
    get_company_membership_by_id,
)

from repositories.organizational_units import (
    get_organizational_unit_by_id,
)

from repositories.unit_memberships import (
    clear_primary_unit_memberships,
    create_unit_membership,
    get_membership_units,
    get_unit_membership,
    get_unit_membership_by_id,
)


class CompanyMembershipNotFoundError(Exception):
    pass


class OrganizationalUnitNotFoundError(Exception):
    pass


class OrganizationalUnitWrongCompanyError(Exception):
    pass


class UnitMembershipNotFoundError(Exception):
    pass


class UnitMembershipAlreadyExistsError(Exception):
    pass


async def list_membership_units(
    session: AsyncSession,
    company_membership_id: int,
) -> list[UnitMembership]:
    membership = await get_company_membership_by_id(
        session,
        company_membership_id,
    )

    if membership is None:
        raise CompanyMembershipNotFoundError

    return await get_membership_units(
        session,
        company_membership_id,
    )


async def add_membership_to_unit(
    session: AsyncSession,
    *,
    company_membership_id: int,
    unit_id: int,
    is_primary: bool,
) -> UnitMembership:
    company_membership = await get_company_membership_by_id(
        session,
        company_membership_id,
    )

    if company_membership is None:
        raise CompanyMembershipNotFoundError

    unit = await get_organizational_unit_by_id(
        session,
        unit_id,
    )

    if unit is None:
        raise OrganizationalUnitNotFoundError

    if unit.company_id != company_membership.company_id:
        raise OrganizationalUnitWrongCompanyError

    existing = await get_unit_membership(
        session,
        company_membership_id=company_membership_id,
        unit_id=unit_id,
    )

    if existing is not None:
        raise UnitMembershipAlreadyExistsError

    try:
        if is_primary:
            await clear_primary_unit_memberships(
                session,
                company_membership_id,
            )

        unit_membership = await create_unit_membership(
            session,
            company_membership_id=company_membership_id,
            unit_id=unit_id,
            is_primary=is_primary,
        )

        await session.commit()
        await session.refresh(unit_membership)

        return unit_membership

    except IntegrityError:
        await session.rollback()

        raise UnitMembershipAlreadyExistsError


async def get_membership_unit(
    session: AsyncSession,
    *,
    company_membership_id: int,
    unit_membership_id: int,
) -> UnitMembership:
    unit_membership = await get_unit_membership_by_id(
        session,
        unit_membership_id,
    )

    if (
        unit_membership is None
        or unit_membership.company_membership_id
        != company_membership_id
    ):
        raise UnitMembershipNotFoundError

    return unit_membership


async def update_membership_unit(
    session: AsyncSession,
    *,
    company_membership_id: int,
    unit_membership_id: int,
    is_primary: bool | None,
    is_active: bool | None,
) -> UnitMembership:
    unit_membership = await get_membership_unit(
        session,
        company_membership_id=company_membership_id,
        unit_membership_id=unit_membership_id,
    )

    if is_primary is True:
        await clear_primary_unit_memberships(
            session,
            company_membership_id,
        )

        unit_membership.is_primary = True

    elif is_primary is False:
        unit_membership.is_primary = False

    if is_active is False:
        unit_membership.is_active = False
        unit_membership.is_primary = False

    elif is_active is True:
        unit_membership.is_active = True

    await session.commit()
    await session.refresh(unit_membership)

    return unit_membership