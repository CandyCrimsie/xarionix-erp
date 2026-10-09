import asyncio
import os

from datetime import datetime, timedelta, timezone

import pytest

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import config
from models.company import Company
from models.company_invitations import CompanyInvitation
from models.company_memberships import CompanyMembership
from models.users import User
from services.auth import register_user
from services.invitations import (
    InvitationAcceptedError,
    accept_invitation_for_new_user,
)


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
        login_response.json()["access_token"],
    )


def auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
    }


def company_headers(
    token: str,
    company_id: int,
) -> dict[str, str]:
    return {
        **auth_headers(token),
        "X-Company-Id": str(company_id),
    }


async def create_invitation(
    api_client: AsyncClient,
    *,
    access_token: str,
    company_id: int,
) -> dict:
    response = await api_client.post(
        f"/api/v1/companies/{company_id}/invitations",
        json={},
        headers=company_headers(
            access_token,
            company_id,
        ),
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_public_invitation_policy_comes_from_backend_config(
    api_client: AsyncClient,
):
    response = await api_client.get(
        "/api/v1/invitations/policy"
    )

    assert response.status_code == 200
    assert response.json() == {
        "default_expire_hours": (
            config.INVITATION_DEFAULT_EXPIRE_HOURS
        ),
        "max_expire_hours": (
            config.INVITATION_MAX_EXPIRE_HOURS
        ),
    }

    openapi_response = await api_client.get(
        "/openapi.json"
    )

    invitation_paths = {
        path
        for path in openapi_response.json()["paths"]
        if path.startswith("/api/v1/invitations")
    }

    assert invitation_paths == {
        "/api/v1/invitations/policy",
        "/api/v1/invitations/resolve",
        "/api/v1/invitations/accept",
        "/api/v1/invitations/accept-existing",
    }
    assert all(
        "{token}" not in path
        for path in invitation_paths
    )


@pytest.mark.asyncio
async def test_public_invitation_validation_returns_only_safe_data(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, access_token = (
        await initialize_and_login_admin(api_client)
    )

    created = await create_invitation(
        api_client,
        access_token=access_token,
        company_id=setup["company_id"],
    )

    response = await api_client.post(
        "/api/v1/invitations/resolve",
        json={
            "token": created["token"],
        },
    )

    assert response.status_code == 200
    assert created["token"] not in str(
        response.request.url
    )
    assert response.json() == {
        "company": {
            "name": "Main Company",
            "short_name": "MAIN",
        },
        "expires_at": created["expires_at"],
        "status": "pending",
    }


@pytest.mark.asyncio
async def test_inactive_company_invitation_cannot_be_resolved(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, access_token = (
        await initialize_and_login_admin(api_client)
    )

    created = await create_invitation(
        api_client,
        access_token=access_token,
        company_id=setup["company_id"],
    )

    company = await db_session.get(
        Company,
        setup["company_id"],
    )

    assert company is not None
    company.is_active = False
    await db_session.commit()

    response = await api_client.post(
        "/api/v1/invitations/resolve",
        json={
            "token": created["token"],
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Company is inactive or unavailable",
    }


@pytest.mark.asyncio
async def test_new_user_acceptance_is_atomic_and_cannot_be_reused(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, access_token = (
        await initialize_and_login_admin(api_client)
    )
    company_id = setup["company_id"]

    created = await create_invitation(
        api_client,
        access_token=access_token,
        company_id=company_id,
    )

    response = await api_client.post(
        "/api/v1/invitations/accept",
        json={
            "token": created["token"],
            "username": "  New.Employee  ",
            "password": "password123",
        },
    )

    assert response.status_code == 201
    assert created["token"] not in str(
        response.request.url
    )
    assert response.json()["user"]["username"] == (
        "new.employee"
    )
    assert response.json()["company_id"] == company_id

    user = (
        await db_session.execute(
            select(User).where(
                User.username == "new.employee"
            )
        )
    ).scalar_one()

    membership = (
        await db_session.execute(
            select(CompanyMembership).where(
                CompanyMembership.user_id == user.id,
                CompanyMembership.company_id == company_id,
            )
        )
    ).scalar_one()

    invitation = await db_session.get(
        CompanyInvitation,
        created["id"],
    )

    assert membership.is_active is True
    assert invitation is not None
    assert invitation.accepted_at is not None
    assert invitation.accepted_by_user_id == user.id

    reuse_response = await api_client.post(
        "/api/v1/invitations/accept",
        json={
            "token": created["token"],
            "username": "another-user",
            "password": "password123",
        },
    )

    assert reuse_response.status_code == 409
    assert reuse_response.json() == {
        "detail": "Invitation has already been accepted",
    }


@pytest.mark.asyncio
async def test_expired_and_revoked_invitations_are_rejected(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, access_token = (
        await initialize_and_login_admin(api_client)
    )
    company_id = setup["company_id"]

    expired = await create_invitation(
        api_client,
        access_token=access_token,
        company_id=company_id,
    )

    expired_model = await db_session.get(
        CompanyInvitation,
        expired["id"],
    )
    assert expired_model is not None

    expired_model.expires_at = (
        datetime.now(timezone.utc)
        - timedelta(minutes=1)
    )
    await db_session.commit()

    expired_response = await api_client.post(
        "/api/v1/invitations/accept",
        json={
            "token": expired["token"],
            "username": "expired-user",
            "password": "password123",
        },
    )

    assert expired_response.status_code == 410
    assert expired_response.json() == {
        "detail": "Invitation has expired",
    }

    revoked = await create_invitation(
        api_client,
        access_token=access_token,
        company_id=company_id,
    )

    revoke_response = await api_client.post(
        (
            f"/api/v1/companies/{company_id}"
            f"/invitations/{revoked['id']}/revoke"
        ),
        headers=company_headers(
            access_token,
            company_id,
        ),
    )
    assert revoke_response.status_code == 200

    revoked_response = await api_client.post(
        "/api/v1/invitations/accept",
        json={
            "token": revoked["token"],
            "username": "revoked-user",
            "password": "password123",
        },
    )

    assert revoked_response.status_code == 410
    assert revoked_response.json() == {
        "detail": "Invitation has been revoked",
    }


@pytest.mark.asyncio
async def test_failed_acceptance_rolls_back_user_membership_and_invitation(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
    monkeypatch,
):
    setup, access_token = (
        await initialize_and_login_admin(api_client)
    )

    created = await create_invitation(
        api_client,
        access_token=access_token,
        company_id=setup["company_id"],
    )

    async def fail_membership(*args, **kwargs):
        raise RuntimeError("membership creation failed")

    monkeypatch.setattr(
        "services.invitations.create_company_membership",
        fail_membership,
    )

    with pytest.raises(
        RuntimeError,
        match="membership creation failed",
    ):
        await accept_invitation_for_new_user(
            db_session,
            token=created["token"],
            username="rollback-user",
            password="password123",
        )

    assert (
        await db_session.execute(
            select(User).where(
                User.username == "rollback-user"
            )
        )
    ).scalar_one_or_none() is None

    invitation = await db_session.get(
        CompanyInvitation,
        created["id"],
    )

    assert invitation is not None
    assert invitation.accepted_at is None
    assert invitation.accepted_by_user_id is None


@pytest.mark.asyncio
async def test_same_invitation_cannot_be_consumed_concurrently(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, access_token = (
        await initialize_and_login_admin(api_client)
    )

    created = await create_invitation(
        api_client,
        access_token=access_token,
        company_id=setup["company_id"],
    )

    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def accept(username: str):
        async with session_factory() as session:
            return await accept_invitation_for_new_user(
                session,
                token=created["token"],
                username=username,
                password="password123",
            )

    try:
        results = await asyncio.gather(
            accept("race-user-a"),
            accept("race-user-b"),
            return_exceptions=True,
        )
    finally:
        await engine.dispose()

    successes = [
        result
        for result in results
        if not isinstance(result, Exception)
    ]
    failures = [
        result
        for result in results
        if isinstance(result, Exception)
    ]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(
        failures[0],
        InvitationAcceptedError,
    )

    created_user_count = (
        await db_session.execute(
            select(func.count(User.id)).where(
                User.username.in_(
                    ["race-user-a", "race-user-b"]
                )
            )
        )
    ).scalar_one()

    assert created_user_count == 1


@pytest.mark.asyncio
async def test_existing_user_joins_another_company_without_duplication(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, admin_token = (
        await initialize_and_login_admin(api_client)
    )
    company_a_id = setup["company_id"]

    company_b_response = await api_client.post(
        "/api/v1/companies",
        json={
            "name": "Company B",
            "short_name": "B",
        },
        headers=auth_headers(admin_token),
    )
    assert company_b_response.status_code == 201
    company_b_id = company_b_response.json()["id"]

    invitation = await create_invitation(
        api_client,
        access_token=admin_token,
        company_id=company_b_id,
    )

    user = await register_user(
        db_session,
        username="existing-user",
        password="password123",
    )
    db_session.add(
        CompanyMembership(
            user_id=user.id,
            company_id=company_a_id,
        )
    )
    await db_session.commit()

    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username": "existing-user",
            "password": "password123",
        },
    )
    assert login_response.status_code == 200
    user_token = login_response.json()["access_token"]

    response = await api_client.post(
        "/api/v1/invitations/accept-existing",
        json={
            "token": invitation["token"],
        },
        headers=auth_headers(user_token),
    )

    assert response.status_code == 201
    assert invitation["token"] not in str(
        response.request.url
    )
    assert response.json()["user"]["id"] == user.id
    assert response.json()["company_id"] == company_b_id

    user_count = (
        await db_session.execute(
            select(func.count(User.id)).where(
                User.username == "existing-user"
            )
        )
    ).scalar_one()

    memberships = (
        await db_session.execute(
            select(CompanyMembership).where(
                CompanyMembership.user_id == user.id
            )
        )
    ).scalars().all()

    assert user_count == 1
    assert {
        membership.company_id
        for membership in memberships
    } == {company_a_id, company_b_id}

    companies_response = await api_client.get(
        "/api/v1/me/companies",
        headers=auth_headers(user_token),
    )

    assert companies_response.status_code == 200
    assert {
        company["id"]
        for company in companies_response.json()
    } == {company_a_id, company_b_id}


@pytest.mark.asyncio
async def test_existing_member_conflict_does_not_consume_invitation(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, admin_token = (
        await initialize_and_login_admin(api_client)
    )
    company_id = setup["company_id"]

    invitation = await create_invitation(
        api_client,
        access_token=admin_token,
        company_id=company_id,
    )

    response = await api_client.post(
        "/api/v1/invitations/accept-existing",
        json={
            "token": invitation["token"],
        },
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "User is already a member of this company"
        ),
    }

    invitation_model = await db_session.get(
        CompanyInvitation,
        invitation["id"],
    )

    assert invitation_model is not None
    assert invitation_model.accepted_at is None


@pytest.mark.asyncio
async def test_invitation_creates_membership_only_in_its_company(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, admin_token = (
        await initialize_and_login_admin(api_client)
    )
    company_a_id = setup["company_id"]

    company_b_response = await api_client.post(
        "/api/v1/companies",
        json={
            "name": "Company B",
            "short_name": "B",
        },
        headers=auth_headers(admin_token),
    )
    company_b_id = company_b_response.json()["id"]

    invitation = await create_invitation(
        api_client,
        access_token=admin_token,
        company_id=company_a_id,
    )

    response = await api_client.post(
        "/api/v1/invitations/accept",
        json={
            "token": invitation["token"],
            "username": "company-a-user",
            "password": "password123",
        },
    )
    assert response.status_code == 201

    user_id = response.json()["user"]["id"]
    memberships = (
        await db_session.execute(
            select(CompanyMembership).where(
                CompanyMembership.user_id == user_id
            )
        )
    ).scalars().all()

    assert [
        membership.company_id
        for membership in memberships
    ] == [company_a_id]
    assert company_b_id not in {
        membership.company_id
        for membership in memberships
    }
