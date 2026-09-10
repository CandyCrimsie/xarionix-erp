from sqlalchemy import (
    and_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from dataclasses import dataclass
from datetime import datetime

from models.company import Company
from models.company_memberships import (
    CompanyMembership,
)
from models.users import User
from models.organizational_units import (
    OrganizationalUnit,
    OrganizationalUnitType,
)

from core.permissions.scopes import (
    PermissionScope,
)

from models.unit_memberships import (
    UnitMembership,
)


@dataclass(
    slots=True,
    frozen=True,
)
class CompanyMemberSummary:
    id: int

    user_id: int
    username: str
    user_is_active: bool

    company_id: int

    is_active: bool

    primary_unit_id: int | None
    primary_unit_name: str | None
    primary_unit_type: (
        OrganizationalUnitType | None
    )

    created_at: datetime
    updated_at: datetime


async def get_company_member_summaries(
    session: AsyncSession,
    membership_ids: list[int],
) -> list[CompanyMemberSummary]:
    if not membership_ids:
        return []

    stmt = (
        select(
            CompanyMembership.id.label(
                "id"
            ),
            CompanyMembership.user_id.label(
                "user_id"
            ),
            User.username.label(
                "username"
            ),
            User.is_active.label(
                "user_is_active"
            ),
            CompanyMembership.company_id.label(
                "company_id"
            ),
            CompanyMembership.is_active.label(
                "is_active"
            ),
            OrganizationalUnit.id.label(
                "primary_unit_id"
            ),
            OrganizationalUnit.name.label(
                "primary_unit_name"
            ),
            OrganizationalUnit.type.label(
                "primary_unit_type"
            ),
            CompanyMembership.created_at.label(
                "created_at"
            ),
            CompanyMembership.updated_at.label(
                "updated_at"
            ),
        )
        .join(
            User,
            User.id
            == CompanyMembership.user_id,
        )
        .outerjoin(
            UnitMembership,
            and_(
                UnitMembership.company_membership_id
                == CompanyMembership.id,
                UnitMembership.is_primary.is_(
                    True
                ),
                UnitMembership.is_active.is_(
                    True
                ),
            ),
        )
        .outerjoin(
            OrganizationalUnit,
            OrganizationalUnit.id
            == UnitMembership.unit_id,
        )
        .where(
            CompanyMembership.id.in_(
                membership_ids
            )
        )
        .order_by(
            CompanyMembership.id.asc()
        )
    )

    result = await session.execute(
        stmt
    )

    return [
        CompanyMemberSummary(
            **row
        )
        for row
        in result.mappings().all()
    ]


async def get_company_membership_by_id(
    session: AsyncSession,
    membership_id: int,
) -> CompanyMembership | None:
    return await session.get(
        CompanyMembership,
        membership_id,
    )


async def get_company_membership_by_user(
    session: AsyncSession,
    *,
    company_id: int,
    user_id: int,
) -> CompanyMembership | None:
    stmt = (
        select(CompanyMembership)
        .where(
            CompanyMembership.company_id
            == company_id,
            CompanyMembership.user_id
            == user_id,
        )
    )

    result = await session.execute(stmt)

    return result.scalar_one_or_none()


async def get_company_memberships(
    session: AsyncSession,
    company_id: int,
) -> list[CompanyMembership]:
    stmt = (
        select(CompanyMembership)
        .where(
            CompanyMembership.company_id
            == company_id
        )
        .order_by(
            CompanyMembership.id.asc()
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def get_scoped_company_memberships(
    session: AsyncSession,
    *,
    company_id: int,
    current_membership_id: int,
    scope: PermissionScope,
    unit_ids: set[int] | None = None,
) -> list[CompanyMembership]:
    stmt = (
        select(CompanyMembership)
        .where(
            CompanyMembership.company_id
            == company_id
        )
    )

    if scope == PermissionScope.SELF:
        stmt = stmt.where(
            CompanyMembership.id
            == current_membership_id
        )

    elif scope in {
        PermissionScope.OWN_UNIT,
        PermissionScope.OWN_UNIT_TREE,
    }:
        if not unit_ids:
            return []

        stmt = (
            stmt
            .join(
                UnitMembership,
                UnitMembership.company_membership_id
                == CompanyMembership.id,
            )
            .where(
                UnitMembership.is_active.is_(
                    True
                ),
                UnitMembership.is_primary.is_(
                    True
                ),
                UnitMembership.unit_id.in_(
                    unit_ids
                ),
            )
        )

    elif scope == PermissionScope.COMPANY:
        pass

    else:
        raise ValueError(
            f"Unsupported permission scope: {scope}"
        )

    stmt = stmt.order_by(
        CompanyMembership.id.asc()
    )

    result = await session.execute(
        stmt
    )

    return list(
        result.scalars().all()
    )


async def get_scoped_company_membership_by_id(
    session: AsyncSession,
    *,
    company_id: int,
    membership_id: int,
    current_membership_id: int,
    scope: PermissionScope,
    unit_ids: set[int] | None = None,
) -> CompanyMembership | None:
    stmt = (
        select(CompanyMembership)
        .where(
            CompanyMembership.id
            == membership_id,
            CompanyMembership.company_id
            == company_id,
        )
    )

    if scope == PermissionScope.SELF:
        stmt = stmt.where(
            CompanyMembership.id
            == current_membership_id
        )

    elif scope in {
        PermissionScope.OWN_UNIT,
        PermissionScope.OWN_UNIT_TREE,
    }:
        if not unit_ids:
            return None

        stmt = (
            stmt
            .join(
                UnitMembership,
                UnitMembership.company_membership_id
                == CompanyMembership.id,
            )
            .where(
                UnitMembership.is_active.is_(
                    True
                ),
                UnitMembership.is_primary.is_(
                    True
                ),
                UnitMembership.unit_id.in_(
                    unit_ids
                ),
            )
        )

    elif scope == PermissionScope.COMPANY:
        pass

    else:
        raise ValueError(
            f"Unsupported permission scope: {scope}"
        )

    result = await session.execute(
        stmt
    )

    return result.scalar_one_or_none()


async def get_user_company_memberships(
    session: AsyncSession,
    user_id: int,
) -> list[CompanyMembership]:
    stmt = (
        select(CompanyMembership)
        .where(
            CompanyMembership.user_id
            == user_id
        )
        .order_by(
            CompanyMembership.id.asc()
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )


async def create_company_membership(
    session: AsyncSession,
    *,
    user_id: int,
    company_id: int,
) -> CompanyMembership:
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
    )

    session.add(membership)

    await session.flush()

    return membership


async def get_available_companies_for_user(
    session: AsyncSession,
    user_id: int,
) -> list[Company]:
    stmt = (
        select(Company)
        .join(
            CompanyMembership,
            CompanyMembership.company_id == Company.id,
        )
        .where(
            CompanyMembership.user_id == user_id,
            CompanyMembership.is_active.is_(True),
            Company.is_active.is_(True),
        )
        .order_by(
            Company.name.asc(),
        )
    )

    result = await session.execute(stmt)

    return list(
        result.scalars().all()
    )