from uuid import uuid4

import pytest

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.config import config
from core.permissions.codes import (
    PERMISSION_DEFINITIONS,
)
from core.security.jwt import (
    decode_access_token,
)

from services.sessions import (
    get_auth_session,
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
                "username": "Admin",
                "password": "password123",
            },
        },
    )

    assert setup_response.status_code == 201

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": "Admin",
            "password": "password123",
        },
    )

    assert login_response.status_code == 200

    return (
        setup_response.json(),
        login_response.json(),
    )


@pytest.mark.asyncio
async def test_initial_administrator_can_login_after_setup(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = await initialize_and_login(
        api_client
    )

    assert login["token_type"] == "bearer"
    assert login["expires_in"] > 0

    access_token = login[
        "access_token"
    ]

    token_data = decode_access_token(
        access_token
    )

    assert (
        token_data.user_id
        == setup["user_id"]
    )

    auth_session = await get_auth_session(
        token_data.session_id
    )

    assert auth_session is not None

    assert (
        auth_session.user_id
        == setup["user_id"]
    )

    refresh_cookie = (
        api_client.cookies.get(
            config.REFRESH_COOKIE_NAME
        )
    )

    assert refresh_cookie is not None


@pytest.mark.asyncio
async def test_initial_administrator_access_token_authenticates_user(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = await initialize_and_login(
        api_client
    )

    response = await api_client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["id"]
        == setup["user_id"]
    )

    assert body["username"] == "admin"
    assert body["is_active"] is True


@pytest.mark.asyncio
async def test_initial_administrator_can_access_created_company(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = await initialize_and_login(
        api_client
    )

    response = await api_client.get(
        "/api/v1/me/companies",
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
        },
    )

    assert response.status_code == 200

    companies = response.json()

    assert len(companies) == 1

    assert (
        companies[0]["id"]
        == setup["company_id"]
    )

    assert (
        companies[0]["name"]
        == "Main Company"
    )

    assert (
        companies[0]["short_name"]
        == "MAIN"
    )


@pytest.mark.asyncio
async def test_initial_administrator_permissions_require_company_context(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    _, login = await initialize_and_login(
        api_client
    )

    response = await api_client.get(
        "/api/v1/me/permissions",
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": (
            "X-Company-Id header "
            "is required"
        ),
    }


@pytest.mark.asyncio
async def test_initial_administrator_has_full_company_permissions(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = await initialize_and_login(
        api_client
    )

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

    assert response.status_code == 200

    body = response.json()

    expected_codes = {
        definition.code.value
        for definition
        in PERMISSION_DEFINITIONS
    }

    assert set(
        body["permissions"]
    ) == expected_codes

    assert set(
        body["scopes"]
    ) == expected_codes

    assert all(
        scope == "company"
        for scope
        in body["scopes"].values()
    )


@pytest.mark.asyncio
async def test_initial_administrator_can_refresh_session(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, _ = await initialize_and_login(
        api_client
    )

    old_refresh_token = (
        api_client.cookies.get(
            config.REFRESH_COOKIE_NAME
        )
    )

    assert old_refresh_token is not None

    response = await api_client.post(
        "/api/v1/auth/refresh"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["token_type"] == "bearer"

    token_data = decode_access_token(
        body["access_token"]
    )

    assert (
        token_data.user_id
        == setup["user_id"]
    )

    new_refresh_token = (
        api_client.cookies.get(
            config.REFRESH_COOKIE_NAME
        )
    )

    assert new_refresh_token is not None

    assert (
        new_refresh_token
        != old_refresh_token
    )


@pytest.mark.asyncio
async def test_invalid_refresh_token_returns_401(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    response = await api_client.post(
        "/api/v1/auth/refresh",
        headers={
            "Cookie": (
                f"{config.REFRESH_COOKIE_NAME}"
                "=invalid-refresh-token"
            ),
        },
    )

    assert response.status_code == 401

    assert response.json() == {
        "detail": (
            "Invalid refresh token"
        ),
    }


@pytest.mark.asyncio
async def test_removing_unknown_session_returns_404(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    _, login = await initialize_and_login(
        api_client
    )

    response = await api_client.delete(
        (
            "/api/v1/auth/sessions/"
            f"{uuid4()}"
        ),
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Session not found",
    }