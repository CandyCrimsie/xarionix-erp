from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.roles import Role


async def get_role_by_id(
    session: AsyncSession,
    role_id: int,
) -> Role | None:
    return await session.get(
        Role,
        role_id,
    )


async def get_role_by_name(
    session: AsyncSession,
    *,
    company_id: int,
    name: str,
) -> Role | None:
    stmt = (
        select(Role)
        .where(
            Role.company_id == company_id,
            Role.name == name,
        )
    )

    result = await session.execute(stmt)

    return result.scalar_one_or_none()


async def get_company_roles(
    session: AsyncSession,
    company_id: int,
) -> list[Role]:
    stmt = (
        select(Role)
        .where(
            Role.company_id == company_id
        )
        .order_by(
            Role.name.asc(),
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def create_role(
    session: AsyncSession,
    *,
    company_id: int,
    name: str,
    description: str | None,
    is_system: bool = False,
) -> Role:
    role = Role(
        company_id=company_id,
        name=name,
        description=description,
        is_system=is_system,
    )

    session.add(role)

    await session.flush()

    return role


async def get_roles_by_ids(
    session: AsyncSession,
    role_ids: list[int],
) -> list[Role]:
    if not role_ids:
        return []

    stmt = (
        select(Role)
        .where(
            Role.id.in_(role_ids)
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )