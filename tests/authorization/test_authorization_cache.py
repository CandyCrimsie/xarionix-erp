import pytest

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.permissions.scopes import (
    PermissionScope,
)

from database.redis import redis_client

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
    clear_authorization_cache,
    invalidate_membership_permissions,
)


@pytest.mark.asyncio
async def test_permission_cache_is_invalidated(
    db_session: AsyncSession,
):
    await clear_authorization_cache()

    user = User(
        username="cache-user",
        password_hash="test",
    )

    company = Company(
        name="Cache Company",
    )

    permission = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
    )

    db_session.add_all(
        [
            user,
            company,
            permission,
        ]
    )

    await db_session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company.id,
    )

    role = Role(
        company_id=company.id,
        name="Operator",
    )

    db_session.add_all(
        [
            membership,
            role,
        ]
    )

    await db_session.flush()

    role_permission = RolePermission(
        role_id=role.id,
        permission_id=permission.id,
        scope=PermissionScope.SELF,
    )

    membership_role = MembershipRole(
        company_membership_id=(
            membership.id
        ),
        role_id=role.id,
    )

    db_session.add_all(
        [
            role_permission,
            membership_role,
        ]
    )

    await db_session.commit()

    authorization = AuthorizationService(
        db_session
    )

    #
    # Первый вызов создаёт Redis cache.
    #
    permissions = (
        await authorization.get_effective_permissions(
            company_id=company.id,
            company_membership_id=(
                membership.id
            ),
        )
    )

    assert permissions[
        "tasks.read"
    ] == PermissionScope.SELF

    #
    # Меняем источник истины в PostgreSQL.
    #
    role_permission.scope = (
        PermissionScope.COMPANY
    )

    await db_session.commit()

    #
    # Cache ещё старый.
    #
    cached_permissions = (
        await authorization.get_effective_permissions(
            company_id=company.id,
            company_membership_id=(
                membership.id
            ),
        )
    )

    assert cached_permissions[
        "tasks.read"
    ] == PermissionScope.SELF

    #
    # Инвалидируем.
    #
    await invalidate_membership_permissions(
        company_id=company.id,
        company_membership_id=(
            membership.id
        ),
    )

    refreshed_permissions = (
        await authorization.get_effective_permissions(
            company_id=company.id,
            company_membership_id=(
                membership.id
            ),
        )
    )

    assert refreshed_permissions[
        "tasks.read"
    ] == PermissionScope.COMPANY

    await clear_authorization_cache()