import pytest

from httpx import AsyncClient

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.system_roles import (
    SystemRoleKey,
)

from repositories.company_memberships import (
    get_company_membership_by_user,
)

from repositories.membership_roles import (
    get_membership_roles,
)

from repositories.users import (
    create_user,
)

from schemas.company import (
    CompanyChildCreate,
    CompanyCreate,
)

from services.company import (
    create_child_company_with_administrator,
    create_new_company,
)

from services.system_admin_access import (
    sync_system_administrator_company_access,
)


async def initialize_installation(
    api_client: AsyncClient,
) -> dict:
    response = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name":
                    "Main Company",

                "short_name":
                    "MAIN",
            },
        },
    )

    assert response.status_code == 201

    return response.json()


@pytest.mark.asyncio
async def test_system_admin_access_is_backfilled_for_existing_company(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup = await initialize_installation(
        api_client
    )


    legacy_company = (
        await create_new_company(
            db_session,
            CompanyCreate(
                name=
                    "Legacy Company",

                short_name=
                    "LEGACY",

                parent_id=
                    None,
            ),
        )
    )


    membership_before = (
        await get_company_membership_by_user(
            db_session,
            company_id=(
                legacy_company.id
            ),
            user_id=(
                setup["user_id"]
            ),
        )
    )


    assert membership_before is None


    await (
        sync_system_administrator_company_access(
            db_session
        )
    )


    membership = (
        await get_company_membership_by_user(
            db_session,
            company_id=(
                legacy_company.id
            ),
            user_id=(
                setup["user_id"]
            ),
        )
    )


    assert membership is not None

    assert membership.is_active is True


    roles = await get_membership_roles(
        db_session,
        membership.id,
    )


    assert any(
        role.system_key
        == (
            SystemRoleKey
            .ADMINISTRATOR
            .value
        )
        for role in roles
    )


@pytest.mark.asyncio
async def test_system_admin_gets_access_when_another_user_creates_company(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup = await initialize_installation(
        api_client
    )


    regular_admin = await create_user(
        db_session,
        username=
            "company-admin",

        password_hash=
            "test-password-hash",
    )

    await db_session.commit()

    await db_session.refresh(
        regular_admin
    )


    child = (
        await create_child_company_with_administrator(
            db_session,
            parent_company_id=(
                setup["company_id"]
            ),
            administrator_user_id=(
                regular_admin.id
            ),
            data=CompanyChildCreate(
                name=
                    "Child Company",

                short_name=
                    "CHILD",
            ),
        )
    )


    regular_membership = (
        await get_company_membership_by_user(
            db_session,
            company_id=child.id,
            user_id=regular_admin.id,
        )
    )


    assert regular_membership is not None


    system_admin_membership = (
        await get_company_membership_by_user(
            db_session,
            company_id=child.id,
            user_id=(
                setup["user_id"]
            ),
        )
    )


    assert (
        system_admin_membership
        is not None
    )

    assert (
        system_admin_membership
        .is_active
        is True
    )


    roles = await get_membership_roles(
        db_session,
        system_admin_membership.id,
    )


    assert any(
        role.system_key
        == (
            SystemRoleKey
            .ADMINISTRATOR
            .value
        )
        for role in roles
    )