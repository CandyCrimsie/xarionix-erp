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

from services.authorization import (
    AuthorizationService,
)

from services.membership_permission_overrides import (
    CompanyMembershipInactiveError,
    CompanyMembershipNotFoundError,
    InvalidPermissionOverrideError,
    InvalidPermissionScopeError,
    PermissionInactiveError,
    PermissionNotFoundError,
    PermissionOverrideNotFoundError,
    delete_membership_permission_override,
    list_membership_permission_overrides,
    set_membership_permission_override,
)


async def create_context(
    session: AsyncSession,
):
    company = Company(
        name="Override Service Company",
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
        username="override-service-user",
        password_hash="test",
    )

    foreign_user = User(
        username="override-foreign-user",
        password_hash="test",
    )

    session.add_all(
        [
            user,
            foreign_user,
        ]
    )

    await session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company.id,
    )

    foreign_membership = CompanyMembership(
        user_id=foreign_user.id,
        company_id=foreign_company.id,
    )

    session.add_all(
        [
            membership,
            foreign_membership,
        ]
    )

    await session.flush()

    tasks_read = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
    )

    companies_manage = Permission(
        code="companies.manage",
        name="Manage companies",
        module="companies",
    )

    inactive_permission = Permission(
        code="tasks.update",
        name="Update tasks",
        module="tasks",
        is_active=False,
    )

    role = Role(
        company_id=company.id,
        name="Operator",
    )

    session.add_all(
        [
            tasks_read,
            companies_manage,
            inactive_permission,
            role,
        ]
    )

    await session.flush()

    session.add_all(
        [
            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=role.id,
            ),

            RolePermission(
                role_id=role.id,
                permission_id=(
                    tasks_read.id
                ),
                scope=PermissionScope.SELF,
            ),
        ]
    )

    await session.flush()

    return {
        "company": company,
        "foreign_company": foreign_company,

        "membership": membership,
        "foreign_membership": (
            foreign_membership
        ),

        "tasks_read": tasks_read,
        "companies_manage": (
            companies_manage
        ),
        "inactive_permission": (
            inactive_permission
        ),

        "role": role,
    }


@pytest.mark.asyncio
async def test_set_allow_override_creates_and_lists_override(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    created = (
        await set_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
            effect=(
                PermissionOverrideEffect.ALLOW
            ),
            scope=PermissionScope.COMPANY,
        )
    )

    assert (
        created.effect
        == PermissionOverrideEffect.ALLOW
    )
    assert (
        created.scope
        == PermissionScope.COMPANY
    )

    overrides = (
        await list_membership_permission_overrides(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert [
        item.id
        for item in overrides
    ] == [
        created.id
    ]


@pytest.mark.asyncio
async def test_set_override_updates_existing_override(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    created = (
        await set_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
            effect=(
                PermissionOverrideEffect.ALLOW
            ),
            scope=PermissionScope.COMPANY,
        )
    )

    updated = (
        await set_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
            effect=(
                PermissionOverrideEffect.DENY
            ),
            scope=None,
        )
    )

    assert updated.id == created.id
    assert (
        updated.effect
        == PermissionOverrideEffect.DENY
    )
    assert updated.scope is None


@pytest.mark.asyncio
async def test_set_override_rejects_foreign_membership(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    with pytest.raises(
        CompanyMembershipNotFoundError
    ):
        await set_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["foreign_membership"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
            effect=(
                PermissionOverrideEffect.ALLOW
            ),
            scope=PermissionScope.COMPANY,
        )


@pytest.mark.asyncio
async def test_set_override_rejects_inactive_membership(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    ctx["membership"].is_active = False

    await db_session.commit()

    with pytest.raises(
        CompanyMembershipInactiveError
    ):
        await set_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
            effect=(
                PermissionOverrideEffect.DENY
            ),
            scope=None,
        )


@pytest.mark.asyncio
async def test_set_override_rejects_missing_permission(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    with pytest.raises(
        PermissionNotFoundError
    ):
        await set_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
            permission_id=999999999,
            effect=(
                PermissionOverrideEffect.DENY
            ),
            scope=None,
        )


@pytest.mark.asyncio
async def test_set_override_rejects_inactive_permission(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    with pytest.raises(
        PermissionInactiveError
    ):
        await set_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
            permission_id=(
                ctx["inactive_permission"].id
            ),
            effect=(
                PermissionOverrideEffect.ALLOW
            ),
            scope=PermissionScope.COMPANY,
        )


@pytest.mark.asyncio
async def test_set_override_rejects_invalid_permission_scope(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    with pytest.raises(
        InvalidPermissionScopeError
    ) as exc:
        await set_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
            permission_id=(
                ctx["companies_manage"].id
            ),
            effect=(
                PermissionOverrideEffect.ALLOW
            ),
            scope=PermissionScope.OWN_UNIT,
        )

    assert exc.value.permission_id == (
        ctx["companies_manage"].id
    )

    assert (
        exc.value.allowed_scopes
        == [
            PermissionScope.COMPANY,
        ]
    )


@pytest.mark.asyncio
async def test_set_override_validates_effect_scope_pair(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    with pytest.raises(
        InvalidPermissionOverrideError
    ):
        await set_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
            effect=(
                PermissionOverrideEffect.ALLOW
            ),
            scope=None,
        )

    with pytest.raises(
        InvalidPermissionOverrideError
    ):
        await set_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
            effect=(
                PermissionOverrideEffect.DENY
            ),
            scope=PermissionScope.COMPANY,
        )


@pytest.mark.asyncio
async def test_set_override_invalidates_authorization_cache(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    authorization = AuthorizationService(
        db_session
    )

    initial = (
        await authorization.get_effective_permissions(
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert initial[
        "tasks.read"
    ] == PermissionScope.SELF

    #
    # Service должен сам удалить старый Redis
    # cache после commit.
    #
    await set_membership_permission_override(
        db_session,
        company_id=ctx["company"].id,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["tasks_read"].id
        ),
        effect=(
            PermissionOverrideEffect.DENY
        ),
        scope=None,
    )

    refreshed = (
        await authorization.get_effective_permissions(
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert "tasks.read" not in refreshed


@pytest.mark.asyncio
async def test_delete_override_invalidates_authorization_cache(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await set_membership_permission_override(
        db_session,
        company_id=ctx["company"].id,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["tasks_read"].id
        ),
        effect=(
            PermissionOverrideEffect.DENY
        ),
        scope=None,
    )

    authorization = AuthorizationService(
        db_session
    )

    denied = (
        await authorization.get_effective_permissions(
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert "tasks.read" not in denied

    await delete_membership_permission_override(
        db_session,
        company_id=ctx["company"].id,
        company_membership_id=(
            ctx["membership"].id
        ),
        permission_id=(
            ctx["tasks_read"].id
        ),
    )

    restored = (
        await authorization.get_effective_permissions(
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert restored[
        "tasks.read"
    ] == PermissionScope.SELF


@pytest.mark.asyncio
async def test_delete_missing_override_is_rejected(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    with pytest.raises(
        PermissionOverrideNotFoundError
    ):
        await delete_membership_permission_override(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
        )