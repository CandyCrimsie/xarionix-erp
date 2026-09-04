from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.permissions import Permission


async def get_permission_by_id(
    session: AsyncSession,
    permission_id: int,
) -> Permission | None:
    return await session.get(
        Permission,
        permission_id,
    )


async def get_permission_by_code(
    session: AsyncSession,
    code: str,
) -> Permission | None:
    stmt = (
        select(Permission)
        .where(
            Permission.code == code,
        )
    )

    result = await session.execute(stmt)

    return result.scalar_one_or_none()


async def get_permissions(
    session: AsyncSession,
    *,
    active_only: bool = True,
) -> list[Permission]:
    stmt = select(Permission)

    if active_only:
        stmt = stmt.where(
            Permission.is_active.is_(True)
        )

    stmt = stmt.order_by(
        Permission.module.asc(),
        Permission.code.asc(),
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def get_all_permissions(
    session: AsyncSession,
) -> list[Permission]:
    stmt = select(Permission)

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def create_permission(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    module: str,
    description: str | None,
) -> Permission:
    permission = Permission(
        code=code,
        name=name,
        module=module,
        description=description,
    )

    session.add(permission)

    await session.flush()

    return permission


async def get_permissions_by_ids(
    session: AsyncSession,
    permission_ids: list[int],
) -> list[Permission]:
    if not permission_ids:
        return []

    stmt = (
        select(Permission)
        .where(
            Permission.id.in_(
                permission_ids
            )
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )