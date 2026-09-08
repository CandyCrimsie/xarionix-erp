from sqlalchemy import (
    delete,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from models.role_delegations import (
    RoleDelegation,
)


async def get_assignable_role_ids(
    session: AsyncSession,
    *,
    manager_role_ids: list[int],
) -> set[int]:
    if not manager_role_ids:
        return set()

    stmt = (
        select(
            RoleDelegation.assignable_role_id
        )
        .where(
            RoleDelegation.manager_role_id.in_(
                manager_role_ids
            )
        )
    )

    result = await session.execute(
        stmt
    )

    return set(
        result.scalars().all()
    )


async def get_role_delegations(
    session: AsyncSession,
    *,
    manager_role_id: int,
) -> list[RoleDelegation]:
    stmt = (
        select(RoleDelegation)
        .where(
            RoleDelegation.manager_role_id
            == manager_role_id
        )
        .order_by(
            RoleDelegation.assignable_role_id.asc()
        )
    )

    result = await session.execute(
        stmt
    )

    return list(
        result.scalars().all()
    )


async def replace_role_delegations(
    session: AsyncSession,
    *,
    manager_role_id: int,
    assignable_role_ids: list[int],
) -> None:
    await session.execute(
        delete(RoleDelegation).where(
            RoleDelegation.manager_role_id
            == manager_role_id
        )
    )

    if not assignable_role_ids:
        return

    session.add_all(
        [
            RoleDelegation(
                manager_role_id=manager_role_id,
                assignable_role_id=role_id,
            )
            for role_id in assignable_role_ids
        ]
    )

    await session.flush()