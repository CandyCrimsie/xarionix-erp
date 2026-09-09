import pytest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.permissions.scopes import (
    PermissionScope,
)
from core.system_roles import (
    SYSTEM_ROLE_TEMPLATES,
    SystemRoleKey,
    get_system_role_template,
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
from models.users import User

from repositories.permissions import (
    get_permission_by_code,
)
from repositories.role_permissions import (
    get_role_permissions,
)
from repositories.roles import (
    get_system_role_by_key,
)

from services.authorization import (
    AuthorizationService,
)
from services.permissions import (
    sync_permissions,
)
from services.system_roles import (
    SystemRolePermissionUnavailableError,
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

    return company_id


async def get_permission_map(
    session: AsyncSession,
    *,
    role_id: int,
) -> dict[
    str,
    PermissionScope,
]:
    rows = await get_role_permissions(
        session,
        role_id,
    )

    return {
        permission.code: scope
        for permission, scope
        in rows
    }


async def get_role_permission_ids(
    session: AsyncSession,
    *,
    role_id: int,
) -> list[int]:
    stmt = (
        select(RolePermission.id)
        .where(
            RolePermission.role_id
            == role_id
        )
        .order_by(
            RolePermission.id.asc()
        )
    )

    result = await session.execute(
        stmt
    )

    return list(
        result.scalars().all()
    )


@pytest.mark.asyncio
async def test_sync_applies_exact_permission_template_to_every_system_role(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_id = (
        await create_ready_company(
            db_session
        )
    )

    roles = (
        await sync_system_roles_for_company(
            db_session,
            company_id=company_id,
        )
    )

    for role in roles:
        template = (
            get_system_role_template(
                role.system_key
            )
        )

        assert template is not None

        actual = await get_permission_map(
            db_session,
            role_id=role.id,
        )

        expected = {
            item.code.value: item.scope
            for item
            in template.permissions
        }

        assert actual == expected


@pytest.mark.asyncio
async def test_permission_sync_is_idempotent(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_id = (
        await create_ready_company(
            db_session
        )
    )

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
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

    first_ids = (
        await get_role_permission_ids(
            db_session,
            role_id=administrator.id,
        )
    )

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
    )

    second_ids = (
        await get_role_permission_ids(
            db_session,
            role_id=administrator.id,
        )
    )

    assert second_ids == first_ids


@pytest.mark.asyncio
async def test_sync_removes_extra_permission_from_system_role(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_id = (
        await create_ready_company(
            db_session
        )
    )

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
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

    temporary_permission = Permission(
        code="temporary.test",
        name="Temporary",
        module="test",
    )

    db_session.add(
        temporary_permission
    )

    await db_session.flush()

    db_session.add(
        RolePermission(
            role_id=employee.id,
            permission_id=(
                temporary_permission.id
            ),
            scope=PermissionScope.COMPANY,
        )
    )

    await db_session.commit()

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
    )

    permissions = await get_permission_map(
        db_session,
        role_id=employee.id,
    )

    assert (
        "temporary.test"
        not in permissions
    )


@pytest.mark.asyncio
async def test_sync_restores_template_permission_scope(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_id = (
        await create_ready_company(
            db_session
        )
    )

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
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

    tasks_read = (
        await get_permission_by_code(
            db_session,
            "tasks.read",
        )
    )

    assert employee is not None
    assert tasks_read is not None

    stmt = (
        select(RolePermission)
        .where(
            RolePermission.role_id
            == employee.id,

            RolePermission.permission_id
            == tasks_read.id,
        )
    )

    result = await db_session.execute(
        stmt
    )

    role_permission = (
        result.scalar_one()
    )

    role_permission.scope = (
        PermissionScope.COMPANY
    )

    await db_session.commit()

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
    )

    permissions = await get_permission_map(
        db_session,
        role_id=employee.id,
    )

    assert permissions[
        "tasks.read"
    ] == PermissionScope.SELF


@pytest.mark.asyncio
async def test_sync_rejects_unavailable_template_permission(
    db_session: AsyncSession,
    clean_test_redis,
):
    await sync_permissions(
        db_session
    )

    permission = (
        await get_permission_by_code(
            db_session,
            "tasks.read",
        )
    )

    assert permission is not None

    permission.is_active = False

    company = Company(
        name="Main Company",
    )

    db_session.add(
        company
    )

    await db_session.flush()

    company_id = company.id

    await db_session.commit()

    with pytest.raises(
        SystemRolePermissionUnavailableError
    ) as exc:
        await sync_system_roles_for_company(
            db_session,
            company_id=company_id,
        )

    assert (
        "tasks.read"
        in exc.value.permission_codes
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

    assert administrator is None


@pytest.mark.asyncio
async def test_permission_sync_invalidates_role_authorization_cache(
    db_session: AsyncSession,
    clean_test_redis,
):
    company_id = (
        await create_ready_company(
            db_session
        )
    )

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
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

    tasks_read = (
        await get_permission_by_code(
            db_session,
            "tasks.read",
        )
    )

    assert employee is not None
    assert tasks_read is not None

    user = User(
        username="system-role-cache-user",
        password_hash="test",
    )

    db_session.add(
        user
    )

    await db_session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company_id,
    )

    db_session.add(
        membership
    )

    await db_session.flush()

    membership_id = membership.id

    db_session.add(
        MembershipRole(
            company_membership_id=(
                membership_id
            ),
            role_id=employee.id,
        )
    )

    stmt = (
        select(RolePermission)
        .where(
            RolePermission.role_id
            == employee.id,

            RolePermission.permission_id
            == tasks_read.id,
        )
    )

    result = await db_session.execute(
        stmt
    )

    role_permission = (
        result.scalar_one()
    )

    #
    # Портим source of truth в DB.
    #
    role_permission.scope = (
        PermissionScope.COMPANY
    )

    await db_session.commit()

    authorization = AuthorizationService(
        db_session
    )

    cached = (
        await authorization.get_effective_permissions(
            company_id=company_id,
            company_membership_id=(
                membership_id
            ),
        )
    )

    assert cached[
        "tasks.read"
    ] == PermissionScope.COMPANY

    #
    # Sync возвращает SELF и обязан удалить
    # старый Redis cache.
    #
    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
    )

    refreshed = (
        await authorization.get_effective_permissions(
            company_id=company_id,
            company_membership_id=(
                membership_id
            ),
        )
    )

    assert refreshed[
        "tasks.read"
    ] == PermissionScope.SELF