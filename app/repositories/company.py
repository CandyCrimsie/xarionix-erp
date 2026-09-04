from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.company import Company


async def get_company_by_id(
    session: AsyncSession,
    company_id: int,
) -> Company | None:
    return await session.get(
        Company,
        company_id,
    )


async def get_companies(
    session: AsyncSession,
) -> list[Company]:
    stmt = (
        select(Company)
        .order_by(
            Company.name.asc(),
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def create_company(
    session: AsyncSession,
    *,
    name: str,
    short_name: str | None,
    parent_id: int | None,
) -> Company:
    company = Company(
        name=name,
        short_name=short_name,
        parent_id=parent_id,
    )

    session.add(company)

    await session.flush()

    return company