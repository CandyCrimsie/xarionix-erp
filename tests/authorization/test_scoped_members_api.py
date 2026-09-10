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

from repositories.unit_memberships import (
    get_primary_unit_id,
)


async def create_membership(
    session: AsyncSession,
    *,
    company: Company,
    username: str,
) -> CompanyMembership:
    user = User(
        username=username,
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

    return membership


async def create_user(
    session: AsyncSession,
    *,
    username: str,
) -> User:
    user = User(
        username=username,
        password_hash="test",
    )

    session.add(user)

    await session.flush()

    return user


async def create_role_with_members_read(
    session: AsyncSession,
    *,
    company: Company,
    membership: CompanyMembership,
    scope: PermissionScope,
) -> None:
    permission = Permission(
        code="members.read",
        name="Read members",
        module="members",
    )

    role = Role(
        company_id=company.id,
        name=f"Reader {scope.value}",
    )

    session.add_all(
        [
            permission,
            role,
        ]
    )

    await session.flush()

    session.add_all(
        [
            RolePermission(
                role_id=role.id,
                permission_id=permission.id,
                scope=scope,
            ),

            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=role.id,
            ),
        ]
    )

    await session.flush()


async def create_role_with_members_manage(
    session: AsyncSession,
    *,
    company: Company,
    membership: CompanyMembership,
    scope: PermissionScope,
) -> None:
    permission = Permission(
        code="members.manage",
        name="Manage members",
        module="members",
    )

    role = Role(
        company_id=company.id,
        name=f"Manager {scope.value}",
    )

    session.add_all(
        [
            permission,
            role,
        ]
    )

    await session.flush()

    session.add_all(
        [
            RolePermission(
                role_id=role.id,
                permission_id=permission.id,
                scope=scope,
            ),

            MembershipRole(
                company_membership_id=(
                    membership.id
                ),
                role_id=role.id,
            ),
        ]
    )

    await session.flush()


