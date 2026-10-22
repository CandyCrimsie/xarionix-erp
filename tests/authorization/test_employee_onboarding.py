import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from models.company_invitations import CompanyInvitation
from models.company_memberships import CompanyMembership
from models.users import User
from services import invitations as invitation_service


DETAILS = {
    "first_name": "Иван",
    "last_name": "Иванов",
    "middle_name": "Иванович",
    "email": "ivan@example.com",
    "phone_number": "+79991234567",
    "date_of_birth": "1992-07-15",
}


def headers(token, company_id=None):
    result = {"Authorization": f"Bearer {token}"}
    if company_id is not None:
        result["X-Company-Id"] = str(company_id)
    return result


async def initialize(api_client):
    setup = await api_client.post(
        "/api/v1/setup/initialize", json={"company": {"name": "Onboarding Company"}}
    )
    assert setup.status_code == 201, setup.text
    login = await api_client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "password123"}
    )
    return setup.json()["company_id"], login.json()["access_token"]


async def create_invite(api_client, company_id, token, data=None):
    response = await api_client.post(
        f"/api/v1/companies/{company_id}/invitations",
        headers=headers(token, company_id), json=DETAILS if data is None else data,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def accept(api_client, invitation, username="new-employee", **overrides):
    response = await api_client.post("/api/v1/invitations/accept", json={
        "token": invitation["token"], "username": username, "password": "password123", **overrides,
    })
    assert response.status_code == 201, response.text
    login = await api_client.post(
        "/api/v1/auth/login", json={"username": username, "password": "password123"}
    )
    return response.json(), login.json()["access_token"]


@pytest.mark.asyncio
async def test_invitation_details_are_normalized_and_hidden_from_public_resolution(api_client):
    company_id, token = await initialize(api_client)
    invitation = await create_invite(api_client, company_id, token, {
        **DETAILS, "first_name": "  Иван  ", "last_name": "  Иванов  ", "middle_name": "  Иванович  ",
        "email": "  ivan@EXAMPLE.COM  ", "phone_number": "+7 (999) 123-45-67",
    })
    assert {key: invitation[key] for key in DETAILS} == DETAILS
    listed = await api_client.get(
        f"/api/v1/companies/{company_id}/invitations", headers=headers(token, company_id)
    )
    assert {key: listed.json()[0][key] for key in DETAILS} == DETAILS
    assert "token" not in listed.json()[0]
    resolved = await api_client.post("/api/v1/invitations/resolve", json={"token": invitation["token"]})
    assert resolved.status_code == 200
    assert set(resolved.json()) == {"company", "expires_at", "status"}
    assert not set(DETAILS).intersection(resolved.json())
    assert "ivan@example.com" not in resolved.text


@pytest.mark.asyncio
async def test_acceptance_copies_invitation_details_and_shows_real_creation_dates(db_session, api_client):
    company_id, token = await initialize(api_client)
    invitation = await create_invite(api_client, company_id, token)
    stored = await db_session.get(CompanyInvitation, invitation["id"])
    stored.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    await db_session.commit()
    before_accept = datetime.now(timezone.utc) - timedelta(seconds=1)
    # Public input cannot replace the details entered by the manager.
    accepted, employee_token = await accept(api_client, invitation, **{
        "first_name": "Попытка подмены", "last_name": "Подмена", "email": "other@example.com",
    })
    profile = await api_client.get("/api/v1/me/profile", headers=headers(employee_token, company_id))
    assert profile.status_code == 200, profile.text
    assert {key: profile.json()[key] for key in DETAILS} == DETAILS
    assert profile.json()["user_id"] == accepted["user"]["id"]
    assert datetime.fromisoformat(profile.json()["account_created_at"]) >= before_accept
    assert datetime.fromisoformat(profile.json()["joined_at"]) >= before_accept
    assert profile.json()["account_created_at"] == accepted["user"]["created_at"]
    membership = (await db_session.scalars(select(CompanyMembership).where(
        CompanyMembership.user_id == accepted["user"]["id"],
        CompanyMembership.company_id == company_id,
    ))).one()
    assert membership.date_of_birth == date(1992, 7, 15)
    # The authorized Members UI can see the same company-owned details.
    members = await api_client.get(f"/api/v1/companies/{company_id}/members", headers=headers(token, company_id))
    member = next(item for item in members.json() if item["user_id"] == accepted["user"]["id"])
    assert {key: member[key] for key in DETAILS} == DETAILS


@pytest.mark.asyncio
async def test_existing_user_profile_is_separate_in_each_company_and_account_is_not_recreated(db_session, api_client):
    company_a, token = await initialize(api_client)
    accepted, employee_token = await accept(api_client, await create_invite(api_client, company_a, token))
    company_b = (await api_client.post(
        "/api/v1/companies", headers=headers(token), json={"name": "Second Company"}
    )).json()["id"]
    details_b = {
        **DETAILS, "first_name": "Иоанн", "last_name": "Иванов-Петров", "middle_name": None,
        "email": "work@example.org", "phone_number": "+74951234567",
    }
    invitation_b = await create_invite(api_client, company_b, token, details_b)
    joined = await api_client.post(
        "/api/v1/invitations/accept-existing", headers=headers(employee_token),
        json={"token": invitation_b["token"]},
    )
    assert joined.status_code == 201, joined.text
    assert joined.json()["user"]["id"] == accepted["user"]["id"]
    for company_id, expected in ((company_a, DETAILS), (company_b, details_b)):
        profile = await api_client.get("/api/v1/me/profile", headers=headers(employee_token, company_id))
        assert {key: profile.json()[key] for key in DETAILS} == expected
        assert profile.json()["account_created_at"] == accepted["user"]["created_at"]
    other_membership = await db_session.get(CompanyMembership, 1)
    assert other_membership.full_name is None  # Administrator was not modified.
    users = list((await db_session.scalars(select(User).where(User.username == "new-employee"))).all())
    assert len(users) == 1
    denied = await api_client.get(
        f"/api/v1/companies/{company_b}/members", headers=headers(employee_token, company_a)
    )
    assert denied.status_code in (403, 404)


@pytest.mark.asyncio
async def test_profile_requires_authentication_and_membership_not_members_read(api_client):
    company_id, token = await initialize(api_client)
    assert (await api_client.get("/api/v1/me/profile")).status_code == 401
    assert (await api_client.get("/api/v1/me/profile", headers=headers(token))).status_code == 400
    _, employee_token = await accept(api_client, await create_invite(api_client, company_id, token))
    # New invitees have no RBAC roles; they may still view their own profile.
    assert (await api_client.get("/api/v1/me/profile", headers=headers(employee_token, company_id))).status_code == 200
    company_b = (await api_client.post(
        "/api/v1/companies", headers=headers(token), json={"name": "Private Company"}
    )).json()["id"]
    assert (await api_client.get("/api/v1/me/profile", headers=headers(employee_token, company_b))).status_code == 403
    assert (await api_client.get(
        f"/api/v1/companies/{company_id}/members", headers=headers(employee_token, company_id)
    )).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [
    {"first_name": "x" * 101}, {"last_name": "x" * 101}, {"middle_name": "x" * 101},
    {"first_name": "Name\u0000"}, {"last_name": "Name\u007f"}, {"middle_name": "Name\u0000"},
    {"full_name": "No more unstructured names"},
    {"email": "not-an-email"}, {"email": "x\r\n@example.com"},
    {"phone_number": "123"}, {"phone_number": "+7 999 letters"},
    {"phone_number": "+1234567890123456"},
    {"date_of_birth": "1992-02-30"}, {"date_of_birth": "2999-01-01"},
])
async def test_invalid_employee_details_are_rejected_before_invitation_creation(api_client, invalid):
    company_id, token = await initialize(api_client)
    response = await api_client.post(
        f"/api/v1/companies/{company_id}/invitations", headers=headers(token, company_id), json=invalid,
    )
    assert response.status_code == 422, response.text
    listed = await api_client.get(f"/api/v1/companies/{company_id}/invitations", headers=headers(token, company_id))
    assert listed.json() == []


