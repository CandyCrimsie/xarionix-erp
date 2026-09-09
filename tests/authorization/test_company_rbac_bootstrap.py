import pytest

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.system_roles import (
    SYSTEM_ROLE_TEMPLATES,
    SystemRoleKey,
)

from repositories.company import (
    get_companies,
)
from repositories.role_delegations import (
    get_role_delegations,
)
from repositories.role_permissions import (
    get_role_permissions,
)
from repositories.roles import (
    get_system_role_by_key,
)

from schemas.company import (
    CompanyCreate,
)

from services.company import (
    create_new_company,
)
from services.permissions import (
    sync_permissions,
)
from services.system_roles import (
    SystemRolePermissionUnavailableError,
)


@pytest.mark.asyncio
async def test_new_company_receives_complete_system_role_baseline(
    db_session: AsyncSession,
    clean_test_redis,
):
    await sync_permissions(
        db_session
    )

    company = await create_new_company(
        db_session,
        CompanyCreate(
            name="New Company",
            short_name="NEW",
        ),
    )

    roles_by_key = {}

    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        role = (
            await get_system_role_by_key(
                db_session,
                company_id=company.id,
                system_key=(
                    template.key.value
                ),
            )
        )

        assert role is not None

        roles_by_key[
            template.key.value
        ] = role

        #
        # Проверяем permissions.
        #
        role_permissions = (
            await get_role_permissions(
                db_session,
                role.id,
            )
        )

        actual_permissions = {
            permission.code: scope
            for permission, scope
            in role_permissions
        }

        expected_permissions = {
            item.code.value: item.scope
            for item
            in template.permissions
        }

        assert (
            actual_permissions
            == expected_permissions
        )

    #
    # Проверяем delegations.
    #
    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        manager = roles_by_key[
            template.key.value
        ]

        rows = await get_role_delegations(
            db_session,
            manager_role_id=manager.id,
        )

        actual_ids = {
            row.assignable_role_id
            for row in rows
        }

        expected_ids = {
            roles_by_key[
                key.value
            ].id
            for key
            in template.assignable_role_keys
        }

        assert actual_ids == expected_ids


@pytest.mark.asyncio
async def test_company_creation_rolls_back_when_system_roles_cannot_be_provisioned(
    db_session: AsyncSession,
    clean_test_redis,
):
    #
    # sync_permissions специально
    # НЕ вызываем.
    #

    with pytest.raises(
        SystemRolePermissionUnavailableError
    ):
        await create_new_company(
            db_session,
            CompanyCreate(
                name="Broken Company",
            ),
        )

    companies = await get_companies(
        db_session
    )

    assert companies == []


@pytest.mark.asyncio
async def test_child_company_receives_independent_system_roles(
    db_session: AsyncSession,
    clean_test_redis,
):
    await sync_permissions(
        db_session
    )

    parent = await create_new_company(
        db_session,
        CompanyCreate(
            name="Parent Company",
        ),
    )

    child = await create_new_company(
        db_session,
        CompanyCreate(
            name="Child Company",
            parent_id=parent.id,
        ),
    )

    parent_admin = (
        await get_system_role_by_key(
            db_session,
            company_id=parent.id,
            system_key=(
                SystemRoleKey
                .ADMINISTRATOR
                .value
            ),
        )
    )

    child_admin = (
        await get_system_role_by_key(
            db_session,
            company_id=child.id,
            system_key=(
                SystemRoleKey
                .ADMINISTRATOR
                .value
            ),
        )
    )

    assert parent_admin is not None
    assert child_admin is not None

    assert (
        parent_admin.id
        != child_admin.id
    )

    assert (
        parent_admin.company_id
        == parent.id
    )

    assert (
        child_admin.company_id
        == child.id
    )