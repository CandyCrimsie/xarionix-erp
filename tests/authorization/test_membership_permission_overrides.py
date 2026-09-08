import pytest

from sqlalchemy.exc import IntegrityError
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
from models.permissions import Permission
from models.users import User

from repositories.membership_permission_overrides import (
    create_membership_permission_override,
    delete_membership_permission_override,
    get_membership_permission_override,
    get_membership_permission_overrides,
    update_membership_permission_override,
)


async def create_context(
    session: AsyncSession,
):
    company = Company(
        name="Main Company",
    )

    session.add(
        company
    )

    await session.flush()

    user_a = User(
        username="override-user-a",
        password_hash="test",
    )

    user_b = User(
        username="override-user-b",
        password_hash="test",
    )

    session.add_all(
        [
            user_a,
            user_b,
        ]
    )

    await session.flush()

    membership_a = CompanyMembership(
        user_id=user_a.id,
        company_id=company.id,
    )

    membership_b = CompanyMembership(
        user_id=user_b.id,
        company_id=company.id,
    )

    session.add_all(
        [
            membership_a,
            membership_b,
        ]
    )

    await session.flush()

    tasks_read = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
    )

    tasks_create = Permission(
        code="tasks.create",
        name="Create tasks",
        module="tasks",
    )

    session.add_all(
        [
            tasks_read,
            tasks_create,
        ]
    )

    await session.flush()

    return {
        "company": company,

        "membership_a": membership_a,
        "membership_b": membership_b,

        "tasks_read": tasks_read,
        "tasks_create": tasks_create,
    }


@pytest.mark.asyncio
async def test_create_allow_override(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    permission_override = (
        await create_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
            effect=(
                PermissionOverrideEffect.ALLOW
            ),
            scope=PermissionScope.OWN_UNIT,
        )
    )

    assert (
        permission_override.company_membership_id
        == ctx["membership_a"].id
    )

    assert (
        permission_override.permission_id
        == ctx["tasks_read"].id
    )

    assert (
        permission_override.effect
        == PermissionOverrideEffect.ALLOW
    )

    assert (
        permission_override.scope
        == PermissionScope.OWN_UNIT
    )


@pytest.mark.asyncio
async def test_create_deny_override(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    permission_override = (
        await create_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
            ),
            permission_id=(
                ctx["tasks_create"].id
            ),
            effect=(
                PermissionOverrideEffect.DENY
            ),
            scope=None,
        )
    )

    assert (
        permission_override.effect
        == PermissionOverrideEffect.DENY
    )

    assert permission_override.scope is None


@pytest.mark.asyncio
async def test_get_membership_permission_override(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    created = (
        await create_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
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

    found = (
        await get_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
        )
    )

    assert found is not None
    assert found.id == created.id


@pytest.mark.asyncio
async def test_get_membership_permission_overrides(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership_a"].id
        ),
        permission_id=(
            ctx["tasks_create"].id
        ),
        effect=PermissionOverrideEffect.DENY,
        scope=None,
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership_a"].id
        ),
        permission_id=(
            ctx["tasks_read"].id
        ),
        effect=PermissionOverrideEffect.ALLOW,
        scope=PermissionScope.OWN_UNIT,
    )

    #
    # Override другого membership не должен
    # попасть в результат.
    #
    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership_b"].id
        ),
        permission_id=(
            ctx["tasks_read"].id
        ),
        effect=PermissionOverrideEffect.ALLOW,
        scope=PermissionScope.COMPANY,
    )

    overrides = (
        await get_membership_permission_overrides(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
            ),
        )
    )

    assert {
        item.permission_id
        for item in overrides
    } == {
        ctx["tasks_read"].id,
        ctx["tasks_create"].id,
    }

    assert all(
        item.company_membership_id
        == ctx["membership_a"].id
        for item in overrides
    )


@pytest.mark.asyncio
async def test_update_membership_permission_override(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    permission_override = (
        await create_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
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
    )

    assert (
        updated.effect
        == PermissionOverrideEffect.DENY
    )

    assert updated.scope is None


@pytest.mark.asyncio
async def test_delete_membership_permission_override(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership_a"].id
        ),
        permission_id=(
            ctx["tasks_read"].id
        ),
        effect=PermissionOverrideEffect.ALLOW,
        scope=PermissionScope.COMPANY,
    )

    await delete_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership_a"].id
        ),
        permission_id=(
            ctx["tasks_read"].id
        ),
    )

    found = (
        await get_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
        )
    )

    assert found is None


@pytest.mark.asyncio
async def test_duplicate_override_is_rejected(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await create_membership_permission_override(
        db_session,
        company_membership_id=(
            ctx["membership_a"].id
        ),
        permission_id=(
            ctx["tasks_read"].id
        ),
        effect=PermissionOverrideEffect.ALLOW,
        scope=PermissionScope.COMPANY,
    )

    with pytest.raises(
        IntegrityError
    ):
        await create_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
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
async def test_allow_without_scope_is_rejected(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    with pytest.raises(
        IntegrityError
    ):
        await create_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
            effect=(
                PermissionOverrideEffect.ALLOW
            ),
            scope=None,
        )


@pytest.mark.asyncio
async def test_deny_with_scope_is_rejected(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    with pytest.raises(
        IntegrityError
    ):
        await create_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
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
async def test_same_permission_can_be_overridden_for_different_memberships(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    override_a = (
        await create_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_a"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
            effect=(
                PermissionOverrideEffect.ALLOW
            ),
            scope=PermissionScope.OWN_UNIT,
        )
    )

    override_b = (
        await create_membership_permission_override(
            db_session,
            company_membership_id=(
                ctx["membership_b"].id
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

    assert override_a.id != override_b.id