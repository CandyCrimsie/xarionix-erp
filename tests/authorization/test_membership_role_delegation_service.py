import pytest

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from models.company import Company
from models.company_memberships import (
    CompanyMembership,
)
from models.membership_roles import (
    MembershipRole,
)
from models.role_delegations import (
    RoleDelegation,
)
from models.roles import Role
from models.users import User

from repositories.membership_roles import (
    get_membership_roles,
)

from services.membership_roles import (
    CompanyMembershipInactiveError,
    InvalidRolesError,
    replace_membership_roles_with_delegation,
)

from services.role_assignment_policy import (
    RoleAssignmentNotAllowedError,
)

from core.permissions.scopes import (
    PermissionScope,
)

from models.permissions import Permission
from models.role_permissions import (
    RolePermission,
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

    actor_user = User(
        username="role-manager",
        password_hash="test",
    )

    target_user = User(
        username="target-user",
        password_hash="test",
    )

    session.add_all(
        [
            actor_user,
            target_user,
        ]
    )

    await session.flush()

    actor = CompanyMembership(
        user_id=actor_user.id,
        company_id=company.id,
    )

    target = CompanyMembership(
        user_id=target_user.id,
        company_id=company.id,
    )

    session.add_all(
        [
            actor,
            target,
        ]
    )

    await session.flush()

    manager = Role(
        company_id=company.id,
        name="Support Manager",
    )

    operator = Role(
        company_id=company.id,
        name="Support Operator",
    )

    trainee = Role(
        company_id=company.id,
        name="Support Trainee",
    )

    administrator = Role(
        company_id=company.id,
        name="Administrator",
    )

    inactive = Role(
        company_id=company.id,
        name="Inactive Role",
        is_active=False,
    )

    foreign = Role(
        company_id=foreign_company.id,
        name="Foreign Role",
    )

    session.add_all(
        [
            manager,
            operator,
            trainee,
            administrator,
            inactive,
            foreign,
        ]
    )

    await session.flush()

    roles_assign_permission = Permission(
        code="roles.assign",
        name="Assign roles",
        module="roles",
    )

    session.add(
        roles_assign_permission
    )

    await session.flush()

    #
    # Actor обладает Support Manager.
    #
    session.add(
        MembershipRole(
            company_membership_id=actor.id,
            role_id=manager.id,
        )
    )

    session.add(
        RolePermission(
            role_id=manager.id,
            permission_id=(
                roles_assign_permission.id
            ),
            scope=PermissionScope.COMPANY,
        )
    )

    #
    # Support Manager может управлять
    # только Operator и Trainee.
    #
    session.add_all(
        [
            RoleDelegation(
                manager_role_id=manager.id,
                assignable_role_id=operator.id,
            ),

            RoleDelegation(
                manager_role_id=manager.id,
                assignable_role_id=trainee.id,
            ),
        ]
    )

    await session.flush()

    return {
        "company": company,
        "foreign_company": foreign_company,

        "actor": actor,
        "target": target,

        "manager": manager,
        "operator": operator,
        "trainee": trainee,
        "administrator": administrator,
        "inactive": inactive,
        "foreign": foreign,
    }


async def add_target_roles(
    session: AsyncSession,
    *,
    target: CompanyMembership,
    roles: list[Role],
) -> None:
    session.add_all(
        [
            MembershipRole(
                company_membership_id=target.id,
                role_id=role.id,
            )
            for role in roles
        ]
    )

    await session.flush()


async def get_target_role_ids(
    session: AsyncSession,
    *,
    target: CompanyMembership,
) -> set[int]:
    roles = await get_membership_roles(
        session,
        target.id,
    )

    return {
        role.id
        for role in roles
    }


def result_role_ids(
    roles: list[Role],
) -> set[int]:
    return {
        role.id
        for role in roles
    }


@pytest.mark.asyncio
async def test_secure_replace_can_add_delegated_role(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
        ],
    )

    await db_session.commit()

    roles = (
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=ctx["actor"].id,
            company_membership_id=ctx["target"].id,
            role_ids=[
                ctx["operator"].id,
                ctx["trainee"].id,
            ],
        )
    )

    assert result_role_ids(
        roles
    ) == {
        ctx["operator"].id,
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_secure_replace_can_remove_delegated_role(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
            ctx["trainee"],
        ],
    )

    await db_session.commit()

    roles = (
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=ctx["actor"].id,
            company_membership_id=ctx["target"].id,
            role_ids=[
                ctx["operator"].id,
            ],
        )
    )

    assert result_role_ids(
        roles
    ) == {
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_secure_replace_preserves_unchanged_undelegated_role(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["administrator"],
            ctx["operator"],
        ],
    )

    await db_session.commit()

    roles = (
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=ctx["actor"].id,
            company_membership_id=ctx["target"].id,
            role_ids=[
                ctx["administrator"].id,
                ctx["trainee"].id,
            ],
        )
    )

    assert result_role_ids(
        roles
    ) == {
        ctx["administrator"].id,
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_secure_replace_cannot_add_undelegated_role(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
        ],
    )

    await db_session.commit()

    with pytest.raises(
        RoleAssignmentNotAllowedError
    ) as exc_info:
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=ctx["actor"].id,
            company_membership_id=ctx["target"].id,
            role_ids=[
                ctx["operator"].id,
                ctx["administrator"].id,
            ],
        )

    assert exc_info.value.role_ids == [
        ctx["administrator"].id,
    ]

    #
    # БД не должна измениться.
    #
    assert await get_target_role_ids(
        db_session,
        target=ctx["target"],
    ) == {
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_secure_replace_cannot_remove_undelegated_role(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["administrator"],
            ctx["operator"],
        ],
    )

    await db_session.commit()

    with pytest.raises(
        RoleAssignmentNotAllowedError
    ) as exc_info:
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=ctx["actor"].id,
            company_membership_id=ctx["target"].id,
            role_ids=[
                ctx["operator"].id,
            ],
        )

    assert exc_info.value.role_ids == [
        ctx["administrator"].id,
    ]

    #
    # Особенно важно:
    # Administrator должен остаться в БД.
    #
    assert await get_target_role_ids(
        db_session,
        target=ctx["target"],
    ) == {
        ctx["administrator"].id,
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_secure_replace_no_changes_is_allowed(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["administrator"],
            ctx["operator"],
        ],
    )

    await db_session.commit()

    roles = (
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=ctx["actor"].id,
            company_membership_id=ctx["target"].id,
            role_ids=[
                ctx["administrator"].id,
                ctx["operator"].id,
            ],
        )
    )

    assert result_role_ids(
        roles
    ) == {
        ctx["administrator"].id,
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_secure_replace_rejects_foreign_role_without_changes(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
        ],
    )

    await db_session.commit()

    with pytest.raises(
        InvalidRolesError
    ) as exc_info:
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=ctx["actor"].id,
            company_membership_id=ctx["target"].id,
            role_ids=[
                ctx["operator"].id,
                ctx["foreign"].id,
            ],
        )

    assert exc_info.value.role_ids == [
        ctx["foreign"].id,
    ]

    assert await get_target_role_ids(
        db_session,
        target=ctx["target"],
    ) == {
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_secure_replace_rejects_inactive_actor(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
        ],
    )

    ctx["actor"].is_active = False

    await db_session.commit()

    with pytest.raises(
        CompanyMembershipInactiveError
    ):
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=ctx["actor"].id,
            company_membership_id=ctx["target"].id,
            role_ids=[
                ctx["operator"].id,
                ctx["trainee"].id,
            ],
        )

    assert await get_target_role_ids(
        db_session,
        target=ctx["target"],
    ) == {
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_secure_replace_rejects_inactive_actor(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
        ],
    )

    ctx["actor"].is_active = False

    await db_session.commit()

    with pytest.raises(
        CompanyMembershipInactiveError
    ):
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=ctx["actor"].id,
            company_membership_id=ctx["target"].id,
            role_ids=[
                ctx["operator"].id,
                ctx["trainee"].id,
            ],
        )

    assert await get_target_role_ids(
        db_session,
        target=ctx["target"],
    ) == {
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_secure_replace_rejects_inactive_target(
    db_session: AsyncSession,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
        ],
    )

    ctx["target"].is_active = False

    await db_session.commit()

    with pytest.raises(
        CompanyMembershipInactiveError
    ):
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=ctx["actor"].id,
            company_membership_id=ctx["target"].id,
            role_ids=[
                ctx["operator"].id,
                ctx["trainee"].id,
            ],
        )

    assert await get_target_role_ids(
        db_session,
        target=ctx["target"],
    ) == {
        ctx["operator"].id,
    }