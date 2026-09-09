import pytest

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.installation import (
    InstallationState,
)
from core.security.password import (
    hash_password,
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

from repositories.company_memberships import (
    create_company_membership,
)
from repositories.membership_roles import (
    create_membership_roles,
)
from repositories.roles import (
    get_system_role_by_key,
)
from repositories.users import (
    create_user,
)

from services.installation import (
    get_installation_status,
)
from services.permissions import (
    sync_permissions,
)
from services.system_roles import (
    sync_system_roles_for_company,
)


@pytest.mark.asyncio
async def test_empty_database_is_ready_for_installation(
    db_session: AsyncSession,
):
    status = await get_installation_status(
        db_session
    )

    assert (
        status.state
        == InstallationState.READY
    )

    assert status.setup_allowed is True

    assert status.has_users is False
    assert status.has_companies is False
    assert status.has_memberships is False
    assert status.has_administrator is False


@pytest.mark.asyncio
async def test_existing_user_without_installation_is_inconsistent(
    db_session: AsyncSession,
):
    await create_user(
        db_session,
        username="orphan-user",
        password_hash=hash_password(
            "password123"
        ),
    )

    await db_session.commit()

    status = await get_installation_status(
        db_session
    )

    assert (
        status.state
        == InstallationState.INCONSISTENT
    )

    assert status.setup_allowed is False

    assert status.has_users is True
    assert status.has_companies is False
    assert status.has_memberships is False
    assert status.has_administrator is False


@pytest.mark.asyncio
async def test_existing_company_without_admin_is_inconsistent(
    db_session: AsyncSession,
):
    company = Company(
        name="Existing Company",
    )

    db_session.add(
        company
    )

    await db_session.commit()

    status = await get_installation_status(
        db_session
    )

    assert (
        status.state
        == InstallationState.INCONSISTENT
    )

    assert status.setup_allowed is False

    assert status.has_companies is True
    assert status.has_administrator is False


@pytest.mark.asyncio
async def test_membership_without_administrator_is_inconsistent(
    db_session: AsyncSession,
):
    user = await create_user(
        db_session,
        username="regular-user",
        password_hash=hash_password(
            "password123"
        ),
    )

    company = Company(
        name="Main Company",
    )

    db_session.add(
        company
    )

    await db_session.flush()

    await create_company_membership(
        db_session,
        user_id=user.id,
        company_id=company.id,
    )

    await db_session.commit()

    status = await get_installation_status(
        db_session
    )

    assert (
        status.state
        == InstallationState.INCONSISTENT
    )

    assert status.setup_allowed is False

    assert status.has_users is True
    assert status.has_companies is True
    assert status.has_memberships is True
    assert status.has_administrator is False


@pytest.mark.asyncio
async def test_active_administrator_membership_marks_installation_complete(
    db_session: AsyncSession,
    clean_test_redis,
):
    await sync_permissions(
        db_session
    )

    company = Company(
        name="Main Company",
    )

    db_session.add(
        company
    )

    await db_session.flush()

    company_id = company.id

    await db_session.commit()

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
    )

    administrator = (
        await get_system_role_by_key(
            db_session,
            company_id=company_id,
            system_key=(
                SystemRoleKey
                .ADMINISTRATOR
                .value
            ),
        )
    )

    assert administrator is not None

    user = await create_user(
        db_session,
        username="admin",
        password_hash=hash_password(
            "password123"
        ),
    )

    membership = (
        await create_company_membership(
            db_session,
            user_id=user.id,
            company_id=company_id,
        )
    )

    await create_membership_roles(
        db_session,
        company_membership_id=(
            membership.id
        ),
        role_ids=[
            administrator.id,
        ],
    )

    await db_session.commit()

    status = await get_installation_status(
        db_session
    )

    assert (
        status.state
        == InstallationState.INSTALLED
    )

    assert status.setup_allowed is False

    assert status.has_users is True
    assert status.has_companies is True
    assert status.has_memberships is True
    assert status.has_administrator is True


@pytest.mark.asyncio
async def test_inactive_administrator_does_not_mark_installation_complete(
    db_session: AsyncSession,
    clean_test_redis,
):
    await sync_permissions(
        db_session
    )

    company = Company(
        name="Main Company",
    )

    db_session.add(
        company
    )

    await db_session.flush()

    company_id = company.id

    await db_session.commit()

    await sync_system_roles_for_company(
        db_session,
        company_id=company_id,
    )

    administrator = (
        await get_system_role_by_key(
            db_session,
            company_id=company_id,
            system_key=(
                SystemRoleKey
                .ADMINISTRATOR
                .value
            ),
        )
    )

    assert administrator is not None

    user = await create_user(
        db_session,
        username="disabled-admin",
        password_hash=hash_password(
            "password123"
        ),
    )

    membership = (
        await create_company_membership(
            db_session,
            user_id=user.id,
            company_id=company_id,
        )
    )

    await create_membership_roles(
        db_session,
        company_membership_id=(
            membership.id
        ),
        role_ids=[
            administrator.id,
        ],
    )

    user.is_active = False

    await db_session.commit()

    status = await get_installation_status(
        db_session
    )

    assert (
        status.state
        == InstallationState.INCONSISTENT
    )

    assert status.setup_allowed is False
    assert status.has_administrator is False