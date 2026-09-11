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
from models.organizational_units import (
    OrganizationalUnit,
    OrganizationalUnitType,
)
from models.permissions import Permission
from models.role_delegations import (
    RoleDelegation,
)
from models.role_permissions import (
    RolePermission,
)
from models.roles import Role
from models.unit_memberships import (
    UnitMembership,
)
from models.users import User

from services.sessions import (
    create_session,
)


async def create_context(
    session: AsyncSession,
    *,
    scope: PermissionScope | None,
    actor_has_primary_unit: bool = True,
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
        username="api-scope-manager",
        password_hash="test",
    )

    same_unit_user = User(
        username="api-same-unit-user",
        password_hash="test",
    )

    child_user = User(
        username="api-child-user",
        password_hash="test",
    )

    grandchild_user = User(
        username="api-grandchild-user",
        password_hash="test",
    )

    other_branch_user = User(
        username="api-other-branch-user",
        password_hash="test",
    )

    no_unit_user = User(
        username="api-no-unit-user",
        password_hash="test",
    )

    foreign_user = User(
        username="api-foreign-user",
        password_hash="test",
    )

    session.add_all(
        [
            actor_user,
            same_unit_user,
            child_user,
            grandchild_user,
            other_branch_user,
            no_unit_user,
            foreign_user,
        ]
    )

    await session.flush()

    actor = CompanyMembership(
        user_id=actor_user.id,
        company_id=company.id,
    )

    same_unit_target = CompanyMembership(
        user_id=same_unit_user.id,
        company_id=company.id,
    )

    child_target = CompanyMembership(
        user_id=child_user.id,
        company_id=company.id,
    )

    grandchild_target = CompanyMembership(
        user_id=grandchild_user.id,
        company_id=company.id,
    )

    other_branch_target = CompanyMembership(
        user_id=other_branch_user.id,
        company_id=company.id,
    )

    no_unit_target = CompanyMembership(
        user_id=no_unit_user.id,
        company_id=company.id,
    )

    foreign_target = CompanyMembership(
        user_id=foreign_user.id,
        company_id=foreign_company.id,
    )

    session.add_all(
        [
            actor,
            same_unit_target,
            child_target,
            grandchild_target,
            other_branch_target,
            no_unit_target,
            foreign_target,
        ]
    )

    await session.flush()

    support = OrganizationalUnit(
        company_id=company.id,
        name="Support",
        type=OrganizationalUnitType.DEPARTMENT,
    )

    accounting = OrganizationalUnit(
        company_id=company.id,
        name="Accounting",
        type=OrganizationalUnitType.DEPARTMENT,
    )

    session.add_all(
        [
            support,
            accounting,
        ]
    )

    await session.flush()

    support_l1 = OrganizationalUnit(
        company_id=company.id,
        parent_id=support.id,
        name="Support L1",
        type=OrganizationalUnitType.TEAM,
    )

    session.add(
        support_l1
    )

    await session.flush()

    support_l1_group = OrganizationalUnit(
        company_id=company.id,
        parent_id=support_l1.id,
        name="Support L1 Group",
        type=OrganizationalUnitType.GROUP,
    )

    session.add(
        support_l1_group
    )

    await session.flush()

    if actor_has_primary_unit:
        session.add(
            UnitMembership(
                company_membership_id=actor.id,
                unit_id=support.id,
                is_primary=True,
                is_active=True,
            )
        )

    session.add_all(
        [
            UnitMembership(
                company_membership_id=(
                    same_unit_target.id
                ),
                unit_id=support.id,
                is_primary=True,
                is_active=True,
            ),

            UnitMembership(
                company_membership_id=(
                    child_target.id
                ),
                unit_id=support_l1.id,
                is_primary=True,
                is_active=True,
            ),

            UnitMembership(
                company_membership_id=(
                    grandchild_target.id
                ),
                unit_id=support_l1_group.id,
                is_primary=True,
                is_active=True,
            ),

            UnitMembership(
                company_membership_id=(
                    other_branch_target.id
                ),
                unit_id=accounting.id,
                is_primary=True,
                is_active=True,
            ),
        ]
    )

    manager = Role(
        company_id=company.id,
        name="Support Manager",
    )

    trainee = Role(
        company_id=company.id,
        name="Support Trainee",
    )

    session.add_all(
        [
            manager,
            trainee,
        ]
    )

    await session.flush()

    session.add(
        MembershipRole(
            company_membership_id=actor.id,
            role_id=manager.id,
        )
    )

    session.add(
        RoleDelegation(
            manager_role_id=manager.id,
            assignable_role_id=trainee.id,
        )
    )

    if scope is not None:
        roles_assign = Permission(
            code="roles.assign",
            name="Assign roles",
            module="roles",
        )

        session.add(
            roles_assign
        )

        await session.flush()

        session.add(
            RolePermission(
                role_id=manager.id,
                permission_id=roles_assign.id,
                scope=scope,
            )
        )

    await session.flush()

    return {
        "company": company,
        "foreign_company": foreign_company,

        "actor": actor,

        "same_unit_target": same_unit_target,
        "child_target": child_target,
        "grandchild_target": grandchild_target,
        "other_branch_target": other_branch_target,
        "no_unit_target": no_unit_target,
        "foreign_target": foreign_target,

        "support": support,
        "support_l1": support_l1,
        "support_l1_group": support_l1_group,
        "accounting": accounting,

        "manager": manager,
        "trainee": trainee,
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


async def assign_trainee(
    client: AsyncClient,
    *,
    ctx,
    target: CompanyMembership,
    headers: dict[str, str],
):
    return await client.put(
        (
            f"/api/v1/members/"
            f"{target.id}/roles"
        ),
        headers=headers,
        json={
            "role_ids": [
                ctx["trainee"].id,
            ],
        },
    )


def response_role_ids(
    response,
) -> set[int]:
    return {
        role["id"]
        for role in response.json()
    }


@pytest.mark.asyncio
async def test_api_roles_assign_own_unit_can_assign_same_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await assign_trainee(
        api_client,
        ctx=ctx,
        target=ctx["same_unit_target"],
        headers=headers,
    )

    assert response.status_code == 200

    assert response_role_ids(
        response
    ) == {
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_api_roles_assign_own_unit_cannot_assign_child(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await assign_trainee(
        api_client,
        ctx=ctx,
        target=ctx["child_target"],
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }


@pytest.mark.asyncio
async def test_api_roles_assign_own_unit_tree_can_assign_child(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.OWN_UNIT_TREE,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await assign_trainee(
        api_client,
        ctx=ctx,
        target=ctx["child_target"],
        headers=headers,
    )

    assert response.status_code == 200

    assert response_role_ids(
        response
    ) == {
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_api_roles_assign_own_unit_tree_can_assign_grandchild(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.OWN_UNIT_TREE,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await assign_trainee(
        api_client,
        ctx=ctx,
        target=ctx["grandchild_target"],
        headers=headers,
    )

    assert response.status_code == 200

    assert response_role_ids(
        response
    ) == {
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_api_roles_assign_own_unit_tree_cannot_assign_other_branch(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.OWN_UNIT_TREE,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await assign_trainee(
        api_client,
        ctx=ctx,
        target=ctx["other_branch_target"],
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }


@pytest.mark.asyncio
async def test_api_roles_assign_company_can_assign_other_branch(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await assign_trainee(
        api_client,
        ctx=ctx,
        target=ctx["other_branch_target"],
        headers=headers,
    )

    assert response.status_code == 200

    assert response_role_ids(
        response
    ) == {
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_api_roles_assign_company_can_assign_target_without_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await assign_trainee(
        api_client,
        ctx=ctx,
        target=ctx["no_unit_target"],
        headers=headers,
    )

    assert response.status_code == 200

    assert response_role_ids(
        response
    ) == {
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_api_roles_assign_company_cannot_cross_company(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await assign_trainee(
        api_client,
        ctx=ctx,
        target=ctx["foreign_target"],
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }


@pytest.mark.asyncio
async def test_api_role_assignment_without_permission_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=None,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await assign_trainee(
        api_client,
        ctx=ctx,
        target=ctx["same_unit_target"],
        headers=headers,
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }


@pytest.mark.asyncio
async def test_api_unit_scope_without_actor_primary_unit_cannot_assign(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.OWN_UNIT_TREE,
        actor_has_primary_unit=False,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await assign_trainee(
        api_client,
        ctx=ctx,
        target=ctx["same_unit_target"],
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }


@pytest.mark.asyncio
async def test_api_assignable_roles_own_unit_can_read_same_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['same_unit_target'].id}"
            f"/roles/assignable"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert {
        role["id"]
        for role in response.json()
    } == {
        ctx["trainee"].id,
    }


@pytest.mark.asyncio
async def test_api_assignable_roles_own_unit_cannot_read_child(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['child_target'].id}"
            f"/roles/assignable"
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
async def test_api_assignable_roles_without_permission_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=None,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['same_unit_target'].id}"
            f"/roles/assignable"
        ),
        headers=headers,
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }


@pytest.mark.asyncio
async def test_api_assignable_roles_excludes_inactive_role(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session,
        scope=PermissionScope.COMPANY,
    )

    ctx["trainee"].is_active = False

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["actor"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['same_unit_target'].id}"
            f"/roles/assignable"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert response.json() == []