from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.company import Company
from models.company_memberships import (
    CompanyMembership,
)


async def get_company_membership_by_id(
    session: AsyncSession,
    membership_id: int,
) -> CompanyMembership | None:
    return await session.get(
        CompanyMembership,
        membership_id,
    )


async def get_company_membership_by_user(
    session: AsyncSession,
    *,
    company_id: int,
    user_id: int,
) -> CompanyMembership | None:
    stmt = (
        select(CompanyMembership)
        .where(
            CompanyMembership.company_id
            == company_id,
            CompanyMembership.user_id
            == user_id,
        )
    )

    result = await session.execute(stmt)

    return result.scalar_one_or_none()


async def get_company_memberships(
    session: AsyncSession,
    company_id: int,
) -> list[CompanyMembership]:
    stmt = (
        select(CompanyMembership)
        .where(
            CompanyMembership.company_id
            == company_id
        )
        .order_by(
            CompanyMembership.id.asc()
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def get_user_company_memberships(
    session: AsyncSession,
    user_id: int,
) -> list[CompanyMembership]:
    stmt = (
        select(CompanyMembership)
        .where(
            CompanyMembership.user_id
            == user_id
        )
        .order_by(
            CompanyMembership.id.asc()
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def create_company_membership(
    session: AsyncSession,
    *,
    user_id: int,
    company_id: int,
) -> CompanyMembership:
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
    )

    session.add(membership)

    await session.flush()

    return membership


async def get_available_companies_for_user(
    session: AsyncSession,
    user_id: int,
) -> list[Company]:
    stmt = (
        select(Company)
        .join(
            CompanyMembership,
            CompanyMembership.company_id == Company.id,
        )
        .where(
            CompanyMembership.user_id == user_id,
            CompanyMembership.is_active.is_(True),
            Company.is_active.is_(True),
        )
        .order_by(
            Company.name.asc(),
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )