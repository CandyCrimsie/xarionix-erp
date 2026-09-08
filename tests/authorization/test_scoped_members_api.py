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