async def create_context(
    session: AsyncSession,
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

    support = OrganizationalUnit(
        company_id=company.id,
        name="Support",
        type=(
            OrganizationalUnitType.DEPARTMENT
        ),
    )

    support_l1 = OrganizationalUnit(
        company_id=company.id,
        name="Support L1",
        type=OrganizationalUnitType.TEAM,
    )

    noc = OrganizationalUnit(
        company_id=company.id,
        name="NOC",
        type=(
            OrganizationalUnitType.DEPARTMENT
        ),
    )

    session.add_all(
        [
            support,
            support_l1,
            noc,
        ]
    )

    await session.flush()

    support_l1.parent_id = support.id

    current = await create_membership(
        session,
        company=company,
        username="current-user",
    )

    same_unit = await create_membership(
        session,
        company=company,
        username="same-unit-user",
    )

    child_unit = await create_membership(
        session,
        company=company,
        username="child-unit-user",
    )

    other_unit = await create_membership(
        session,
        company=company,
        username="other-unit-user",
    )

    without_unit = await create_membership(
        session,
        company=company,
        username="without-unit-user",
    )

    foreign = await create_membership(
        session,
        company=foreign_company,
        username="foreign-user",
    )

    session.add_all(
        [
            UnitMembership(
                company_membership_id=(
                    current.id
                ),
                unit_id=support.id,
                is_primary=True,
            ),

            UnitMembership(
                company_membership_id=(
                    same_unit.id
                ),
                unit_id=support.id,
                is_primary=True,
            ),

            UnitMembership(
                company_membership_id=(
                    child_unit.id
                ),
                unit_id=support_l1.id,
                is_primary=True,
            ),

            UnitMembership(
                company_membership_id=(
                    other_unit.id
                ),
                unit_id=noc.id,
                is_primary=True,
            ),
        ]
    )

    await session.flush()

    return {
        "company": company,
        "foreign_company": foreign_company,

        "support": support,
        "support_l1": support_l1,
        "noc": noc,

        "current": current,
        "same_unit": same_unit,
        "child_unit": child_unit,
        "other_unit": other_unit,
        "without_unit": without_unit,
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
        session_id=(
            created_session.session_id
        ),
    )

    return {
        "Authorization": (
            f"Bearer {access_token}"
        ),
        "X-Company-Id": str(
            company_id
        ),
    }


def response_membership_ids(
    response,
) -> set[int]:
    return {
        item["id"]
        for item in response.json()
    }


async def assign_test_role(
    session: AsyncSession,
    *,
    company: Company,
    membership: CompanyMembership,
    name: str,
) -> Role:
    role = Role(
        company_id=company.id,
        name=name,
    )

    session.add(role)

    await session.flush()

    session.add(
        MembershipRole(
            company_membership_id=(
                membership.id
            ),
            role_id=role.id,
        )
    )

    await session.flush()

    return role


@pytest.mark.asyncio
async def test_api_members_self_scope(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.SELF,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert response_membership_ids(
        response
    ) == {
        ctx["current"].id,
    }


@pytest.mark.asyncio
async def test_api_members_own_unit_scope(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert response_membership_ids(
        response
    ) == {
        ctx["current"].id,
        ctx["same_unit"].id,
    }


@pytest.mark.asyncio
async def test_api_members_own_unit_tree_scope(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert response_membership_ids(
        response
    ) == {
        ctx["current"].id,
        ctx["same_unit"].id,
        ctx["child_unit"].id,
    }


@pytest.mark.asyncio
async def test_api_members_company_scope(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert response_membership_ids(
        response
    ) == {
        ctx["current"].id,
        ctx["same_unit"].id,
        ctx["child_unit"].id,
        ctx["other_unit"].id,
        ctx["without_unit"].id,
    }


@pytest.mark.asyncio
async def test_api_members_without_permission_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }


@pytest.mark.asyncio
async def test_api_members_path_company_must_match_context(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['foreign_company'].id}/members"
        ),
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company not found",
    }


@pytest.mark.asyncio
async def test_api_target_self_can_read_self(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.SELF,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['current'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == (
        ctx["current"].id
    )


@pytest.mark.asyncio
async def test_api_target_self_cannot_read_other(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.SELF,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['same_unit'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }


@pytest.mark.asyncio
async def test_api_target_own_unit_can_read_same_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['same_unit'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == (
        ctx["same_unit"].id
    )


@pytest.mark.asyncio
async def test_api_target_own_unit_cannot_read_child(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['child_unit'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }


@pytest.mark.asyncio
async def test_api_target_own_unit_tree_can_read_child(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['child_unit'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == (
        ctx["child_unit"].id
    )


@pytest.mark.asyncio
async def test_api_target_own_unit_tree_cannot_read_other_branch(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['other_unit'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }


@pytest.mark.asyncio
async def test_api_target_company_can_read_company_member(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['other_unit'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == (
        ctx["other_unit"].id
    )


@pytest.mark.asyncio
async def test_api_target_company_cannot_cross_company(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['foreign'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }


@pytest.mark.asyncio
async def test_api_target_without_permission_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['current'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }


@pytest.mark.asyncio
async def test_api_target_path_company_must_match_context(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['foreign_company'].id}/members/"
            f"{ctx['foreign'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company not found",
    }


@pytest.mark.asyncio
async def test_api_update_own_unit_can_update_same_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['same_unit'].id}"
        ),
        headers=headers,
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == (
        ctx["same_unit"].id
    )
    assert (
        response.json()["is_active"]
        is False
    )


@pytest.mark.asyncio
async def test_api_update_own_unit_cannot_update_child(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['child_unit'].id}"
        ),
        headers=headers,
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }

    assert (
        ctx["child_unit"].is_active
        is True
    )


@pytest.mark.asyncio
async def test_api_update_own_unit_tree_can_update_child(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['child_unit'].id}"
        ),
        headers=headers,
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == (
        ctx["child_unit"].id
    )
    assert (
        response.json()["is_active"]
        is False
    )


@pytest.mark.asyncio
async def test_api_update_own_unit_tree_cannot_update_other_branch(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['other_unit'].id}"
        ),
        headers=headers,
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }

    assert (
        ctx["other_unit"].is_active
        is True
    )


@pytest.mark.asyncio
async def test_api_update_company_can_update_company_member(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['other_unit'].id}"
        ),
        headers=headers,
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == (
        ctx["other_unit"].id
    )
    assert (
        response.json()["is_active"]
        is False
    )


@pytest.mark.asyncio
async def test_api_update_company_cannot_cross_company(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['foreign'].id}"
        ),
        headers=headers,
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company membership not found",
    }

    assert ctx["foreign"].is_active is True


@pytest.mark.asyncio
async def test_api_update_without_manage_permission_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['same_unit'].id}"
        ),
        headers=headers,
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }

    assert (
        ctx["same_unit"].is_active
        is True
    )


