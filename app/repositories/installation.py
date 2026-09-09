from sqlalchemy import (
    exists,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.system_roles import (
    SystemRoleKey,
)

from models.company import Company
from models.company_memberships import (
    CompanyMembership,
)
from models.membership_roles import (
    MembershipRole,
)
from models.roles import Role
from models.users import User


async def has_users(
    session: AsyncSession,
) -> bool:
    stmt = select(
        exists().where(
            User.id.is_not(None)
        )
    )

    return bool(
        await session.scalar(stmt)
    )


async def has_companies(
    session: AsyncSession,
) -> bool:
    stmt = select(
        exists().where(
            Company.id.is_not(None)
        )
    )

    return bool(
        await session.scalar(stmt)
    )


async def has_company_memberships(
    session: AsyncSession,
) -> bool:
    stmt = select(
        exists().where(
            CompanyMembership.id.is_not(
                None
            )
        )
    )

    return bool(
        await session.scalar(stmt)
    )


async def has_active_administrator_membership(
    session: AsyncSession,
) -> bool:
    stmt = select(
        exists()
        .select_from(
            CompanyMembership
        )
        .join(
            User,
            User.id
            == CompanyMembership.user_id,
        )
        .join(
            Company,
            Company.id
            == CompanyMembership.company_id,
        )
        .join(
            MembershipRole,
            (
                MembershipRole
                .company_membership_id
                == CompanyMembership.id
            ),
        )
        .join(
            Role,
            Role.id
            == MembershipRole.role_id,
        )
        .where(
            User.is_active.is_(True),

            Company.is_active.is_(True),

            CompanyMembership
            .is_active.is_(True),

            Role.is_active.is_(True),

            Role.is_system.is_(True),

            Role.system_key
            == (
                SystemRoleKey
                .ADMINISTRATOR
                .value
            ),
        )
    )

    return bool(
        await session.scalar(stmt)
    )