@pytest.mark.asyncio
async def test_blank_optional_details_and_legacy_invitations_remain_usable(api_client):
    company_id, token = await initialize(api_client)
    invitation = await create_invite(api_client, company_id, token, {
        "first_name": "  ", "last_name": " ", "middle_name": " ",
        "email": " ", "phone_number": " ", "date_of_birth": None,
    })
    _, employee_token = await accept(api_client, invitation)
    profile = await api_client.get("/api/v1/me/profile", headers=headers(employee_token, company_id))
    assert all(profile.json()[field] is None for field in DETAILS)


@pytest.mark.asyncio
async def test_acceptance_failure_rolls_back_employee_profile_with_the_rest(db_session, api_client, monkeypatch):
    company_id, token = await initialize(api_client)
    invitation = await create_invite(api_client, company_id, token)
    async def fail_after_flush():
        await db_session.flush()
        raise RuntimeError("profile transaction failed")

    monkeypatch.setattr(db_session, "commit", fail_after_flush)
    with pytest.raises(RuntimeError, match="profile transaction failed"):
        await invitation_service.accept_invitation_for_new_user(
            db_session, token=invitation["token"], username="failed-employee", password="password123"
        )
    assert (await db_session.scalar(select(User).where(User.username == "failed-employee"))) is None
    stored = await db_session.get(CompanyInvitation, invitation["id"])
    assert stored.accepted_at is None
    assert stored.first_name == DETAILS["first_name"]
    assert stored.last_name == DETAILS["last_name"]
    assert stored.middle_name == DETAILS["middle_name"]