@pytest.mark.asyncio
async def test_api_update_read_permission_does_not_grant_manage(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members/"
            f"{ctx['same_unit'].id}"
        ),
        headers=headers,
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }

    assert (
        ctx["same_unit"].is_active
        is True
    )


@pytest.mark.asyncio
async def test_api_update_path_company_must_match_context(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{ctx['foreign_company'].id}/members/"
            f"{ctx['foreign'].id}"
        ),
        headers=headers,
        json={
            "is_active": False,
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company not found",
    }


@pytest.mark.asyncio
async def test_api_create_own_unit_can_create_in_own_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    user = await create_user(
        db_session,
        username="api-new-own-unit-user",
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": user.id,
            "primary_unit_id": (
                ctx["support"].id
            ),
        },
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == user.id

    membership_id = response.json()["id"]

    primary_unit_id = await get_primary_unit_id(
        db_session,
        membership_id,
    )

    assert primary_unit_id == (
        ctx["support"].id
    )


@pytest.mark.asyncio
async def test_api_create_own_unit_cannot_create_in_child_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    user = await create_user(
        db_session,
        username="api-child-denied-user",
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": user.id,
            "primary_unit_id": (
                ctx["support_l1"].id
            ),
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Organizational unit not found",
    }


@pytest.mark.asyncio
async def test_api_create_own_unit_requires_primary_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    user = await create_user(
        db_session,
        username="api-no-unit-user",
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": user.id,
        },
    )

    assert response.status_code == 400

    assert response.json() == {
        "detail": (
            "Primary unit is required "
            "for this permission scope"
        ),
    }


@pytest.mark.asyncio
async def test_api_create_own_unit_tree_can_create_in_child(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    user = await create_user(
        db_session,
        username="api-tree-user",
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": user.id,
            "primary_unit_id": (
                ctx["support_l1"].id
            ),
        },
    )

    assert response.status_code == 201

    primary_unit_id = await get_primary_unit_id(
        db_session,
        response.json()["id"],
    )

    assert primary_unit_id == (
        ctx["support_l1"].id
    )


@pytest.mark.asyncio
async def test_api_create_own_unit_tree_cannot_create_in_other_branch(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    user = await create_user(
        db_session,
        username="api-other-branch-user",
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": user.id,
            "primary_unit_id": ctx["noc"].id,
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Organizational unit not found",
    }


@pytest.mark.asyncio
async def test_api_create_company_can_create_without_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    user = await create_user(
        db_session,
        username="api-company-user",
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": user.id,
        },
    )

    assert response.status_code == 201

    primary_unit_id = await get_primary_unit_id(
        db_session,
        response.json()["id"],
    )

    assert primary_unit_id is None


@pytest.mark.asyncio
async def test_api_create_company_can_create_with_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    user = await create_user(
        db_session,
        username="api-company-unit-user",
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": user.id,
            "primary_unit_id": ctx["noc"].id,
        },
    )

    assert response.status_code == 201

    primary_unit_id = await get_primary_unit_id(
        db_session,
        response.json()["id"],
    )

    assert primary_unit_id == ctx["noc"].id


