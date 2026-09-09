import pytest

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.security.jwt import (
    create_access_token,
)
from core.system_roles import (
    SystemRoleKey,
)

from models.company import Company
from models.company_memberships import (
    CompanyMembership,
)
from models.membership_roles import (
    MembershipRole,
)
from models.roles import Role
from models.users import User

from repositories.roles import (
    get_system_role_by_key,
)

from services.permissions import (
    sync_permissions,
)
from services.sessions import (
    create_session,
)
from services.system_roles import (
    sync_system_roles_for_company,
)


async def create_api_context(
    session: AsyncSession,
):
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

    await sync_system_roles_for_company(
        session,
        company_id=company_id,
    )

    administrator = (
        await get_system_role_by_key(
            session,
            company_id=company_id,
            system_key=(
                SystemRoleKey
                .ADMINISTRATOR
                .value
            ),
        )
    )

    assert administrator is not None

    user = User(
        username="system-role-api-admin",
        password_hash="test",
    )

    session.add(
        user
    )

    await session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company_id,
    )

    custom_role = Role(
        company_id=company_id,
        name="Custom Role",
    )

    session.add_all(
        [
            membership,
            custom_role,
        ]
    )

    await session.flush()

    session.add(
        MembershipRole(
            company_membership_id=(
                membership.id
            ),
            role_id=administrator.id,
        )
    )

    await session.commit()

    return {
        "company_id": company_id,
        "user_id": user.id,
        "administrator": administrator,
        "custom_role": custom_role,
    }


async def create_auth_headers(
    *,
    user_id: int,
    company_id: int,
) -> dict[str, str]:
    created_session = await create_session(
        user_id=user_id,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    token = create_access_token(
        user_id=user_id,
        session_id=(
            created_session.session_id
        ),
    )

    return {
        "Authorization": (
            f"Bearer {token}"
        ),
        "X-Company-Id": str(
            company_id
        ),
    }


@pytest.mark.asyncio
async def test_api_cannot_update_system_role(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_api_context(
        db_session
    )

    headers = await create_auth_headers(
        user_id=ctx["user_id"],
        company_id=ctx["company_id"],
    )

    response = await api_client.patch(
        (
            f"/api/v1/roles/"
            f"{ctx['administrator'].id}"
        ),
        headers=headers,
        json={
            "name": "Hacked Administrator",
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": (
            "System role is managed "
            "by the system"
        ),
    }


@pytest.mark.asyncio
async def test_api_cannot_replace_system_role_permissions(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_api_context(
        db_session
    )

    headers = await create_auth_headers(
        user_id=ctx["user_id"],
        company_id=ctx["company_id"],
    )

    response = await api_client.put(
        (
            f"/api/v1/roles/"
            f"{ctx['administrator'].id}"
            f"/permissions"
        ),
        headers=headers,
        json={
            "permissions": [],
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": (
            "System role is managed "
            "by the system"
        ),
    }


@pytest.mark.asyncio
async def test_api_cannot_replace_system_role_delegations(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_api_context(
        db_session
    )

    headers = await create_auth_headers(
        user_id=ctx["user_id"],
        company_id=ctx["company_id"],
    )

    response = await api_client.put(
        (
            f"/api/v1/roles/"
            f"{ctx['administrator'].id}"
            f"/delegations"
        ),
        headers=headers,
        json={
            "assignable_role_ids": [],
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": (
            "System role is managed "
            "by the system"
        ),
    }