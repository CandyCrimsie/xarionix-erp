import pytest

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

from repositories.role_delegations import (
    get_role_delegations,
)
from repositories.role_permissions import (
    get_role_permissions,
)
from repositories.roles import (
    get_system_role_by_key,
)

from schemas.role_permissions import (
    RolePermissionAssignment,
)
from schemas.roles import (
    RoleCreate,
    RoleUpdate,
)

from services.membership_roles import (
    replace_membership_roles_with_delegation,
)
from services.permissions import (
    sync_permissions,
)
from services.role_delegations import (
    replace_role_delegations_for_role,
)
from services.role_permissions import (
    replace_role_permissions,
)
from services.roles import (
    create_new_role,
    update_role,
)
from services.system_role_policy import (
    SystemRoleProtectedError,
)
from services.system_roles import (
    sync_system_roles_for_company,
)


async def create_ready_company(
    session: AsyncSession,
) -> int:
    await sync_permissions(
        session
    )

    company = Company(
        name="Main Company",
    )

    session.add(
        company
    )

    await session.flush()

    company_id = company.id

    await session.commit()

    await sync_system_roles_for_company(
        session,
        company_id=company_id,
    )

    return company_id


@pytest.mark.asyncio
async def test_system_role_metadata_cannot_be_updated(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_id = await create_ready_company(
        db_session
    )

    administrator = (
        await get_system_role_by_key(
            db_session,
            company_id=company_id,
            system_key=(
                SystemRoleKey
                .ADMINISTRATOR
                .value
            ),
        )
    )

    assert administrator is not None

    original_name = administrator.name

    with pytest.raises(
        SystemRoleProtectedError
    ):
        await update_role(
            db_session,
            company_id=company_id,
            role_id=administrator.id,
            data=RoleUpdate(
                name="Hacked Administrator",
                is_active=False,
            ),
        )

    await db_session.refresh(
        administrator
    )

    assert (
        administrator.name
        == original_name
    )

    assert administrator.is_active is True


@pytest.mark.asyncio
async def test_system_role_permissions_cannot_be_replaced(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_id = await create_ready_company(
        db_session
    )

    employee = (
        await get_system_role_by_key(
            db_session,
            company_id=company_id,
            system_key=(
                SystemRoleKey.EMPLOYEE.value
            ),
        )
    )

    assert employee is not None

    before = await get_role_permissions(
        db_session,
        employee.id,
    )

    before_map = {
        permission.code: scope
        for permission, scope in before
    }

    with pytest.raises(
        SystemRoleProtectedError
    ):
        await replace_role_permissions(
            db_session,
            company_id=company_id,
            role_id=employee.id,
            permissions=[],
        )

    after = await get_role_permissions(
        db_session,
        employee.id,
    )

    after_map = {
        permission.code: scope
        for permission, scope in after
    }

    assert after_map == before_map


@pytest.mark.asyncio
async def test_system_role_delegations_cannot_be_replaced(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_id = await create_ready_company(
        db_session
    )

    administrator = (
        await get_system_role_by_key(
            db_session,
            company_id=company_id,
            system_key=(
                SystemRoleKey
                .ADMINISTRATOR
                .value
            ),
        )
    )

    assert administrator is not None

    before = await get_role_delegations(
        db_session,
        manager_role_id=administrator.id,
    )

    before_ids = {
        item.assignable_role_id
        for item in before
    }

    with pytest.raises(
        SystemRoleProtectedError
    ):
        await replace_role_delegations_for_role(
            db_session,
            company_id=company_id,
            manager_role_id=(
                administrator.id
            ),
            assignable_role_ids=[],
        )

    after = await get_role_delegations(
        db_session,
        manager_role_id=administrator.id,
    )

    after_ids = {
        item.assignable_role_id
        for item in after
    }

    assert after_ids == before_ids


@pytest.mark.asyncio
async def test_custom_role_remains_mutable(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_id = await create_ready_company(
        db_session
    )

    role = await create_new_role(
        db_session,
        company_id=company_id,
        data=RoleCreate(
            name="Custom Operator",
        ),
    )

    updated = await update_role(
        db_session,
        company_id=company_id,
        role_id=role.id,
        data=RoleUpdate(
            name="Senior Custom Operator",
        ),
    )

    assert (
        updated.name
        == "Senior Custom Operator"
    )

    assert updated.is_system is False


@pytest.mark.asyncio
async def test_system_role_can_still_be_assigned_through_delegation(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_id = await create_ready_company(
        db_session
    )

    administrator = (
        await get_system_role_by_key(
            db_session,
            company_id=company_id,
            system_key=(
                SystemRoleKey
                .ADMINISTRATOR
                .value
            ),
        )
    )

    employee = (
        await get_system_role_by_key(
            db_session,
            company_id=company_id,
            system_key=(
                SystemRoleKey.EMPLOYEE.value
            ),
        )
    )

    assert administrator is not None
    assert employee is not None

    actor_user = User(
        username="system-role-admin",
        password_hash="test",
    )

    target_user = User(
        username="system-role-target",
        password_hash="test",
    )

    db_session.add_all(
        [
            actor_user,
            target_user,
        ]
    )

    await db_session.flush()

    actor_membership = CompanyMembership(
        user_id=actor_user.id,
        company_id=company_id,
    )

    target_membership = CompanyMembership(
        user_id=target_user.id,
        company_id=company_id,
    )

    db_session.add_all(
        [
            actor_membership,
            target_membership,
        ]
    )

    await db_session.flush()

    db_session.add(
        MembershipRole(
            company_membership_id=(
                actor_membership.id
            ),
            role_id=administrator.id,
        )
    )

    await db_session.commit()

    result = (
        await replace_membership_roles_with_delegation(
            db_session,
            company_id=company_id,
            actor_membership_id=(
                actor_membership.id
            ),
            company_membership_id=(
                target_membership.id
            ),
            role_ids=[
                employee.id,
            ],
        )
    )

    assert {
        role.id
        for role in result
    } == {
        employee.id,
    }