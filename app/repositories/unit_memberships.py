from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.unit_memberships import UnitMembership


async def get_unit_membership_by_id(
    session: AsyncSession,
    unit_membership_id: int,
) -> UnitMembership | None:
    return await session.get(
        UnitMembership,
        unit_membership_id,
    )


async def get_unit_membership(
    session: AsyncSession,
    *,
    company_membership_id: int,
    unit_id: int,
) -> UnitMembership | None:
    stmt = (
        select(UnitMembership)
        .where(
            UnitMembership.company_membership_id
            == company_membership_id,
            UnitMembership.unit_id
            == unit_id,
        )
    )

    result = await session.execute(stmt)

    return result.scalar_one_or_none()


async def get_membership_units(
    session: AsyncSession,
    company_membership_id: int,
) -> list[UnitMembership]:
    stmt = (
        select(UnitMembership)
        .where(
            UnitMembership.company_membership_id
            == company_membership_id
        )
        .order_by(
            UnitMembership.id.asc()
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def create_unit_membership(
    session: AsyncSession,
    *,
    company_membership_id: int,
    unit_id: int,
    is_primary: bool,
) -> UnitMembership:
    unit_membership = UnitMembership(
        company_membership_id=company_membership_id,
        unit_id=unit_id,
        is_primary=is_primary,
    )

    session.add(unit_membership)

    await session.flush()

    return unit_membership


async def clear_primary_unit_memberships(
    session: AsyncSession,
    company_membership_id: int,
) -> None:
    stmt = (
        update(UnitMembership)
        .where(
            UnitMembership.company_membership_id
            == company_membership_id,
            UnitMembership.is_primary.is_(True),
        )
        .values(
            is_primary=False,
        )
    )

    await session.execute(stmt)