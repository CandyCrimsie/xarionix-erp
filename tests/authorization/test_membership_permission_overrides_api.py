import pytest

from httpx import AsyncClient

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.permissions.effects import (
    PermissionOverrideEffect,
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

from services.authorization import (
    AuthorizationService,
)

from services.membership_permission_overrides import (
    set_membership_permission_override,
)

from services.sessions import (
    create_session,
)


async def create_context(
    session: AsyncSession,
    *,
    manage_scope: PermissionScope | None = (
        PermissionScope.COMPANY
    ),
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
        username="override-api-manager",
        password_hash="test",
    )

    target_user = User(
        username="override-api-target",
        password_hash="test",
    )

    foreign_user = User(
        username="override-api-foreign",
        password_hash="test",
    )

    session.add_all(
        [
            actor_user,
            target_user,
            foreign_user,
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

    foreign_target = CompanyMembership(
        user_id=foreign_user.id,
        company_id=foreign_company.id,
    )

    session.add_all(
        [
            actor,
            target,
            foreign_target,
        ]
    )

    await session.flush()

    roles_manage = Permission(
        code="roles.manage",
        name="Manage roles",
        module="roles",
    )

    tasks_read = Permission(
        code="tasks.read",
        name="Read tasks",
        module="tasks",
    )

    companies_manage = Permission(
        code="companies.manage",
        name="Manage companies",
        module="companies",
    )

    inactive_permission = Permission(
        code="tasks.update",
        name="Update tasks",
        module="tasks",
        is_active=False,
    )

    access_role = Role(
        company_id=company.id,
        name="RBAC Administrator",
    )

    target_role = Role(
        company_id=company.id,
        name="Target Operator",
    )

    session.add_all(
        [
            roles_manage,
            tasks_read,
            companies_manage,
            inactive_permission,
            access_role,
            target_role,
        ]
    )

    await session.flush()

    session.add_all(
        [
            MembershipRole(
                company_membership_id=actor.id,
                role_id=access_role.id,
            ),

            MembershipRole(
                company_membership_id=target.id,
                role_id=target_role.id,
            ),

            RolePermission(
                role_id=target_role.id,
                permission_id=tasks_read.id,
                scope=PermissionScope.SELF,
            ),
        ]
    )

    if manage_scope is not None:
        session.add(
            RolePermission(
                role_id=access_role.id,
                permission_id=roles_manage.id,
                scope=manage_scope,
            )
        )

    await session.flush()

    return {
        "company": company,
        "foreign_company": foreign_company,

        "actor": actor,
        "target": target,
        "foreign_target": foreign_target,

        "roles_manage": roles_manage,
        "tasks_read": tasks_read,
        "companies_manage": companies_manage,
        "inactive_permission": inactive_permission,

        "access_role": access_role,
        "target_role": target_role,
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


def override_url(
    *,
    membership_id: int,
    permission_id: int | None = None,
) -> str:
    base = (
        f"/api/v1/members/"
        f"{membership_id}"
        f"/permission-overrides"
    )

    if permission_id is None:
        return base

    return (
        f"{base}/{permission_id}"
    )


@pytest.mark.asyncio
async def test_api_can_create_and_list_allow_override(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
        json={
            "effect": "allow",
            "scope": "company",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data[
        "company_membership_id"
    ] == ctx["target"].id

    assert data[
        "permission_id"
    ] == ctx["tasks_read"].id

    assert data["effect"] == "allow"
    assert data["scope"] == "company"

    list_response = await api_client.get(
        override_url(
            membership_id=ctx["target"].id,
        ),
        headers=headers,
    )

    assert list_response.status_code == 200

    assert len(
        list_response.json()
    ) == 1

    assert list_response.json()[0][
        "id"
    ] == data["id"]


@pytest.mark.asyncio
async def test_api_put_updates_existing_override(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    first = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
        json={
            "effect": "allow",
            "scope": "own_unit",
        },
    )

    assert first.status_code == 200

    second = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
        json={
            "effect": "deny",
            "scope": None,
        },
    )

    assert second.status_code == 200

    assert (
        second.json()["id"]
        == first.json()["id"]
    )

    assert (
        second.json()["effect"]
        == "deny"
    )

    assert second.json()["scope"] is None


@pytest.mark.asyncio
async def test_api_can_delete_override(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    created = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
        json={
            "effect": "deny",
            "scope": None,
        },
    )

    assert created.status_code == 200

    response = await api_client.delete(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
    )

    assert response.status_code == 204

    list_response = await api_client.get(
        override_url(
            membership_id=ctx["target"].id,
        ),
        headers=headers,
    )

    assert list_response.status_code == 200
    assert list_response.json() == []


@pytest.mark.asyncio
async def test_api_without_roles_manage_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        manage_scope=None,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
        json={
            "effect": "deny",
            "scope": None,
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }


@pytest.mark.asyncio
async def test_api_roles_manage_below_company_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        manage_scope=(
            PermissionScope.OWN_UNIT
        ),
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
        json={
            "effect": "deny",
            "scope": None,
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_foreign_membership_is_not_found(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=(
                ctx["foreign_target"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
        ),
        headers=headers,
        json={
            "effect": "allow",
            "scope": "company",
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": (
            "Company membership not found"
        ),
    }


@pytest.mark.asyncio
async def test_api_inactive_membership_is_conflict(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    ctx["target"].is_active = False

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
        json={
            "effect": "deny",
            "scope": None,
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": (
            "Company membership is inactive"
        ),
    }


@pytest.mark.asyncio
async def test_api_missing_permission_is_not_found(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=999999999,
        ),
        headers=headers,
        json={
            "effect": "deny",
            "scope": None,
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Permission not found",
    }


@pytest.mark.asyncio
async def test_api_inactive_permission_is_conflict(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=(
                ctx["inactive_permission"].id
            ),
        ),
        headers=headers,
        json={
            "effect": "allow",
            "scope": "company",
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": "Permission is inactive",
    }


@pytest.mark.asyncio
async def test_api_invalid_permission_scope_is_bad_request(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=(
                ctx["companies_manage"].id
            ),
        ),
        headers=headers,
        json={
            "effect": "allow",
            "scope": "own_unit",
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": {
            "message": (
                "Invalid permission scope"
            ),
            "permission_id": (
                ctx["companies_manage"].id
            ),
            "code": "companies.manage",
            "scope": "own_unit",
            "allowed_scopes": [
                "company",
            ],
        },
    }


@pytest.mark.asyncio
async def test_api_allow_without_scope_is_bad_request(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
        json={
            "effect": "allow",
            "scope": None,
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": (
            "ALLOW override requires scope"
        ),
    }


@pytest.mark.asyncio
async def test_api_deny_with_scope_is_bad_request(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
        json={
            "effect": "deny",
            "scope": "company",
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": (
            "DENY override must not have scope"
        ),
    }


@pytest.mark.asyncio
async def test_api_delete_missing_override_is_not_found(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.delete(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": (
            "Permission override not found"
        ),
    }


@pytest.mark.asyncio
async def test_api_put_invalidates_target_authorization_cache(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    authorization = AuthorizationService(
        db_session
    )

    before = (
        await authorization.get_effective_permissions(
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["target"].id
            ),
        )
    )

    assert before[
        "tasks.read"
    ] == PermissionScope.SELF

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.put(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
        json={
            "effect": "deny",
            "scope": None,
        },
    )

    assert response.status_code == 200

    after = (
        await authorization.get_effective_permissions(
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["target"].id
            ),
        )
    )

    assert "tasks.read" not in after


@pytest.mark.asyncio
async def test_api_delete_invalidates_target_authorization_cache(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    #
    # Seed DENY через service.
    #
    await set_membership_permission_override(
        db_session,
        company_id=ctx["company"].id,
        company_membership_id=(
            ctx["target"].id
        ),
        permission_id=(
            ctx["tasks_read"].id
        ),
        effect=PermissionOverrideEffect.DENY,
        scope=None,
    )

    authorization = AuthorizationService(
        db_session
    )

    denied = (
        await authorization.get_effective_permissions(
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["target"].id
            ),
        )
    )

    assert "tasks.read" not in denied

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.delete(
        override_url(
            membership_id=ctx["target"].id,
            permission_id=ctx["tasks_read"].id,
        ),
        headers=headers,
    )

    assert response.status_code == 204

    restored = (
        await authorization.get_effective_permissions(
            company_id=ctx["company"].id,
            company_membership_id=(
                ctx["target"].id
            ),
        )
    )

    assert restored[
        "tasks.read"
    ] == PermissionScope.SELF


@pytest.mark.asyncio
async def test_api_permission_override_catalog_returns_permissions(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}"
            f"/permission-overrides/catalog"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    permissions = response.json()

    assert permissions

    assert all(
        "id" in permission
        and "code" in permission
        and "allowed_scopes"
        in permission
        for permission
        in permissions
    )


@pytest.mark.asyncio
async def test_api_permission_override_catalog_cannot_read_foreign_membership(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['foreign_target'].id}"
            f"/permission-overrides/catalog"
        ),
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": (
            "Company membership not found"
        ),
    }


@pytest.mark.asyncio
async def test_api_effective_permissions_returns_role_permissions(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )


    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}"
            f"/permission-overrides/effective"
        ),
        headers=headers,
    )


    assert response.status_code == 200

    data = response.json()


    assert (
        "tasks.read"
        in data["permissions"]
    )

    assert (
        data["scopes"][
            "tasks.read"
        ]
        == "self"
    )


