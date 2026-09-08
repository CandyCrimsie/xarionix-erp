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

from services.role_assignment_policy import (
    RoleAssignmentNotAllowedError,
    ensure_role_changes_are_delegated,
    get_changed_role_ids,
    get_membership_assignable_role_ids,
)


async def create_context(
    session: AsyncSession,
):
    company = Company(
        name="Main Company",
    )

    session.add(company)

    await session.flush()

    user = User(
        username="assignment-manager",
        password_hash="test",
    )

    session.add(user)

    await session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company.id,
    )

    session.add(membership)

    await session.flush()

    manager_a = Role(
        company_id=company.id,
        name="Support Manager",
    )

    manager_b = Role(
        company_id=company.id,
        name="Project Manager",
    )

    inactive_manager = Role(
        company_id=company.id,
        name="Inactive Manager",
        is_active=False,
    )

    operator = Role(
        company_id=company.id,
        name="Operator",
    )

    trainee = Role(
        company_id=company.id,
        name="Trainee",
    )

    viewer = Role(
        company_id=company.id,
        name="Viewer",
    )

    administrator = Role(
        company_id=company.id,
        name="Administrator",
    )

    session.add_all(
        [
            manager_a,
            manager_b,
            inactive_manager,
            operator,
            trainee,
            viewer,
            administrator,
        ]
    )

    await session.flush()

    session.add_all(
        [
            MembershipRole(
                company_membership_id=membership.id,
                role_id=manager_a.id,
            ),

            MembershipRole(
                company_membership_id=membership.id,
                role_id=manager_b.id,
            ),

            MembershipRole(
                company_membership_id=membership.id,
                role_id=inactive_manager.id,
            ),
        ]
    )

    session.add_all(
        [
            RoleDelegation(
                manager_role_id=manager_a.id,
                assignable_role_id=operator.id,
            ),

            RoleDelegation(
                manager_role_id=manager_a.id,
                assignable_role_id=trainee.id,
            ),

            RoleDelegation(
                manager_role_id=manager_b.id,
                assignable_role_id=viewer.id,
            ),

            #
            # Специально делаем delegation
            # от inactive manager.
            #
            # Она НЕ должна давать actor
            # возможность назначать Administrator.
            #
            RoleDelegation(
                manager_role_id=inactive_manager.id,
                assignable_role_id=administrator.id,
            ),
        ]
    )

    await session.flush()

    return {
        "company": company,
        "membership": membership,

        "manager_a": manager_a,
        "manager_b": manager_b,
        "inactive_manager": inactive_manager,

        "operator": operator,
        "trainee": trainee,
        "viewer": viewer,
        "administrator": administrator,
    }


def test_get_changed_role_ids_returns_symmetric_difference():
    changed = get_changed_role_ids(
        current_role_ids={
            1,
            2,
            3,
        },
        requested_role_ids={
            2,
            3,
            4,
        },
    )

    assert changed == {
        1,
        4,
    }


@pytest.mark.asyncio
async def test_assignable_roles_are_merged_from_multiple_manager_roles(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    role_ids = (
        await get_membership_assignable_role_ids(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert role_ids == {
        ctx["operator"].id,
        ctx["trainee"].id,
        ctx["viewer"].id,
    }


@pytest.mark.asyncio
async def test_inactive_manager_role_does_not_grant_delegation(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    role_ids = (
        await get_membership_assignable_role_ids(
            db_session,
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["membership"].id
            ),
        )
    )

    assert (
        ctx["administrator"].id
        not in role_ids
    )


@pytest.mark.asyncio
async def test_unchanged_undelegated_role_is_allowed(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await ensure_role_changes_are_delegated(
        db_session,
        company_id=ctx["company"].id,
        actor_membership_id=(
            ctx["membership"].id
        ),
        current_role_ids={
            ctx["administrator"].id,
            ctx["operator"].id,
        },
        requested_role_ids={
            ctx["administrator"].id,
            ctx["operator"].id,
        },
    )


@pytest.mark.asyncio
async def test_delegated_role_can_be_added(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await ensure_role_changes_are_delegated(
        db_session,
        company_id=ctx["company"].id,
        actor_membership_id=(
            ctx["membership"].id
        ),
        current_role_ids={
            ctx["operator"].id,
        },
        requested_role_ids={
            ctx["operator"].id,
            ctx["trainee"].id,
        },
    )


@pytest.mark.asyncio
async def test_delegated_role_can_be_removed(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await ensure_role_changes_are_delegated(
        db_session,
        company_id=ctx["company"].id,
        actor_membership_id=(
            ctx["membership"].id
        ),
        current_role_ids={
            ctx["operator"].id,
            ctx["trainee"].id,
        },
        requested_role_ids={
            ctx["operator"].id,
        },
    )


@pytest.mark.asyncio
async def test_delegated_roles_can_be_replaced(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await ensure_role_changes_are_delegated(
        db_session,
        company_id=ctx["company"].id,
        actor_membership_id=(
            ctx["membership"].id
        ),
        current_role_ids={
            ctx["operator"].id,
        },
        requested_role_ids={
            ctx["trainee"].id,
        },
    )


@pytest.mark.asyncio
async def test_undelegated_role_cannot_be_added(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    with pytest.raises(
        RoleAssignmentNotAllowedError
    ) as exc_info:
        await ensure_role_changes_are_delegated(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=(
                ctx["membership"].id
            ),
            current_role_ids={
                ctx["operator"].id,
            },
            requested_role_ids={
                ctx["operator"].id,
                ctx["administrator"].id,
            },
        )

    assert exc_info.value.role_ids == [
        ctx["administrator"].id,
    ]


@pytest.mark.asyncio
async def test_undelegated_role_cannot_be_removed(
    db_session: AsyncSession,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    with pytest.raises(
        RoleAssignmentNotAllowedError
    ) as exc_info:
        await ensure_role_changes_are_delegated(
            db_session,
            company_id=ctx["company"].id,
            actor_membership_id=(
                ctx["membership"].id
            ),
            current_role_ids={
                ctx["administrator"].id,
                ctx["operator"].id,
            },
            requested_role_ids={
                ctx["operator"].id,
            },
        )

    assert exc_info.value.role_ids == [
        ctx["administrator"].id,
    ]