import pytest

from httpx import AsyncClient
from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.permissions.codes import (
    PERMISSION_DEFINITIONS,
)
from core.system_roles import (
    SYSTEM_ROLE_TEMPLATES,
)

from models.company_memberships import (
    CompanyMembership,
)
from models.users import User

from repositories.company import (
    get_companies,
)
from repositories.company_memberships import (
    get_company_membership_by_id,
)
from repositories.membership_roles import (
    get_membership_roles,
)
from repositories.roles import (
    get_company_roles,
)
from repositories.users import (
    get_user_by_id,
)

from services.authorization_bootstrap import (
    sync_authorization_baseline,
)


async def initialize_installation_via_api(
    api_client: AsyncClient,
) -> dict:
    response = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "Main Company",
                "short_name": "MAIN",
            },
            "administrator": {
                "username": "admin",
                "password": "password123",
            },
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_startup_authorization_bootstrap_does_not_consume_first_run(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    #
    # Имитируем lifespan на совершенно
    # новой установке.
    #
    synchronized = (
        await sync_authorization_baseline(
            db_session
        )
    )

    #
    # Компаний ещё нет, поэтому
    # system roles создавать пока не для кого.
    #
    assert synchronized == {}

    status_response = await api_client.get(
        "/api/v1/setup/status"
    )

    assert status_response.status_code == 200

    assert status_response.json() == {
        "state": "ready",
        "setup_allowed": True,
    }

    #
    # Несмотря на уже созданный permission
    # catalog, first-run должен нормально
    # завершиться.
    #
    setup_response = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "Main Company",
                "short_name": "MAIN",
            },
            "administrator": {
                "username": "admin",
                "password": "password123",
            },
        },
    )

    assert setup_response.status_code == 201

    final_status = await api_client.get(
        "/api/v1/setup/status"
    )

    assert final_status.status_code == 200

    assert final_status.json() == {
        "state": "installed",
        "setup_allowed": False,
    }


@pytest.mark.asyncio
async def test_restart_authorization_bootstrap_preserves_installed_system(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup = (
        await initialize_installation_via_api(
            api_client
        )
    )

    company_id = setup[
        "company_id"
    ]

    user_id = setup[
        "user_id"
    ]

    membership_id = setup[
        "membership_id"
    ]

    administrator_role_id = setup[
        "administrator_role_id"
    ]

    #
    # Запоминаем system-role identities
    # ДО рестарта.
    #
    roles_before = await get_company_roles(
        db_session,
        company_id,
    )

    system_role_ids_before = {
        role.system_key: role.id
        for role in roles_before
        if role.is_system
    }

    assert len(
        system_role_ids_before
    ) == len(
        SYSTEM_ROLE_TEMPLATES
    )

    #
    # Имитируем следующий запуск приложения.
    #
    synchronized = (
        await sync_authorization_baseline(
            db_session
        )
    )

    assert set(
        synchronized
    ) == {
        company_id,
    }

    #
    # Company не продублировалась.
    #
    companies = await get_companies(
        db_session
    )

    assert len(companies) == 1

    assert (
        companies[0].id
        == company_id
    )

    #
    # User не продублировался.
    #
    user_count = await db_session.scalar(
        select(
            func.count(User.id)
        )
    )

    assert user_count == 1

    user = await get_user_by_id(
        db_session,
        user_id,
    )

    assert user is not None
    assert user.username == "admin"

    #
    # Membership тоже должна остаться
    # ровно одна и с тем же ID.
    #
    membership_count = (
        await db_session.scalar(
            select(
                func.count(
                    CompanyMembership.id
                )
            )
        )
    )

    assert membership_count == 1

    membership = (
        await get_company_membership_by_id(
            db_session,
            membership_id,
        )
    )

    assert membership is not None

    assert (
        membership.user_id
        == user_id
    )

    assert (
        membership.company_id
        == company_id
    )

    assert membership.is_active is True

    #
    # System-role identities должны быть
    # стабильными после повторного sync.
    #
    roles_after = await get_company_roles(
        db_session,
        company_id,
    )

    system_roles_after = {
        role.system_key: role
        for role in roles_after
        if role.is_system
    }

    assert set(
        system_roles_after
    ) == {
        template.key.value
        for template
        in SYSTEM_ROLE_TEMPLATES
    }

    system_role_ids_after = {
        key: role.id
        for key, role
        in system_roles_after.items()
    }

    assert (
        system_role_ids_after
        == system_role_ids_before
    )

    assert (
        administrator_role_id
        in system_role_ids_after.values()
    )

    #
    # Первый пользователь всё ещё имеет
    # ровно Administrator role.
    #
    membership_roles = (
        await get_membership_roles(
            db_session,
            membership_id,
        )
    )

    assert {
        role.id
        for role
        in membership_roles
    } == {
        administrator_role_id,
    }

    #
    # И installer после рестарта
    # по-прежнему закрыт.
    #
    status_response = await api_client.get(
        "/api/v1/setup/status"
    )

    assert status_response.status_code == 200

    assert status_response.json() == {
        "state": "installed",
        "setup_allowed": False,
    }


    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": "password123",
        },
    )

    assert login_response.status_code == 200

    access_token = (
        login_response.json()[
            "access_token"
        ]
    )

    permissions_response = (
        await api_client.get(
            "/api/v1/me/permissions",
            headers={
                "Authorization": (
                    f"Bearer {access_token}"
                ),
                "X-Company-Id": str(
                    company_id
                ),
            },
        )
    )

    assert (
        permissions_response.status_code
        == 200
    )

    permissions = (
        permissions_response.json()
    )

    expected_codes = {
        definition.code.value
        for definition
        in PERMISSION_DEFINITIONS
    }

    assert set(
        permissions["permissions"]
    ) == expected_codes

    assert set(
        permissions["scopes"]
    ) == expected_codes

    assert all(
        scope == "company"
        for scope
        in permissions[
            "scopes"
        ].values()
    )