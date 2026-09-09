import pytest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.system_roles import (
    SYSTEM_ROLE_TEMPLATES,
    SystemRoleKey,
)

from models.company import Company
from models.role_delegations import (
    RoleDelegation,
)
from models.roles import Role

from repositories.role_delegations import (
    get_role_delegations,
)
from repositories.roles import (
    get_system_role_by_key,
)

from services.permissions import (
    sync_permissions,
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

    return company_id


async def get_system_roles_by_key(
    session: AsyncSession,
    *,
    company_id: int,
) -> dict[str, Role]:
    roles: dict[str, Role] = {}

    for key in SystemRoleKey:
        role = (
            await get_system_role_by_key(
                session,
                company_id=company_id,
                system_key=key.value,
            )
        )

        assert role is not None

        roles[key.value] = role

    return roles


async def get_delegation_ids(
    session: AsyncSession,
    *,
    manager_role_id: int,
) -> set[int]:
    rows = await get_role_delegations(
        session,
        manager_role_id=manager_role_id,
    )

    return {
        row.assignable_role_id
        for row in rows
    }


@pytest.mark.asyncio
async def test_sync_applies_exact_system_role_delegation_matrix(
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

    roles = await get_system_roles_by_key(
        db_session,
        company_id=company_id,
    )

    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        manager = roles[
            template.key.value
        ]

        actual = await get_delegation_ids(
            db_session,
            manager_role_id=manager.id,
        )

        expected = {
            roles[key.value].id
            for key
            in template.assignable_role_keys
        }

        assert actual == expected


@pytest.mark.asyncio
async def test_administrator_can_delegate_administrator(
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

    assignable_ids = (
        await get_delegation_ids(
            db_session,
            manager_role_id=(
                administrator.id
            ),
        )
    )

    assert (
        administrator.id
        in assignable_ids
    )


@pytest.mark.asyncio
async def test_sync_removes_extra_system_role_delegation(
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

    custom_role = Role(
        company_id=company_id,
        name="Custom Role",
        is_system=False,
        system_key=None,
    )

    db_session.add(
        custom_role
    )

    await db_session.flush()

    db_session.add(
        RoleDelegation(
            manager_role_id=employee.id,
            assignable_role_id=custom_role.id,
        )
    )

    await db_session.commit()

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
    )

    actual = await get_delegation_ids(
        db_session,
        manager_role_id=employee.id,
    )

    assert actual == set()


@pytest.mark.asyncio
async def test_sync_restores_missing_system_role_delegation(
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

    roles = await get_system_roles_by_key(
        db_session,
        company_id=company_id,
    )

    manager = roles[
        SystemRoleKey
        .DEPARTMENT_MANAGER
        .value
    ]

    employee = roles[
        SystemRoleKey.EMPLOYEE.value
    ]

    stmt = (
        select(RoleDelegation)
        .where(
            RoleDelegation.manager_role_id
            == manager.id,

            RoleDelegation.assignable_role_id
            == employee.id,
        )
    )

    result = await db_session.execute(
        stmt
    )

    delegation = result.scalar_one()

    await db_session.delete(
        delegation
    )

    await db_session.commit()

    assert (
        employee.id
        not in await get_delegation_ids(
            db_session,
            manager_role_id=manager.id,
        )
    )

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
    )

    assert (
        employee.id
        in await get_delegation_ids(
            db_session,
            manager_role_id=manager.id,
        )
    )


@pytest.mark.asyncio
async def test_system_role_delegation_sync_is_idempotent(
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

    stmt = (
        select(
            RoleDelegation.id
        )
        .where(
            RoleDelegation.manager_role_id
            == administrator.id
        )
        .order_by(
            RoleDelegation.id.asc()
        )
    )

    first_result = (
        await db_session.execute(
            stmt
        )
    )

    first_ids = list(
        first_result.scalars().all()
    )

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
    )

    second_result = (
        await db_session.execute(
            stmt
        )
    )

    second_ids = list(
        second_result.scalars().all()
    )

    assert second_ids == first_ids