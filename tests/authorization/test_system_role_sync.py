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
)

from models.company import Company
from models.permissions import Permission
from models.role_permissions import (
    RolePermission,
)
from models.roles import Role

from services.system_roles import (
    SystemRoleCompanyNotFoundError,
    SystemRoleNameConflictError,
    sync_system_roles,
    sync_system_roles_for_company,
)


async def create_company(
    session: AsyncSession,
    *,
    name: str,
) -> Company:
    company = Company(
        name=name,
    )

    session.add(
        company
    )

    await session.flush()

    return company


async def get_company_system_roles(
    session: AsyncSession,
    *,
    company_id: int,
) -> list[Role]:
    stmt = (
        select(Role)
        .where(
            Role.company_id
            == company_id,

            Role.is_system.is_(True),
        )
        .order_by(
            Role.system_key.asc()
        )
    )

    result = await session.execute(
        stmt
    )

    return list(
        result.scalars().all()
    )


@pytest.mark.asyncio
async def test_sync_creates_all_system_roles(
    db_session: AsyncSession,
):
    company = await create_company(
        db_session,
        name="Main Company",
    )

    await db_session.commit()

    roles = (
        await sync_system_roles_for_company(
            db_session,
            company_id=company.id,
        )
    )

    assert len(roles) == len(
        SYSTEM_ROLE_TEMPLATES
    )

    roles_by_key = {
        role.system_key: role
        for role in roles
    }

    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        role = roles_by_key[
            template.key.value
        ]

        assert (
            role.name
            == template.name
        )

        assert (
            role.description
            == template.description
        )

        assert role.is_system is True
        assert role.is_active is True


@pytest.mark.asyncio
async def test_sync_is_idempotent(
    db_session: AsyncSession,
):
    company = await create_company(
        db_session,
        name="Main Company",
    )

    await db_session.commit()

    first = (
        await sync_system_roles_for_company(
            db_session,
            company_id=company.id,
        )
    )

    first_ids = {
        role.system_key: role.id
        for role in first
    }

    second = (
        await sync_system_roles_for_company(
            db_session,
            company_id=company.id,
        )
    )

    second_ids = {
        role.system_key: role.id
        for role in second
    }

    assert second_ids == first_ids

    stored = (
        await get_company_system_roles(
            db_session,
            company_id=company.id,
        )
    )

    assert len(stored) == len(
        SYSTEM_ROLE_TEMPLATES
    )


@pytest.mark.asyncio
async def test_sync_restores_system_role_metadata(
    db_session: AsyncSession,
):
    company = await create_company(
        db_session,
        name="Main Company",
    )

    await db_session.commit()

    roles = (
        await sync_system_roles_for_company(
            db_session,
            company_id=company.id,
        )
    )

    administrator = next(
        role
        for role in roles
        if (
            role.system_key
            == SystemRoleKey.ADMINISTRATOR.value
        )
    )

    original_id = administrator.id

    administrator.name = (
        "Renamed Administrator"
    )
    administrator.description = (
        "Modified description"
    )
    administrator.is_active = False

    await db_session.commit()

    synced = (
        await sync_system_roles_for_company(
            db_session,
            company_id=company.id,
        )
    )

    administrator = next(
        role
        for role in synced
        if (
            role.system_key
            == SystemRoleKey.ADMINISTRATOR.value
        )
    )

    template = next(
        template
        for template
        in SYSTEM_ROLE_TEMPLATES
        if (
            template.key
            == SystemRoleKey.ADMINISTRATOR
        )
    )

    assert administrator.id == (
        original_id
    )

    assert (
        administrator.name
        == template.name
    )

    assert (
        administrator.description
        == template.description
    )

    assert administrator.is_active is True


