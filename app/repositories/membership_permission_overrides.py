from sqlalchemy import (
    delete,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.effects import (
    PermissionOverrideEffect,
)
from core.permissions.scopes import (
    PermissionScope,
)

from models.membership_permission_overrides import (
    MembershipPermissionOverride,
)


async def get_membership_permission_overrides(
    session: AsyncSession,
    *,
    company_membership_id: int,
) -> list[MembershipPermissionOverride]:
    stmt = (
        select(MembershipPermissionOverride)
        .where(
            MembershipPermissionOverride.company_membership_id
            == company_membership_id
        )
        .order_by(
            MembershipPermissionOverride.permission_id.asc()
        )
    )

    result = await session.execute(
        stmt
    )

    return list(
        result.scalars().all()
    )


async def get_membership_permission_override(
    session: AsyncSession,
    *,
    company_membership_id: int,
    permission_id: int,
) -> MembershipPermissionOverride | None:
    stmt = (
        select(MembershipPermissionOverride)
        .where(
            MembershipPermissionOverride.company_membership_id
            == company_membership_id,

            MembershipPermissionOverride.permission_id
            == permission_id,
        )
    )

    result = await session.execute(
        stmt
    )

    return result.scalar_one_or_none()


async def create_membership_permission_override(
    session: AsyncSession,
    *,
    company_membership_id: int,
    permission_id: int,
    effect: PermissionOverrideEffect,
    scope: PermissionScope | None,
) -> MembershipPermissionOverride:
    permission_override = (
        MembershipPermissionOverride(
            company_membership_id=(
                company_membership_id
            ),
            permission_id=permission_id,
            effect=effect,
            scope=scope,
        )
    )

    session.add(
        permission_override
    )

    await session.flush()

    return permission_override


async def update_membership_permission_override(
    session: AsyncSession,
    *,
    permission_override: MembershipPermissionOverride,
    effect: PermissionOverrideEffect,
    scope: PermissionScope | None,
) -> MembershipPermissionOverride:
    permission_override.effect = effect
    permission_override.scope = scope

    await session.flush()

    return permission_override


async def delete_membership_permission_override(
    session: AsyncSession,
    *,
    company_membership_id: int,
    permission_id: int,
) -> None:
    stmt = (
        delete(MembershipPermissionOverride)
        .where(
            MembershipPermissionOverride.company_membership_id
            == company_membership_id,

            MembershipPermissionOverride.permission_id
            == permission_id,
        )
    )

    await session.execute(
        stmt
    )