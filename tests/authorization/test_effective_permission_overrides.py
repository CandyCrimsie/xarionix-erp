import pytest

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.permissions.effects import (
    PermissionOverrideEffect,
)
from core.permissions.scopes import (
    PermissionScope,
)

from models.company import Company
from models.company_memberships import (
    CompanyMembership,
)
from models.membership_roles import (
    MembershipRole,
)
from models.permissions import Permission
from models.role_permissions import (
    RolePermission,
)
from models.roles import Role
from models.users import User

from repositories.authorization import (
    get_effective_permission_codes,
)

from repositories.membership_permission_overrides import (
    create_membership_permission_override,
)


async def create_context(
    session: AsyncSession,
):
    company = Company(
        name="Main Company",
    )

    foreign_company = Company(
        name="Foreign Company",
    )

    session.add_all(
        [
            company,
            foreign_company,
        ]
    )

    await session.flush()

    user = User(
        username="override-effective-user",
        password_hash="test",
    )

    other_user = User(
        username="override-other-user",
        password_hash="test",
    )

    session.add_all(
        [
            user,
            other_user,
        ]
    )

    await session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company.id,
    )

    other_membership = CompanyMembership(
        user_id=other_user.id,
        company_id=company.id,
    )

    session.add_all(
        [
            membership,
            other_membership,
        ]
    )

    await session.flush()

    permission = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
    )

    role = Role(
        company_id=company.id,
        name="Operator",
    )

    session.add_all(
        [
            permission,
            role,
        ]
    )

    await session.flush()

    session.add(
        MembershipRole(
            company_membership_id=(
                membership.id
            ),
            role_id=role.id,
        )
    )

    await session.flush()

    return {
        "company": company,
        "foreign_company": foreign_company,
        "membership": membership,
        "other_membership": other_membership,
        "permission": permission,
        "role": role,
    }


async def grant_role_permission(
    session: AsyncSession,
    *,
    ctx,
    scope: PermissionScope,
) -> None:
    session.add(
        RolePermission(
            role_id=ctx["role"].id,
            permission_id=(
                ctx["permission"].id
            ),
            scope=scope,
        )
    )

    await session.flush()


@pytest.mark.asyncio
async def test_allow_override_adds_permission_without_role_grant(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["permission"].id
        ),
        effect=(
            PermissionOverrideEffect.ALLOW
        ),
        scope=PermissionScope.OWN_UNIT,
    )

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert permissions == {
        "tasks.read": (
            PermissionScope.OWN_UNIT
        ),
    }


@pytest.mark.asyncio
async def test_allow_override_can_broaden_role_scope(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await grant_role_permission(
        db_session,
        ctx=ctx,
        scope=PermissionScope.SELF,
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["permission"].id
        ),
        effect=(
            PermissionOverrideEffect.ALLOW
        ),
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert permissions[
        "tasks.read"
    ] == PermissionScope.OWN_UNIT_TREE


@pytest.mark.asyncio
async def test_allow_override_does_not_narrow_role_scope(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await grant_role_permission(
        db_session,
        ctx=ctx,
        scope=PermissionScope.COMPANY,
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["permission"].id
        ),
        effect=(
            PermissionOverrideEffect.ALLOW
        ),
        scope=PermissionScope.OWN_UNIT,
    )

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert permissions[
        "tasks.read"
    ] == PermissionScope.COMPANY


@pytest.mark.asyncio
async def test_deny_override_removes_role_permission(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await grant_role_permission(
        db_session,
        ctx=ctx,
        scope=PermissionScope.COMPANY,
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["permission"].id
        ),
        effect=(
            PermissionOverrideEffect.DENY
        ),
        scope=None,
    )

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert "tasks.read" not in permissions


@pytest.mark.asyncio
async def test_deny_override_does_not_create_permission(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["permission"].id
        ),
        effect=(
            PermissionOverrideEffect.DENY
        ),
        scope=None,
    )

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert permissions == {}


@pytest.mark.asyncio
async def test_override_from_other_membership_is_ignored(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["other_membership"].id
        ),
        permission_id=(
            ctx["permission"].id
        ),
        effect=(
            PermissionOverrideEffect.ALLOW
        ),
        scope=PermissionScope.COMPANY,
    )

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert permissions == {}


@pytest.mark.asyncio
async def test_allow_override_for_inactive_permission_is_ignored(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    ctx["permission"].is_active = False

    await db_session.flush()

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["permission"].id
        ),
        effect=(
            PermissionOverrideEffect.ALLOW
        ),
        scope=PermissionScope.COMPANY,
    )

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert permissions == {}


@pytest.mark.asyncio
async def test_inactive_membership_does_not_receive_override(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["permission"].id
        ),
        effect=(
            PermissionOverrideEffect.ALLOW
        ),
        scope=PermissionScope.COMPANY,
    )

    ctx["membership"].is_active = False

    await db_session.flush()

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert permissions == {}