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

from repositories.membership_permission_overrides import (
    create_membership_permission_override,
    delete_membership_permission_override,
    update_membership_permission_override,
)

from services.authorization import (
    AuthorizationService,
    invalidate_membership_permissions,
)


async def create_context(
    session: AsyncSession,
):
    company = Company(
        name="Override Cache Company",
    )

    user = User(
        username="override-cache-user",
        password_hash="test",
    )

    permission = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
    )

    session.add_all(
        [
            company,
            user,
            permission,
        ]
    )

    await session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company.id,
    )

    role = Role(
        company_id=company.id,
        name="Operator",
    )

    session.add_all(
        [
            membership,
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
        "membership": membership,
        "permission": permission,
        "role": role,
    }


@pytest.mark.asyncio
async def test_allow_override_is_refreshed_after_cache_invalidation(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    permission_override = (
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
    )

    await db_session.commit()

    authorization = AuthorizationService(
        db_session
    )

    #
    # Первый вызов формирует effective
    # permissions и записывает их в Redis.
    #
    permissions = (
        await authorization.get_effective_permissions(
            company_id=(
                ctx["company"].id
            ),
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert permissions[
        "tasks.read"
    ] == PermissionScope.OWN_UNIT

    #
    # Меняем PostgreSQL source of truth.
    #
    await update_membership_permission_override(
        db_session,
        permission_override=(
            permission_override
        ),
        effect=(
            PermissionOverrideEffect.ALLOW
        ),
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    #
    # Redis пока содержит старое значение.
    #
    cached_permissions = (
        await authorization.get_effective_permissions(
            company_id=(
                ctx["company"].id
            ),
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert cached_permissions[
        "tasks.read"
    ] == PermissionScope.OWN_UNIT

    #
    # Инвалидируем cache конкретного
    # membership.
    #
    await invalidate_membership_permissions(
        company_id=ctx["company"].id,
        company_membership_id=(
            ctx["membership"].id
        ),
    )

    refreshed_permissions = (
        await authorization.get_effective_permissions(
            company_id=(
                ctx["company"].id
            ),
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert refreshed_permissions[
        "tasks.read"
    ] == PermissionScope.COMPANY


@pytest.mark.asyncio
async def test_deny_override_removes_cached_permission_after_invalidation(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    permission_override = (
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
    )

    await db_session.commit()

    authorization = AuthorizationService(
        db_session
    )

    permissions = (
        await authorization.get_effective_permissions(
            company_id=(
                ctx["company"].id
            ),
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert permissions[
        "tasks.read"
    ] == PermissionScope.COMPANY

    #
    # Теперь персонально запрещаем permission.
    #
    await update_membership_permission_override(
        db_session,
        permission_override=(
            permission_override
        ),
        effect=(
            PermissionOverrideEffect.DENY
        ),
        scope=None,
    )

    await db_session.commit()

    #
    # До invalidation Redis всё ещё знает
    # старый ALLOW.
    #
    cached_permissions = (
        await authorization.get_effective_permissions(
            company_id=(
                ctx["company"].id
            ),
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert cached_permissions[
        "tasks.read"
    ] == PermissionScope.COMPANY

    await invalidate_membership_permissions(
        company_id=ctx["company"].id,
        company_membership_id=(
            ctx["membership"].id
        ),
    )

    refreshed_permissions = (
        await authorization.get_effective_permissions(
            company_id=(
                ctx["company"].id
            ),
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert "tasks.read" not in (
        refreshed_permissions
    )


@pytest.mark.asyncio
async def test_deleting_deny_override_restores_role_permission_after_invalidation(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    db_session.add(
        RolePermission(
            role_id=ctx["role"].id,
            permission_id=(
                ctx["permission"].id
            ),
            scope=PermissionScope.SELF,
        )
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

    await db_session.commit()

    authorization = AuthorizationService(
        db_session
    )

    permissions = (
        await authorization.get_effective_permissions(
            company_id=(
                ctx["company"].id
            ),
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert "tasks.read" not in permissions

    #
    # Убираем персональный DENY.
    #
    await delete_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["permission"].id
        ),
    )

    await db_session.commit()

    #
    # Redis пока по-прежнему содержит {}.
    #
    cached_permissions = (
        await authorization.get_effective_permissions(
            company_id=(
                ctx["company"].id
            ),
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert "tasks.read" not in (
        cached_permissions
    )

    await invalidate_membership_permissions(
        company_id=ctx["company"].id,
        company_membership_id=(
            ctx["membership"].id
        ),
    )

    refreshed_permissions = (
        await authorization.get_effective_permissions(
            company_id=(
                ctx["company"].id
            ),
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert refreshed_permissions[
        "tasks.read"
    ] == PermissionScope.SELF