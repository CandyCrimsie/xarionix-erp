import pytest

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.security.password import (
    hash_password,
)

from repositories.company import (
    create_company,
    get_companies,
    get_company_by_id,
)
from repositories.company_memberships import (
    get_company_membership_by_id,
)
from repositories.users import (
    create_user,
    get_user_by_id,
    get_user_by_username,
)

from services.company_memberships import (
    update_company_membership,
)


async def initialize_and_login(
    api_client: AsyncClient,
) -> tuple[
    dict,
    dict,
]:
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

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": "password123",
        },
    )

    assert login_response.status_code == 200

    return (
        setup_response.json(),
        login_response.json(),
    )


@pytest.mark.asyncio
async def test_inconsistent_database_does_not_allow_setup(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    await create_user(
        db_session,
        username="orphan-user",
        password_hash=hash_password(
            "password123"
        ),
    )

    await db_session.commit()

    status_response = await api_client.get(
        "/api/v1/setup/status"
    )

    assert status_response.status_code == 200

    assert status_response.json() == {
        "state": "inconsistent",
        "setup_allowed": False,
    }

    setup_response = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "Attacker Company",
            },
            "administrator": {
                "username": "attacker-admin",
                "password": "password123",
            },
        },
    )

    assert setup_response.status_code == 409

    assert setup_response.json() == {
        "detail": {
            "message": (
                "Installation is not allowed"
            ),
            "state": "inconsistent",
        },
    }

    companies = await get_companies(
        db_session
    )

    assert companies == []

    attacker = await get_user_by_username(
        db_session,
        "attacker-admin",
    )

    assert attacker is None


@pytest.mark.asyncio
async def test_disabling_initial_administrator_does_not_reopen_setup(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    setup_response = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "Main Company",
            },
            "administrator": {
                "username": "admin",
                "password": "password123",
            },
        },
    )

    assert setup_response.status_code == 201

    setup = setup_response.json()

    user = await get_user_by_id(
        db_session,
        setup["user_id"],
    )

    assert user is not None

    user.is_active = False

    await db_session.commit()

    status_response = await api_client.get(
        "/api/v1/setup/status"
    )

    assert status_response.status_code == 200

    assert status_response.json() == {
        "state": "inconsistent",
        "setup_allowed": False,
    }

    second_setup = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "Second Company",
            },
            "administrator": {
                "username": "new-admin",
                "password": "password123",
            },
        },
    )

    assert second_setup.status_code == 409

    assert second_setup.json() == {
        "detail": {
            "message": (
                "Installation is not allowed"
            ),
            "state": "inconsistent",
        },
    }

    new_admin = await get_user_by_username(
        db_session,
        "new-admin",
    )

    assert new_admin is None


@pytest.mark.asyncio
async def test_administrator_cannot_use_company_without_membership(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = await initialize_and_login(
        api_client
    )

    foreign_company = await create_company(
        db_session,
        name="Foreign Company",
        short_name="FOREIGN",
        parent_id=None,
    )

    foreign_company_id = (
        foreign_company.id
    )

    await db_session.commit()

    response = await api_client.get(
        "/api/v1/me/permissions",
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
            "X-Company-Id": str(
                foreign_company_id
            ),
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Company access denied",
    }

    companies_response = (
        await api_client.get(
            "/api/v1/me/companies",
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{login['access_token']}"
                ),
            },
        )
    )

    assert (
        companies_response.status_code
        == 200
    )

    companies = (
        companies_response.json()
    )

    assert {
        company["id"]
        for company in companies
    } == {
        setup["company_id"]
    }


@pytest.mark.asyncio
async def test_inactive_membership_blocks_company_access(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = await initialize_and_login(
        api_client
    )

    membership = (
        await get_company_membership_by_id(
            db_session,
            setup["membership_id"],
        )
    )

    assert membership is not None

    await update_company_membership(
        db_session,
        company_id=setup["company_id"],
        membership_id=membership.id,
        is_active=False,
    )

    permissions_response = (
        await api_client.get(
            "/api/v1/me/permissions",
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{login['access_token']}"
                ),
                "X-Company-Id": str(
                    setup["company_id"]
                ),
            },
        )
    )

    assert (
        permissions_response.status_code
        == 403
    )

    assert permissions_response.json() == {
        "detail": "Company access denied",
    }

    companies_response = (
        await api_client.get(
            "/api/v1/me/companies",
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{login['access_token']}"
                ),
            },
        )
    )

    assert (
        companies_response.status_code
        == 200
    )

    assert companies_response.json() == []


@pytest.mark.asyncio
async def test_inactive_company_blocks_company_access(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = await initialize_and_login(
        api_client
    )

    company = await get_company_by_id(
        db_session,
        setup["company_id"],
    )

    assert company is not None

    company.is_active = False

    await db_session.commit()

    response = await api_client.get(
        "/api/v1/me/permissions",
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
            "X-Company-Id": str(
                setup["company_id"]
            ),
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Company access denied",
    }

    companies_response = (
        await api_client.get(
            "/api/v1/me/companies",
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{login['access_token']}"
                ),
            },
        )
    )

    assert (
        companies_response.status_code
        == 200
    )

    assert companies_response.json() == []


@pytest.mark.asyncio
async def test_disabled_user_cannot_use_existing_session(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = await initialize_and_login(
        api_client
    )

    user = await get_user_by_id(
        db_session,
        setup["user_id"],
    )

    assert user is not None

    user.is_active = False

    await db_session.commit()

    response = await api_client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "User is disabled",
    }


@pytest.mark.asyncio
async def test_disabled_user_cannot_refresh_session(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, _ = await initialize_and_login(
        api_client
    )

    user = await get_user_by_id(
        db_session,
        setup["user_id"],
    )

    assert user is not None

    user.is_active = False

    await db_session.commit()

    response = await api_client.post(
        "/api/v1/auth/refresh"
    )

    assert response.status_code == 401

    assert response.json() == {
        "detail": "User is not available",
    }