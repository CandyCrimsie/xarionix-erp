from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.organizational_units import (
    OrganizationalUnit,
    OrganizationalUnitType,
)


async def get_organizational_unit_by_id(
    session: AsyncSession,
    unit_id: int,
) -> OrganizationalUnit | None:
    return await session.get(
        OrganizationalUnit,
        unit_id,
    )


async def get_company_organizational_units(
    session: AsyncSession,
    company_id: int,
) -> list[OrganizationalUnit]:
    stmt = (
        select(OrganizationalUnit)
        .where(
            OrganizationalUnit.company_id
            == company_id
        )
        .order_by(
            OrganizationalUnit.name.asc(),
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def create_organizational_unit(
    session: AsyncSession,
    *,
    company_id: int,
    parent_id: int | None,
    name: str,
    type: OrganizationalUnitType,
) -> OrganizationalUnit:
    unit = OrganizationalUnit(
        company_id=company_id,
        parent_id=parent_id,
        name=name,
        type=type,
    )

    session.add(unit)

    await session.flush()

    return unit