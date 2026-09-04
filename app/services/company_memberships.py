from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.company import (
    Company,
)

from models.company_memberships import (
    CompanyMembership,
)

from repositories.company import (
    get_company_by_id,
)

from repositories.company_memberships import (
    create_company_membership,
    get_company_membership_by_id,
    get_company_membership_by_user,
    get_company_memberships,
    get_available_companies_for_user,
)

from repositories.users import (
    get_user_by_id,
)


class CompanyNotFoundError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class CompanyMembershipNotFoundError(Exception):
    pass


class CompanyMembershipAlreadyExistsError(Exception):
    pass


async def list_company_memberships(
    session: AsyncSession,
    company_id: int,
) -> list[CompanyMembership]:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    return await get_company_memberships(
        session,
        company_id,
    )


async def add_user_to_company(
    session: AsyncSession,
    *,
    company_id: int,
    user_id: int,
) -> CompanyMembership:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    user = await get_user_by_id(
        session=session,
        user_id=user_id,
    )

    if user is None:
        raise UserNotFoundError

    existing_membership = (
        await get_company_membership_by_user(
            session,
            company_id=company_id,
            user_id=user_id,
        )
    )

    if existing_membership is not None:
        raise CompanyMembershipAlreadyExistsError

    try:
        membership = await create_company_membership(
            session,
            user_id=user_id,
            company_id=company_id,
        )

        await session.commit()
        await session.refresh(membership)

        return membership

    except IntegrityError:
        await session.rollback()

        raise CompanyMembershipAlreadyExistsError


async def get_company_membership(
    session: AsyncSession,
    *,
    company_id: int,
    membership_id: int,
) -> CompanyMembership:
    membership = await get_company_membership_by_id(
        session,
        membership_id,
    )

    if (
        membership is None
        or membership.company_id != company_id
    ):
        raise CompanyMembershipNotFoundError

    return membership


async def update_company_membership(
    session: AsyncSession,
    *,
    company_id: int,
    membership_id: int,
    is_active: bool,
) -> CompanyMembership:
    membership = await get_company_membership(
        session,
        company_id=company_id,
        membership_id=membership_id,
    )

    membership.is_active = is_active

    await session.commit()
    await session.refresh(membership)

    return membership


async def list_available_companies_for_user(
    session: AsyncSession,
    user_id: int,
) -> list[Company]:
    return await get_available_companies_for_user(
        session,
        user_id,
    )