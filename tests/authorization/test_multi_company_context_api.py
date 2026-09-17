import pytest

from httpx import AsyncClient

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.permissions.scopes import (
    PermissionScope,
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

from services.auth import (
    register_user,
)


async def create_multi_company_user(
    session: AsyncSession,
):
    user = await register_user(
        session,
        username="multi-user",
        password="password123",
    )


    company_a = Company(
        name="Company A",
        short_name="A",
    )

    company_b = Company(
        name="Company B",
        short_name="B",
    )

    company_c = Company(
        name="Company C",
        short_name="C",
    )


    session.add_all([
        company_a,
        company_b,
        company_c,
    ])


    await session.flush()


    membership_a = CompanyMembership(
        user_id=user.id,
        company_id=company_a.id,
        is_active=True,
    )

    membership_b = CompanyMembership(
        user_id=user.id,
        company_id=company_b.id,
        is_active=True,
    )


    session.add_all([
        membership_a,
        membership_b,
    ])


    await session.flush()


    permission_a = Permission(
        code="multi_company.permission_a",
        name="Multi-company permission A",
        module="multi_company_test",
    )

    permission_b = Permission(
        code="multi_company.permission_b",
        name="Multi-company permission B",
        module="multi_company_test",
    )


    role_a = Role(
        company_id=company_a.id,
        name="Company A Role",
    )

    role_b = Role(
        company_id=company_b.id,
        name="Company B Role",
    )


    session.add_all([
        permission_a,
        permission_b,
        role_a,
        role_b,
    ])


    await session.flush()


    session.add_all([
        RolePermission(
            role_id=role_a.id,
            permission_id=permission_a.id,
            scope=(
                PermissionScope.COMPANY
            ),
        ),

        RolePermission(
            role_id=role_b.id,
            permission_id=permission_b.id,
            scope=(
                PermissionScope.SELF
            ),
        ),

        MembershipRole(
            company_membership_id=(
                membership_a.id
            ),
            role_id=role_a.id,
        ),

        MembershipRole(
            company_membership_id=(
                membership_b.id
            ),
            role_id=role_b.id,
        ),
    ])


    await session.commit()


    return {
        "user": user,

        "company_a": company_a,
        "company_b": company_b,
        "company_c": company_c,

        "membership_a": membership_a,
        "membership_b": membership_b,
    }


async def login_multi_company_user(
    api_client: AsyncClient,
) -> str:
    response = await api_client.post(
        "/api/v1/auth/login",
        json={
            "username":
                "multi-user",

            "password":
                "password123",
        },
    )


    assert response.status_code == 200


    return response.json()[
        "access_token"
    ]


@pytest.mark.asyncio
async def test_same_user_has_isolated_permissions_between_companies(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    context = (
        await create_multi_company_user(
            db_session
        )
    )


    token = await login_multi_company_user(
        api_client
    )


    authorization = (
        f"Bearer {token}"
    )


    company_a = context[
        "company_a"
    ]

    company_b = context[
        "company_b"
    ]


    response_a = await api_client.get(
        "/api/v1/me/permissions",
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(company_a.id),
        },
    )


    assert response_a.status_code == 200


    assert response_a.json() == {
        "permissions": [
            "multi_company.permission_a",
        ],

        "scopes": {
            "multi_company.permission_a":
                "company",
        },
    }


    response_b = await api_client.get(
        "/api/v1/me/permissions",
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(company_b.id),
        },
    )


    assert response_b.status_code == 200


    assert response_b.json() == {
        "permissions": [
            "multi_company.permission_b",
        ],

        "scopes": {
            "multi_company.permission_b":
                "self",
        },
    }


    # Проверяем отсутствие утечки
    # permission A -> company B.
    assert (
        "multi_company.permission_a"
        not in response_b.json()[
            "permissions"
        ]
    )


    # Проверяем отсутствие утечки
    # permission B -> company A.
    assert (
        "multi_company.permission_b"
        not in response_a.json()[
            "permissions"
        ]
    )


@pytest.mark.asyncio
async def test_my_companies_contains_only_companies_with_active_membership(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    context = (
        await create_multi_company_user(
            db_session
        )
    )


    token = await login_multi_company_user(
        api_client
    )


    response = await api_client.get(
        "/api/v1/me/companies",
        headers={
            "Authorization":
                f"Bearer {token}",
        },
    )


    assert response.status_code == 200


    company_ids = {
        company["id"]
        for company
        in response.json()
    }


    assert company_ids == {
        context[
            "company_a"
        ].id,

        context[
            "company_b"
        ].id,
    }


    assert (
        context[
            "company_c"
        ].id
        not in company_ids
    )


@pytest.mark.asyncio
async def test_user_cannot_select_company_without_membership(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    context = (
        await create_multi_company_user(
            db_session
        )
    )


    token = await login_multi_company_user(
        api_client
    )


    response = await api_client.get(
        "/api/v1/me/permissions",
        headers={
            "Authorization":
                f"Bearer {token}",

            "X-Company-Id":
                str(
                    context[
                        "company_c"
                    ].id
                ),
        },
    )


    assert response.status_code == 404

    assert response.json() == {
        "detail":
            "Company not found",
    }