@pytest.mark.asyncio
async def test_sync_rejects_custom_role_with_system_role_name(
    db_session: AsyncSession,
):
    company = await create_company(
        db_session,
        name="Main Company",
    )

    custom_role = Role(
        company_id=company.id,
        name="Administrator",
        description="Custom administrator",
        is_system=False,
        system_key=None,
    )

    db_session.add(
        custom_role
    )

    await db_session.flush()

    #
    # Сохраняем scalar IDs ДО rollback.
    #
    company_id = company.id
    custom_role_id = custom_role.id

    await db_session.commit()

    with pytest.raises(
        SystemRoleNameConflictError
    ) as exc:
        await sync_system_roles_for_company(
            db_session,
            company_id=company_id,
        )

    assert exc.value.company_id == (
        company_id
    )

    assert exc.value.role_name == (
        "Administrator"
    )

    assert (
        exc.value.existing_role_id
        == custom_role_id
    )

    system_roles = (
        await get_company_system_roles(
            db_session,
            company_id=company_id,
        )
    )

    assert system_roles == []


@pytest.mark.asyncio
async def test_sync_rolls_back_partial_system_role_creation_on_conflict(
    db_session: AsyncSession,
):
    company = await create_company(
        db_session,
        name="Main Company",
    )

    company_id = company.id

    #
    # Administrator будет создан первым,
    # а Company Manager вызовет конфликт.
    #
    db_session.add(
        Role(
            company_id=company_id,
            name="Company Manager",
            description="Custom role",
            is_system=False,
            system_key=None,
        )
    )

    await db_session.commit()

    with pytest.raises(
        SystemRoleNameConflictError
    ):
        await sync_system_roles_for_company(
            db_session,
            company_id=company_id,
        )

    system_roles = (
        await get_company_system_roles(
            db_session,
            company_id=company_id,
        )
    )

    assert system_roles == []


@pytest.mark.asyncio
async def test_sync_all_companies_creates_roles_for_each_company(
    db_session: AsyncSession,
):
    company_a = await create_company(
        db_session,
        name="Company A",
    )

    company_b = await create_company(
        db_session,
        name="Company B",
    )

    await db_session.commit()

    result = await sync_system_roles(
        db_session
    )

    assert set(
        result
    ) == {
        company_a.id,
        company_b.id,
    }

    assert len(
        result[company_a.id]
    ) == len(
        SYSTEM_ROLE_TEMPLATES
    )

    assert len(
        result[company_b.id]
    ) == len(
        SYSTEM_ROLE_TEMPLATES
    )

    admin_a = next(
        role
        for role
        in result[company_a.id]
        if (
            role.system_key
            == SystemRoleKey.ADMINISTRATOR.value
        )
    )

    admin_b = next(
        role
        for role
        in result[company_b.id]
        if (
            role.system_key
            == SystemRoleKey.ADMINISTRATOR.value
        )
    )

    assert admin_a.id != admin_b.id


@pytest.mark.asyncio
async def test_sync_missing_company_is_rejected(
    db_session: AsyncSession,
):
    with pytest.raises(
        SystemRoleCompanyNotFoundError
    ):
        await sync_system_roles_for_company(
            db_session,
            company_id=999999999,
        )


@pytest.mark.asyncio
async def test_system_role_sync_does_not_modify_role_permissions(
    db_session: AsyncSession,
):
    company = await create_company(
        db_session,
        name="Main Company",
    )

    await db_session.commit()

    roles = (
        await sync_system_roles_for_company(
            db_session,
            company_id=company.id,
        )
    )

    employee = next(
        role
        for role in roles
        if (
            role.system_key
            == SystemRoleKey.EMPLOYEE.value
        )
    )

    permission = Permission(
        code="temporary.test",
        name="Temporary permission",
        module="test",
    )

    db_session.add(
        permission
    )

    await db_session.flush()

    custom_role_permission = (
        RolePermission(
            role_id=employee.id,
            permission_id=permission.id,
            scope=PermissionScope.COMPANY,
        )
    )

    db_session.add(
        custom_role_permission
    )

    await db_session.commit()

    await sync_system_roles_for_company(
        db_session,
        company_id=company.id,
    )

    stmt = (
        select(RolePermission)
        .where(
            RolePermission.role_id
            == employee.id,

            RolePermission.permission_id
            == permission.id,
        )
    )

    result = await db_session.execute(
        stmt
    )

    assert (
        result.scalar_one_or_none()
        is not None
    )