import pytest

from sqlalchemy.ext.asyncio import (
    AsyncSession,
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


async def create_base_context(
    session: AsyncSession,
):
    user = User(
        username="rbac-user",
        password_hash="test",
    )

    company = Company(
        name="RBAC Company",
    )

    session.add_all(
        [
            user,
            company,
        ]
    )

    await session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company.id,
    )

    session.add(
        membership
    )

    await session.flush()

    return (
        user,
        company,
        membership,
    )


@pytest.mark.asyncio
async def test_permissions_from_multiple_roles_are_merged(
    db_session: AsyncSession,
):
    _, company, membership = (
        await create_base_context(
            db_session
        )
    )

    permission_read = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
    )

    permission_update = Permission(
        code="tasks.update",
        name="Update tasks",
        module="tasks",
    )

    role_operator = Role(
        company_id=company.id,
        name="Operator",
    )

    role_manager = Role(
        company_id=company.id,
        name="Manager",
    )

    db_session.add_all(
        [
            permission_read,
            permission_update,
            role_operator,
            role_manager,
        ]
    )

    await db_session.flush()

    db_session.add_all(
        [
            RolePermission(
                role_id=role_operator.id,
                permission_id=(
                    permission_read.id
                ),
                scope=PermissionScope.SELF,
            ),

            RolePermission(
                role_id=role_manager.id,
                permission_id=(
                    permission_update.id
                ),
                scope=(
                    PermissionScope.OWN_UNIT
                ),
            ),

            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=role_operator.id,
            ),

            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=role_manager.id,
            ),
        ]
    )

    await db_session.flush()

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=company.id,
            company_membership_id=(
                membership.id
            ),
        )
    )

    assert permissions == {
        "tasks.read": (
            PermissionScope.SELF
        ),
        "tasks.update": (
            PermissionScope.OWN_UNIT
        ),
    }


@pytest.mark.asyncio
async def test_broader_scope_wins(
    db_session: AsyncSession,
):
    _, company, membership = (
        await create_base_context(
            db_session
        )
    )

    permission = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
    )

    role_a = Role(
        company_id=company.id,
        name="Role A",
    )

    role_b = Role(
        company_id=company.id,
        name="Role B",
    )

    db_session.add_all(
        [
            permission,
            role_a,
            role_b,
        ]
    )

    await db_session.flush()

    db_session.add_all(
        [
            RolePermission(
                role_id=role_a.id,
                permission_id=permission.id,
                scope=PermissionScope.SELF,
            ),

            RolePermission(
                role_id=role_b.id,
                permission_id=permission.id,
                scope=(
                    PermissionScope.OWN_UNIT_TREE
                ),
            ),

            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=role_a.id,
            ),

            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=role_b.id,
            ),
        ]
    )

    await db_session.flush()

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=company.id,
            company_membership_id=(
                membership.id
            ),
        )
    )

    assert permissions[
        "tasks.read"
    ] == PermissionScope.OWN_UNIT_TREE


@pytest.mark.asyncio
async def test_inactive_role_does_not_grant_permissions(
    db_session: AsyncSession,
):
    _, company, membership = (
        await create_base_context(
            db_session
        )
    )

    permission = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
    )

    role = Role(
        company_id=company.id,
        name="Disabled Role",
        is_active=False,
    )

    db_session.add_all(
        [
            permission,
            role,
        ]
    )

    await db_session.flush()

    db_session.add_all(
        [
            RolePermission(
                role_id=role.id,
                permission_id=permission.id,
                scope=PermissionScope.COMPANY,
            ),

            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=role.id,
            ),
        ]
    )

    await db_session.flush()

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=company.id,
            company_membership_id=(
                membership.id
            ),
        )
    )

    assert permissions == {}


@pytest.mark.asyncio
async def test_inactive_permission_is_ignored(
    db_session: AsyncSession,
):
    _, company, membership = (
        await create_base_context(
            db_session
        )
    )

    permission = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
        is_active=False,
    )

    role = Role(
        company_id=company.id,
        name="Operator",
    )

    db_session.add_all(
        [
            permission,
            role,
        ]
    )

    await db_session.flush()

    db_session.add_all(
        [
            RolePermission(
                role_id=role.id,
                permission_id=permission.id,
                scope=PermissionScope.COMPANY,
            ),

            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=role.id,
            ),
        ]
    )

    await db_session.flush()

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=company.id,
            company_membership_id=(
                membership.id
            ),
        )
    )

    assert permissions == {}


@pytest.mark.asyncio
async def test_role_from_other_company_is_ignored(
    db_session: AsyncSession,
):
    _, company_a, membership = (
        await create_base_context(
            db_session
        )
    )

    company_b = Company(
        name="Other Company",
    )

    permission = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
    )

    db_session.add_all(
        [
            company_b,
            permission,
        ]
    )

    await db_session.flush()

    foreign_role = Role(
        company_id=company_b.id,
        name="Foreign Role",
    )

    db_session.add(
        foreign_role
    )

    await db_session.flush()

    db_session.add_all(
        [
            RolePermission(
                role_id=foreign_role.id,
                permission_id=permission.id,
                scope=PermissionScope.COMPANY,
            ),

            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=foreign_role.id,
            ),
        ]
    )

    await db_session.flush()

    permissions = (
        await get_effective_permission_codes(
            db_session,
            company_id=company_a.id,
            company_membership_id=(
                membership.id
            ),
        )
    )

    assert permissions == {}