@pytest.mark.asyncio
async def test_api_create_company_cannot_use_foreign_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    foreign_unit = OrganizationalUnit(
        company_id=ctx["foreign_company"].id,
        name="Foreign Department",
        type=(
            OrganizationalUnitType.DEPARTMENT
        ),
    )

    db_session.add(foreign_unit)

    user = await create_user(
        db_session,
        username="api-foreign-unit-user",
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": user.id,
            "primary_unit_id": foreign_unit.id,
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Organizational unit not found",
    }


@pytest.mark.asyncio
async def test_api_create_without_manage_permission_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    user = await create_user(
        db_session,
        username="api-create-denied-user",
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": user.id,
            "primary_unit_id": (
                ctx["support"].id
            ),
        },
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }


@pytest.mark.asyncio
async def test_api_create_existing_membership_returns_conflict(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": (
                ctx["same_unit"].user_id
            ),
            "primary_unit_id": (
                ctx["support"].id
            ),
        },
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": (
            "User is already a member "
            "of this company"
        ),
    }


@pytest.mark.asyncio
async def test_api_create_path_company_must_match_context(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    user = await create_user(
        db_session,
        username="api-path-mismatch-user",
    )

    await create_role_with_members_manage(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{ctx['foreign_company'].id}/members"
        ),
        headers=headers,
        json={
            "user_id": user.id,
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company not found",
    }


@pytest.mark.asyncio
async def test_api_members_returns_member_summary(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}/members"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    members = {
        item["id"]: item
        for item in response.json()
    }


    same_unit = members[
        ctx["same_unit"].id
    ]

    assert same_unit["user_id"] == (
        ctx["same_unit"].user_id
    )

    assert (
        same_unit["username"]
        == "same-unit-user"
    )

    assert (
        same_unit["user_is_active"]
        is True
    )

    assert (
        same_unit["is_active"]
        is True
    )

    assert (
        same_unit["primary_unit_id"]
        == ctx["support"].id
    )

    assert (
        same_unit["primary_unit_name"]
        == "Support"
    )

    assert (
        same_unit["primary_unit_type"]
        == "department"
    )


    without_unit = members[
        ctx["without_unit"].id
    ]

    assert (
        without_unit["username"]
        == "without-unit-user"
    )

    assert (
        without_unit["primary_unit_id"]
        is None
    )

    assert (
        without_unit["primary_unit_name"]
        is None
    )

    assert (
        without_unit["primary_unit_type"]
        is None
    )


@pytest.mark.asyncio
async def test_api_membership_roles_own_unit_can_read_same_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    role = await assign_test_role(
        db_session,
        company=ctx["company"],
        membership=ctx["same_unit"],
        name="Same Unit Role",
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['same_unit'].id}/roles"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert {
        item["id"]
        for item in response.json()
    } == {
        role.id,
    }


@pytest.mark.asyncio
async def test_api_membership_roles_own_unit_cannot_read_child_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=PermissionScope.OWN_UNIT,
    )

    await assign_test_role(
        db_session,
        company=ctx["company"],
        membership=ctx["child_unit"],
        name="Child Unit Role",
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['child_unit'].id}/roles"
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
async def test_api_membership_roles_own_unit_tree_can_read_child_unit(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await create_role_with_members_read(
        db_session,
        company=ctx["company"],
        membership=ctx["current"],
        scope=(
            PermissionScope.OWN_UNIT_TREE
        ),
    )

    role = await assign_test_role(
        db_session,
        company=ctx["company"],
        membership=ctx["child_unit"],
        name="Child Unit Role",
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=ctx["current"].user_id,
        company_id=ctx["company"].id,
    )

    response = await api_client.get(
        (
            f"/api/v1/members/"
            f"{ctx['child_unit'].id}/roles"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert {
        item["id"]
        for item in response.json()
    } == {
        role.id,
    }