@pytest.mark.asyncio
async def test_concurrent_acceptance_creates_exactly_one_employee_profile(db_session, api_client):
    company_id, token = await initialize(api_client)
    invitation = await create_invite(api_client, company_id, token)
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False, autoflush=False)

    async def consume(username):
        async with sessions() as session:
            return await invitation_service.accept_invitation_for_new_user(
                session, token=invitation["token"], username=username, password="password123"
            )

    results = await asyncio.wait_for(asyncio.gather(
        consume("profile-race-a"), consume("profile-race-b"), return_exceptions=True,
    ), timeout=15)
    assert len([item for item in results if not isinstance(item, Exception)]) == 1
    failures = [item for item in results if isinstance(item, Exception)]
    assert len(failures) == 1
    assert isinstance(failures[0], invitation_service.InvitationAcceptedError)
    memberships = list((await db_session.scalars(select(CompanyMembership).where(
        CompanyMembership.company_id == company_id,
        CompanyMembership.email == DETAILS["email"],
    ))).all())
    assert len(memberships) == 1
    assert memberships[0].first_name == DETAILS["first_name"]
    assert memberships[0].last_name == DETAILS["last_name"]
    assert memberships[0].middle_name == DETAILS["middle_name"]


@pytest.mark.asyncio
async def test_legacy_name_is_preserved_without_guessing_components(db_session, api_client):
    company_id, token = await initialize(api_client)
    invitation = await create_invite(api_client, company_id, token, {})
    stored = await db_session.get(CompanyInvitation, invitation["id"])
    stored.full_name = "Историческое имя с неизвестным порядком"
    await db_session.commit()
    _, employee_token = await accept(api_client, invitation)
    profile = await api_client.get("/api/v1/me/profile", headers=headers(employee_token, company_id))
    assert profile.json()["full_name"] == "Историческое имя с неизвестным порядком"
    assert all(profile.json()[field] is None for field in ("first_name", "last_name", "middle_name"))


@pytest.mark.asyncio
async def test_middle_name_is_optional_and_multiword_components_remain_separate(api_client):
    company_id, token = await initialize(api_client)
    invitation = await create_invite(api_client, company_id, token, {
        "first_name": " Анна   Мария ", "last_name": " Де   ла Крус ",
    })
    assert invitation["first_name"] == "Анна Мария"
    assert invitation["last_name"] == "Де ла Крус"
    assert invitation["middle_name"] is None
    assert invitation["full_name"] is None
