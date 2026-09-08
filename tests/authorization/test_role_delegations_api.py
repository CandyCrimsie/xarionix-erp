import pytest

from httpx import AsyncClient

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.permissions.scopes import (
    PermissionScope,
)

from core.security.jwt import (
    create_access_token,
)

from models.company import Company
from models.company_memberships import (
    CompanyMembership,
)
from models.membership_roles import (
    MembershipRole,
)
from models.permissions import Permission
from models.role_permissions import (
    RolePermission,
)
from models.roles import Role
from models.users import User

from services.role_delegations import (
    list_role_delegations,
    replace_role_delegations_for_role,
)

from services.sessions import (
    create_session,
)


async def create_context(
    session: AsyncSession,
    *,
    with_manage_permission: bool = True,
):
    company = Company(
        name="Main Company",
    )

    foreign_company = Company(
        name="Foreign Company",
    )

    session.add_all(
        [
            company,
            foreign_company,
        ]
    )

    await session.flush()

    user = User(
        username="current-user",
        password_hash="test",
    )

    session.add(user)

    await session.flush()

    membership = CompanyMembership(
        user_id=user.id,
        company_id=company.id,
    )

    session.add(membership)

    await session.flush()

    manager = Role(
        company_id=company.id,
        name="Support Manager",
    )

    operator = Role(
        company_id=company.id,
        name="Support Operator",
    )

    trainee = Role(
        company_id=company.id,
        name="Support Trainee",
    )

    inactive = Role(
        company_id=company.id,
        name="Inactive Role",
        is_active=False,
    )

    foreign = Role(
        company_id=foreign_company.id,
        name="Foreign Role",
    )

    session.add_all(
        [
            manager,
            operator,
            trainee,
            inactive,
            foreign,
        ]
    )

    await session.flush()

    if with_manage_permission:
        permission = Permission(
            code="roles.manage",
            name="Manage roles",
            module="roles",
        )

        access_role = Role(
            company_id=company.id,
            name="RBAC Administrator",
        )

        session.add_all(
            [
                permission,
                access_role,
            ]
        )

        await session.flush()

        session.add_all(
            [
                RolePermission(
                    role_id=access_role.id,
                    permission_id=permission.id,
                    scope=PermissionScope.COMPANY,
                ),

                MembershipRole(
                    company_membership_id=(
                        membership.id
                    ),
                    role_id=access_role.id,
                ),
            ]
        )

        await session.flush()

    return {
        "company": company,
        "foreign_company": foreign_company,

        "user": user,
        "membership": membership,

        "manager": manager,
        "operator": operator,
        "trainee": trainee,
        "inactive": inactive,
        "foreign": foreign,
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

    access_token = create_access_token(
        user_id=user_id,
        session_id=created_session.session_id,
    )

    return {
        "Authorization": (
            f"Bearer {access_token}"
        ),
        "X-Company-Id": str(
            company_id
        ),
    }


def response_assignable_role_ids(
    response,
) -> set[int]:
    return {
        item["assignable_role_id"]
        for item in response.json()
    }


def delegation_role_ids(
    delegations,
) -> set[int]:
    return {
        delegation.assignable_role_id
        for delegation in delegations
    }


@pytest.mark.asyncio
async def test_api_put_role_delegations(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["user"].id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/roles/"
            f"{ctx['manager'].id}/delegations"
        ),
        headers=headers,
        json={
            "assignable_role_ids": [
                ctx["operator"].id,
                ctx["trainee"].id,
            ],
        },
    )

    assert response.status_code == 200

    assert response_assignable_role_ids(
        response
    ) == {
        ctx["operator"].id,
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_api_get_role_delegations(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await replace_role_delegations_for_role(
        db_session,
        company_id=ctx["company"].id,
        manager_role_id=ctx["manager"].id,
        assignable_role_ids=[
            ctx["operator"].id,
            ctx["trainee"].id,
        ],
    )

    headers = await create_auth_headers(
        user_id=ctx["user"].id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/roles/"
            f"{ctx['manager'].id}/delegations"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert response_assignable_role_ids(
        response
    ) == {
        ctx["operator"].id,
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_api_put_empty_list_clears_delegations(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await replace_role_delegations_for_role(
        db_session,
        company_id=ctx["company"].id,
        manager_role_id=ctx["manager"].id,
        assignable_role_ids=[
            ctx["operator"].id,
            ctx["trainee"].id,
        ],
    )

    headers = await create_auth_headers(
        user_id=ctx["user"].id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/roles/"
            f"{ctx['manager'].id}/delegations"
        ),
        headers=headers,
        json={
            "assignable_role_ids": [],
        },
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_api_put_delegations_without_permission_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        with_manage_permission=False,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["user"].id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/roles/"
            f"{ctx['manager'].id}/delegations"
        ),
        headers=headers,
        json={
            "assignable_role_ids": [
                ctx["operator"].id,
            ],
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }


@pytest.mark.asyncio
async def test_api_foreign_manager_role_is_not_found(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["user"].id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/roles/"
            f"{ctx['foreign'].id}/delegations"
        ),
        headers=headers,
        json={
            "assignable_role_ids": [],
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Role not found",
    }


@pytest.mark.asyncio
async def test_api_inactive_manager_role_is_conflict(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    ctx["manager"].is_active = False

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["user"].id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/roles/"
            f"{ctx['manager'].id}/delegations"
        ),
        headers=headers,
        json={
            "assignable_role_ids": [
                ctx["operator"].id,
            ],
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": "Role is inactive",
    }


@pytest.mark.asyncio
async def test_api_foreign_assignable_role_is_invalid(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["user"].id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/roles/"
            f"{ctx['manager'].id}/delegations"
        ),
        headers=headers,
        json={
            "assignable_role_ids": [
                ctx["operator"].id,
                ctx["foreign"].id,
            ],
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "message": (
                "Invalid assignable roles"
            ),
            "role_ids": [
                ctx["foreign"].id,
            ],
        },
    }


@pytest.mark.asyncio
async def test_api_inactive_assignable_role_is_invalid(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["user"].id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/roles/"
            f"{ctx['manager'].id}/delegations"
        ),
        headers=headers,
        json={
            "assignable_role_ids": [
                ctx["inactive"].id,
            ],
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "message": (
                "Invalid assignable roles"
            ),
            "role_ids": [
                ctx["inactive"].id,
            ],
        },
    }


@pytest.mark.asyncio
async def test_api_invalid_put_keeps_existing_delegations(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    await replace_role_delegations_for_role(
        db_session,
        company_id=ctx["company"].id,
        manager_role_id=ctx["manager"].id,
        assignable_role_ids=[
            ctx["operator"].id,
            ctx["trainee"].id,
        ],
    )

    headers = await create_auth_headers(
        user_id=ctx["user"].id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/roles/"
            f"{ctx['manager'].id}/delegations"
        ),
        headers=headers,
        json={
            "assignable_role_ids": [
                ctx["operator"].id,
                ctx["foreign"].id,
            ],
        },
    )

    assert response.status_code == 400

    delegations = await list_role_delegations(
        db_session,
        company_id=ctx["company"].id,
        manager_role_id=ctx["manager"].id,
    )

    assert delegation_role_ids(
        delegations
    ) == {
        ctx["operator"].id,
        ctx["trainee"].id,
    }