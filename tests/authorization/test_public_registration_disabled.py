import pytest

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from repositories.users import (
    get_user_by_username,
)


@pytest.mark.asyncio
async def test_public_registration_is_not_available_before_installation(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "username": "attacker",
            "password": "password123",
        },
    )

    assert response.status_code == 404

    user = await get_user_by_username(
        db_session,
        "attacker",
    )

    assert user is None


@pytest.mark.asyncio
async def test_public_registration_is_not_available_after_installation(
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

    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "username": "random-user",
            "password": "password123",
        },
    )

    assert response.status_code == 404

    user = await get_user_by_username(
        db_session,
        "random-user",
    )

    assert user is None


@pytest.mark.asyncio
async def test_first_user_can_still_be_created_through_setup(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    response = await api_client.post(
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

    assert response.status_code == 201

    user = await get_user_by_username(
        db_session,
        "admin",
    )

    assert user is not None


@pytest.mark.asyncio
async def test_public_registration_is_not_exposed_in_openapi(
    api_client: AsyncClient,
):
    response = await api_client.get(
        "/openapi.json"
    )

    assert response.status_code == 200

    paths = response.json()[
        "paths"
    ]

    assert (
        "/api/v1/auth/register"
        not in paths
    )