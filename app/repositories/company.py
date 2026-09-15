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


async def get_company_subtree(
    session: AsyncSession,
    root_company_id: int,
) -> list[Company]:
    company_tree = (
        select(
            Company.id
        )
        .where(
            Company.id
            == root_company_id
        )
        .cte(
            name="company_tree",
            recursive=True,
        )
    )


    company_tree = (
        company_tree.union_all(
            select(
                Company.id
            )
            .where(
                Company.parent_id
                == company_tree.c.id
            )
        )
    )


    stmt = (
        select(
            Company
        )
        .join(
            company_tree,
            company_tree.c.id
            == Company.id,
        )
        .order_by(
            Company.name.asc(),
            Company.id.asc(),
        )
    )


    result = await session.execute(
        stmt
    )


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