import hashlib

from datetime import (
    datetime,
    timedelta,
    timezone,
)

import pytest

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.company_invitations import (
    CompanyInvitation,
)
from models.company_memberships import (
    CompanyMembership,
)
from services.auth import register_user


async def initialize_and_login_admin(
    api_client: AsyncClient,
) -> tuple[dict, str]:
    setup_response = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "Main Company",
                "short_name": "MAIN",
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
        login_response.json()[
            "access_token"
        ],
    )


def company_headers(
    token: str,
    company_id: int,
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": str(company_id),
    }


@pytest.mark.asyncio
async def test_company_administrator_can_create_and_list_invitation_without_exposing_hash(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, token = (
        await initialize_and_login_admin(
            api_client
        )
    )

    company_id = setup["company_id"]

    response = await api_client.post(
        (
            f"/api/v1/companies/{company_id}"
            "/invitations"
        ),
        json={
            "expires_in_hours": 24,
        },
        headers=company_headers(
            token,
            company_id,
        ),
    )

    assert response.status_code == 201

    created = response.json()
    raw_token = created["token"]

    assert len(raw_token) >= 32
    assert created["status"] == "pending"
    assert created["token_prefix"] == raw_token[:8]
    assert "token_hash" not in created

    result = await db_session.execute(
        select(CompanyInvitation)
    )

    invitation = result.scalar_one()

    assert invitation.token_hash == (
        hashlib.sha256(
            raw_token.encode("utf-8")
        ).hexdigest()
    )
    assert invitation.token_hash != raw_token

    list_response = await api_client.get(
        (
            f"/api/v1/companies/{company_id}"
            "/invitations?scope=mine"
        ),
        headers=company_headers(
            token,
            company_id,
        ),
    )

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    listed = list_response.json()[0]

    assert listed["id"] == created["id"]
    assert listed["status"] == "pending"
    assert listed["created_by_username"] == "admin"
    assert "token" not in listed
    assert "token_hash" not in listed


@pytest.mark.asyncio
async def test_invitation_mine_and_all_scopes_are_separated(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, token = (
        await initialize_and_login_admin(
            api_client
        )
    )

    company_id = setup["company_id"]

    own_response = await api_client.post(
        (
            f"/api/v1/companies/{company_id}"
            "/invitations"
        ),
        json={},
        headers=company_headers(
            token,
            company_id,
        ),
    )

    assert own_response.status_code == 201

    other_user = await register_user(
        db_session,
        username="other-manager",
        password="password123",
    )

    other_membership = CompanyMembership(
        user_id=other_user.id,
        company_id=company_id,
    )

    db_session.add(other_membership)
    await db_session.flush()

    db_session.add(
        CompanyInvitation(
            company_id=company_id,
            created_by_membership_id=(
                other_membership.id
            ),
            token_hash="b" * 64,
            token_prefix="other123",
            expires_at=(
                datetime.now(timezone.utc)
                + timedelta(hours=12)
            ),
        )
    )

    await db_session.commit()

    mine_response = await api_client.get(
        (
            f"/api/v1/companies/{company_id}"
            "/invitations?scope=mine"
        ),
        headers=company_headers(
            token,
            company_id,
        ),
    )

    all_response = await api_client.get(
        (
            f"/api/v1/companies/{company_id}"
            "/invitations?scope=all"
        ),
        headers=company_headers(
            token,
            company_id,
        ),
    )

    assert mine_response.status_code == 200
    assert all_response.status_code == 200

    assert len(mine_response.json()) == 1
    assert len(all_response.json()) == 2

    assert {
        item["created_by_username"]
        for item in all_response.json()
    } == {
        "admin",
        "other-manager",
    }


@pytest.mark.asyncio
async def test_user_without_members_manage_cannot_create_invitation(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, _ = (
        await initialize_and_login_admin(
            api_client
        )
    )

    company_id = setup["company_id"]

    user = await register_user(
        db_session,
        username="ordinary-user",
        password="password123",
    )

    db_session.add(
        CompanyMembership(
            user_id=user.id,
            company_id=company_id,
        )
    )
    await db_session.commit()

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": "ordinary-user",
            "password": "password123",
        },
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/{company_id}"
            "/invitations"
        ),
        json={},
        headers=company_headers(
            login_response.json()[
                "access_token"
            ],
            company_id,
        ),
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Permission denied",
    }


@pytest.mark.asyncio
async def test_company_context_cannot_manage_other_company_invitations(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, token = (
        await initialize_and_login_admin(
            api_client
        )
    )

    company_a_id = setup["company_id"]

    company_b_response = await api_client.post(
        "/api/v1/companies",
        json={
            "name": "Company B",
            "short_name": "B",
        },
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert company_b_response.status_code == 201

    company_b_id = company_b_response.json()["id"]

    response = await api_client.post(
        (
            f"/api/v1/companies/{company_b_id}"
            "/invitations"
        ),
        json={},
        headers=company_headers(
            token,
            company_a_id,
        ),
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Company not found",
    }


@pytest.mark.asyncio
async def test_pending_invitation_can_be_revoked_idempotently(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, token = (
        await initialize_and_login_admin(
            api_client
        )
    )

    company_id = setup["company_id"]
    headers = company_headers(
        token,
        company_id,
    )

    create_response = await api_client.post(
        (
            f"/api/v1/companies/{company_id}"
            "/invitations"
        ),
        json={},
        headers=headers,
    )

    invitation_id = create_response.json()["id"]

    url = (
        f"/api/v1/companies/{company_id}"
        f"/invitations/{invitation_id}"
        "/revoke"
    )

    first_response = await api_client.post(
        url,
        headers=headers,
    )

    second_response = await api_client.post(
        url,
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    assert first_response.json()["status"] == (
        "revoked"
    )
    assert second_response.json()["status"] == (
        "revoked"
    )


@pytest.mark.asyncio
async def test_expired_invitation_cannot_be_revoked(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, token = (
        await initialize_and_login_admin(
            api_client
        )
    )

    company_id = setup["company_id"]
    headers = company_headers(
        token,
        company_id,
    )

    create_response = await api_client.post(
        (
            f"/api/v1/companies/{company_id}"
            "/invitations"
        ),
        json={},
        headers=headers,
    )

    invitation_id = create_response.json()["id"]

    invitation = await db_session.get(
        CompanyInvitation,
        invitation_id,
    )

    assert invitation is not None

    invitation.expires_at = (
        datetime.now(timezone.utc)
        - timedelta(minutes=1)
    )

    await db_session.commit()

    response = await api_client.post(
        (
            f"/api/v1/companies/{company_id}"
            f"/invitations/{invitation_id}"
            "/revoke"
        ),
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Expired invitation cannot "
            "be revoked"
        ),
    }