@pytest.mark.asyncio
async def test_api_effective_permissions_reflects_allow_override(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )


    before = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}"
            f"/permission-overrides/effective"
        ),
        headers=headers,
    )

    assert before.status_code == 200

    assert (
        before.json()["scopes"][
            "tasks.read"
        ]
        == "self"
    )


    override = await api_client.put(
        override_url(
            membership_id=(
                ctx["target"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
        ),
        headers=headers,
        json={
            "effect": "allow",
            "scope": "company",
        },
    )

    assert override.status_code == 200


    after = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}"
            f"/permission-overrides/effective"
        ),
        headers=headers,
    )

    assert after.status_code == 200

    assert (
        after.json()["scopes"][
            "tasks.read"
        ]
        == "company"
    )


@pytest.mark.asyncio
async def test_api_effective_permissions_reflects_deny_override(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )


    response = await api_client.put(
        override_url(
            membership_id=(
                ctx["target"].id
            ),
            permission_id=(
                ctx["tasks_read"].id
            ),
        ),
        headers=headers,
        json={
            "effect": "deny",
            "scope": None,
        },
    )

    assert response.status_code == 200


    effective = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['target'].id}"
            f"/permission-overrides/effective"
        ),
        headers=headers,
    )

    assert effective.status_code == 200

    data = effective.json()


    assert (
        "tasks.read"
        not in data["permissions"]
    )

    assert (
        "tasks.read"
        not in data["scopes"]
    )


@pytest.mark.asyncio
async def test_api_effective_permissions_cannot_read_foreign_membership(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )


    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['foreign_target'].id}"
            f"/permission-overrides/effective"
        ),
        headers=headers,
    )


    assert response.status_code == 404

    assert response.json() == {
        "detail": (
            "Company membership not found"
        ),
    }