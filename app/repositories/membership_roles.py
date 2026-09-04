from sqlalchemy import (
    delete,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from models.membership_roles import MembershipRole
from models.roles import Role


async def get_membership_roles(
    session: AsyncSession,
    company_membership_id: int,
) -> list[Role]:
    stmt = (
        select(Role)
        .join(
            MembershipRole,
            MembershipRole.role_id == Role.id,
        )
        .where(
            MembershipRole.company_membership_id
            == company_membership_id
        )
        .order_by(
            Role.name.asc(),
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def delete_membership_roles(
    session: AsyncSession,
    company_membership_id: int,
) -> None:
    stmt = (
        delete(MembershipRole)
        .where(
            MembershipRole.company_membership_id
            == company_membership_id
        )
    )

    await session.execute(stmt)


async def create_membership_roles(
    session: AsyncSession,
    *,
    company_membership_id: int,
    role_ids: list[int],
) -> None:
    if not role_ids:
        return

    session.add_all(
        [
            MembershipRole(
                company_membership_id=company_membership_id,
                role_id=role_id,
            )
            for role_id in role_ids
        ]
    )

    await session.flush()