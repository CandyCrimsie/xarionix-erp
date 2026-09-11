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

from models.permissions import (
    Permission,
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
):
    company = Company(
        name="Main Company",
    )

    session.add(
        company
    )

    await session.flush()


    support = OrganizationalUnit(
        company_id=company.id,
        name="Support",
        type=(
            OrganizationalUnitType
                .DEPARTMENT
        ),
    )

    support_l1 = OrganizationalUnit(
        company_id=company.id,
        name="Support L1",
        type=(
            OrganizationalUnitType.TEAM
        ),
    )

    noc = OrganizationalUnit(
        company_id=company.id,
        name="NOC",
        type=(
            OrganizationalUnitType
                .DEPARTMENT
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

    support_l1.parent_id = (
        support.id
    )


    user = User(
        username="unit-reader",
        password_hash="test",
    )

    session.add(
        user
    )

    await session.flush()


    membership = CompanyMembership(
        user_id=user.id,
        company_id=company.id,
    )

    session.add(
        membership
    )

    await session.flush()


    session.add(
        UnitMembership(
            company_membership_id=(
                membership.id
            ),
            unit_id=support.id,
            is_primary=True,
        )
    )

    await session.flush()


    return {
        "company":
            company,

        "membership":
            membership,

        "support":
            support,

        "support_l1":
            support_l1,

        "noc":
            noc,
    }


async def grant_units_read(
    session: AsyncSession,
    *,
    company: Company,
    membership: CompanyMembership,
    scope: PermissionScope,
) -> None:
    permission = Permission(
        code=(
            "organizational_units.read"
        ),
        name="Read units",
        module="organizational_units",
    )

    role = Role(
        company_id=company.id,
        name=(
            f"Unit Reader "
            f"{scope.value}"
        ),
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
                permission_id=(
                    permission.id
                ),
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


async def create_auth_headers(
    *,
    user_id: int,
    company_id: int,
) -> dict[str, str]:
    created_session = (
        await create_session(
            user_id=user_id,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
    )

    access_token = (
        create_access_token(
            user_id=user_id,
            session_id=(
                created_session
                    .session_id
            ),
        )
    )

    return {
        "Authorization":
            f"Bearer {access_token}",

        "X-Company-Id":
            str(company_id),
    }


def unit_ids(
    response,
) -> set[int]:
    return {
        item["id"]
        for item
        in response.json()
    }


@pytest.mark.asyncio
async def test_api_units_own_unit_scope(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await grant_units_read(
        db_session,
        company=ctx["company"],
        membership=ctx["membership"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=(
            ctx["membership"].user_id
        ),
        company_id=(
            ctx["company"].id
        ),
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}"
            f"/units"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert unit_ids(
        response
    ) == {
        ctx["support"].id,
    }


@pytest.mark.asyncio
async def test_api_units_own_unit_tree_scope(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await grant_units_read(
        db_session,
        company=ctx["company"],
        membership=ctx["membership"],
        scope=(
            PermissionScope
                .OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=(
            ctx["membership"].user_id
        ),
        company_id=(
            ctx["company"].id
        ),
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}"
            f"/units"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert unit_ids(
        response
    ) == {
        ctx["support"].id,
        ctx["support_l1"].id,
    }


@pytest.mark.asyncio
async def test_api_units_company_scope(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await grant_units_read(
        db_session,
        company=ctx["company"],
        membership=ctx["membership"],
        scope=PermissionScope.COMPANY,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=(
            ctx["membership"].user_id
        ),
        company_id=(
            ctx["company"].id
        ),
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}"
            f"/units"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert unit_ids(
        response
    ) == {
        ctx["support"].id,
        ctx["support_l1"].id,
        ctx["noc"].id,
    }


@pytest.mark.asyncio
async def test_api_unit_own_unit_cannot_read_child(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await grant_units_read(
        db_session,
        company=ctx["company"],
        membership=ctx["membership"],
        scope=PermissionScope.OWN_UNIT,
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=(
            ctx["membership"].user_id
        ),
        company_id=(
            ctx["company"].id
        ),
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}"
            f"/units/"
            f"{ctx['support_l1'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail":
            "Organizational unit not found",
    }


@pytest.mark.asyncio
async def test_api_unit_tree_can_read_child(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await grant_units_read(
        db_session,
        company=ctx["company"],
        membership=ctx["membership"],
        scope=(
            PermissionScope
                .OWN_UNIT_TREE
        ),
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=(
            ctx["membership"].user_id
        ),
        company_id=(
            ctx["company"].id
        ),
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}"
            f"/units/"
            f"{ctx['support_l1'].id}"
        ),
        headers=headers,
    )

    assert response.status_code == 200

    assert (
        response.json()["id"]
        == ctx["support_l1"].id
    )


@pytest.mark.asyncio
async def test_api_units_without_permission_is_forbidden(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    ctx = await create_context(
        db_session
    )

    await db_session.commit()

    headers = await create_auth_headers(
        user_id=(
            ctx["membership"].user_id
        ),
        company_id=(
            ctx["company"].id
        ),
    )

    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{ctx['company'].id}"
            f"/units"
        ),
        headers=headers,
    )

    assert response.status_code == 403

    assert response.json() == {
        "detail": "Permission denied",
    }