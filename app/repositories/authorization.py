from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.company_memberships import CompanyMembership
from models.membership_roles import MembershipRole
from models.permissions import Permission
from models.role_permissions import RolePermission
from models.roles import Role


async def get_effective_permission_codes(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
) -> set[str]:
    stmt = (
        select(Permission.code)
        .join(
            RolePermission,
            RolePermission.permission_id
            == Permission.id,
        )
        .join(
            Role,
            Role.id
            == RolePermission.role_id,
        )
        .join(
            MembershipRole,
            MembershipRole.role_id
            == Role.id,
        )
        .join(
            CompanyMembership,
            CompanyMembership.id
            == MembershipRole.company_membership_id,
        )
        .where(
            CompanyMembership.id
            == company_membership_id,

            CompanyMembership.company_id
            == company_id,

            CompanyMembership.is_active.is_(True),

            Role.company_id
            == company_id,

            Role.is_active.is_(True),

            Permission.is_active.is_(True),
        )
        .distinct()
    )

    result = await session.execute(stmt)

    return set(
        result.scalars().all()
    )


async def get_membership_ids_by_role(
    session: AsyncSession,
    role_id: int,
) -> list[int]:
    stmt = (
        select(
            MembershipRole.company_membership_id
        )
        .where(
            MembershipRole.role_id
            == role_id
        )
        .distinct()
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )