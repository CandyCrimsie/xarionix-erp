import pytest

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.installation import (
    InstallationState,
)

from repositories.company import (
    get_companies,
)
from repositories.membership_roles import (
    get_membership_roles,
)
from repositories.users import (
    get_user_by_username,
)

from services.installation import (
    get_installation_status,
)


@pytest.mark.asyncio
async def test_setup_status_is_ready_on_empty_database(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    response = await api_client.get(
        "/api/v1/setup/status"
    )

    assert response.status_code == 200

    assert response.json() == {
        "state": "ready",
        "setup_allowed": True,
        "has_users": False,
        "has_companies": False,
        "has_memberships": False,
        "has_administrator": False,
    }


@pytest.mark.asyncio
async def test_setup_initialize_creates_first_installation(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    response = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "Main Company",
                "short_name": "MAIN",
            },
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body[
        "state"
    ] == "installed"

    assert body[
        "company_name"
    ] == "Main Company"

    assert body[
        "username"
    ] == "admin"

    assert isinstance(
        body["company_id"],
        int,
    )

    assert isinstance(
        body["user_id"],
        int,
    )

    assert isinstance(
        body["membership_id"],
        int,
    )

    assert isinstance(
        body["administrator_role_id"],
        int,
    )

    installation_status = (
        await get_installation_status(
            db_session
        )
    )

    assert (
        installation_status.state
        == InstallationState.INSTALLED
    )

    user = await get_user_by_username(
        db_session,
        "admin",
    )

    assert user is not None

    assert (
        user.is_system_admin
        is True
    )

    roles = await get_membership_roles(
        db_session,
        body["membership_id"],
    )

    assert {
        role.id
        for role in roles
    } == {
        body[
            "administrator_role_id"
        ]
    }

    login_response = (
        await api_client.post(
            "/api/v1/auth/login",
            json={
                "username":
                    "admin",

                "password":
                    "password123",
            },
        )
    )


    assert (
        login_response.status_code
        == 200
    )

    wrong_login_response = (
        await api_client.post(
            "/api/v1/auth/login",
            json={
                "username":
                    "admin",

                "password":
                    "client-password123",
            },
        )
    )


    assert (
        wrong_login_response.status_code
        == 401
    )

    me_response = await api_client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": (
                f"Bearer "
                f"{login_response.json()['access_token']}"
            ),
        },
    )


    assert me_response.status_code == 200

    assert (
        me_response.json()[
            "is_system_admin"
        ]
        is True
    )


@pytest.mark.asyncio
async def test_setup_status_becomes_installed_after_initialization(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    initialize_response = (
        await api_client.post(
            "/api/v1/setup/initialize",
            json={
                "company": {
                    "name": (
                        "Main Company"
                    ),
                    "short_name": None,
                },
            },
        )
    )

    assert (
        initialize_response.status_code
        == 201
    )

    response = await api_client.get(
        "/api/v1/setup/status"
    )

    assert response.status_code == 200

    assert response.json() == {
        "state": "installed",
        "setup_allowed": False,
        "has_users": True,
        "has_companies": True,
        "has_memberships": True,
        "has_administrator": True,
    }


@pytest.mark.asyncio
async def test_setup_initialize_cannot_be_called_twice(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    first = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "Main Company",
            },
        },
    )

    assert first.status_code == 201

    second = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "Evil Company",
            },
        },
    )

    assert second.status_code == 409

    assert second.json() == {
        "detail": {
            "message": (
                "Installation is not allowed"
            ),
            "state": "installed",
        },
    }

    companies = await get_companies(
        db_session
    )

    assert len(companies) == 1

    second_user = (
        await get_user_by_username(
            db_session,
            "second-admin",
        )
    )

    assert second_user is None


@pytest.mark.asyncio
async def test_invalid_setup_payload_does_not_change_installation_state(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    response = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "   ",
            },
        },
    )

    assert response.status_code == 422

    installation_status = (
        await get_installation_status(
            db_session
        )
    )

    assert (
        installation_status.state
        == InstallationState.READY
    )

    assert (
        installation_status.setup_allowed
        is True
    )

    companies = await get_companies(
        db_session
    )

    assert companies == []