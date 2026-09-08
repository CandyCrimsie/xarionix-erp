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
from models.role_delegations import (
    RoleDelegation,
)
from models.role_permissions import (
    RolePermission,
)
from models.roles import Role
from models.users import User

from repositories.membership_roles import (
    get_membership_roles,
)

from services.sessions import (
    create_session,
)


async def create_context(
    session: AsyncSession,
    *,
    with_assign_permission: bool = True,
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

    actor_user = User(
        username="api-role-manager",
        password_hash="test",
    )

    target_user = User(
        username="api-role-target",
        password_hash="test",
    )

    session.add_all(
        [
            actor_user,
            target_user,
        ]
    )

    await session.flush()

    actor = CompanyMembership(
        user_id=actor_user.id,
        company_id=company.id,
    )

    target = CompanyMembership(
        user_id=target_user.id,
        company_id=company.id,
    )

    session.add_all(
        [
            actor,
            target,
        ]
    )

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

    administrator = Role(
        company_id=company.id,
        name="Administrator",
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
            administrator,
            foreign,
        ]
    )

    await session.flush()

    #
    # Actor всегда имеет manager-role.
    #
    session.add(
        MembershipRole(
            company_membership_id=actor.id,
            role_id=manager.id,
        )
    )

    #
    # Manager может управлять только
    # Operator и Trainee.
    #
    session.add_all(
        [
            RoleDelegation(
                manager_role_id=manager.id,
                assignable_role_id=operator.id,
            ),

            RoleDelegation(
                manager_role_id=manager.id,
                assignable_role_id=trainee.id,
            ),
        ]
    )

    if with_assign_permission:
        permission = Permission(
            code="roles.assign",
            name="Assign roles",
            module="roles",
        )

        session.add(permission)

        await session.flush()

        session.add(
            RolePermission(
                role_id=manager.id,
                permission_id=permission.id,
                scope=PermissionScope.COMPANY,
            )
        )

    await session.flush()

    return {
        "company": company,
        "foreign_company": foreign_company,

        "actor": actor,
        "target": target,

        "manager": manager,
        "operator": operator,
        "trainee": trainee,
        "administrator": administrator,
        "foreign": foreign,
    }


async def add_target_roles(
    session: AsyncSession,
    *,
    target: CompanyMembership,
    roles: list[Role],
) -> None:
    session.add_all(
        [
            MembershipRole(
                company_membership_id=target.id,
                role_id=role.id,
            )
            for role in roles
        ]
    )

    await session.flush()


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


async def get_target_role_ids(
    session: AsyncSession,
    *,
    target: CompanyMembership,
) -> set[int]:
    roles = await get_membership_roles(
        session,
        target.id,
    )

    return {
        role.id
        for role in roles
    }


def response_role_ids(
    response,
) -> set[int]:
    return {
        item["id"]
        for item in response.json()
    }


@pytest.mark.asyncio
async def test_api_can_replace_delegated_roles_and_preserve_admin(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["administrator"],
            ctx["operator"],
        ],
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}/roles"
        ),
        headers=headers,
        json={
            "role_ids": [
                ctx["administrator"].id,
                ctx["trainee"].id,
            ],
        },
    )

    assert response.status_code == 200

    assert response_role_ids(
        response
    ) == {
        ctx["administrator"].id,
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_api_cannot_add_undelegated_admin_role(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
        ],
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}/roles"
        ),
        headers=headers,
        json={
            "role_ids": [
                ctx["operator"].id,
                ctx["administrator"].id,
            ],
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": {
            "message": (
                "Role assignment is not allowed"
            ),
            "role_ids": [
                ctx["administrator"].id,
            ],
        },
    }

    assert await get_target_role_ids(
        db_session,
        target=ctx["target"],
    ) == {
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_api_cannot_remove_undelegated_admin_role(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["administrator"],
            ctx["operator"],
        ],
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}/roles"
        ),
        headers=headers,
        json={
            "role_ids": [
                ctx["operator"].id,
            ],
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": {
            "message": (
                "Role assignment is not allowed"
            ),
            "role_ids": [
                ctx["administrator"].id,
            ],
        },
    }

    #
    # Критичная проверка:
    # запрещённый PUT не изменил БД.
    #
    assert await get_target_role_ids(
        db_session,
        target=ctx["target"],
    ) == {
        ctx["administrator"].id,
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_api_noop_with_undelegated_admin_is_allowed(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["administrator"],
            ctx["operator"],
        ],
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}/roles"
        ),
        headers=headers,
        json={
            "role_ids": [
                ctx["administrator"].id,
                ctx["operator"].id,
            ],
        },
    )

    assert response.status_code == 200

    assert response_role_ids(
        response
    ) == {
        ctx["administrator"].id,
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_api_without_roles_assign_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        with_assign_permission=False,
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
        ],
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}/roles"
        ),
        headers=headers,
        json={
            "role_ids": [
                ctx["operator"].id,
                ctx["trainee"].id,
            ],
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }


@pytest.mark.asyncio
async def test_api_foreign_role_is_invalid_and_keeps_old_roles(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
        ],
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}/roles"
        ),
        headers=headers,
        json={
            "role_ids": [
                ctx["operator"].id,
                ctx["foreign"].id,
            ],
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "message": "Invalid roles",
            "role_ids": [
                ctx["foreign"].id,
            ],
        },
    }

    assert await get_target_role_ids(
        db_session,
        target=ctx["target"],
    ) == {
        ctx["operator"].id,
    }


@pytest.mark.asyncio
async def test_api_inactive_target_is_conflict(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await add_target_roles(
        db_session,
        target=ctx["target"],
        roles=[
            ctx["operator"],
        ],
    )

    ctx["target"].is_active = False

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}/roles"
        ),
        headers=headers,
        json={
            "role_ids": [
                ctx["operator"].id,
                ctx["trainee"].id,
            ],
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": "Company membership is inactive",
    }