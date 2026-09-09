import asyncio

import pytest

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from core.installation import (
    InstallationState,
)
from core.security.password import (
    verify_password,
)
from core.system_roles import (
    SYSTEM_ROLE_TEMPLATES,
    SystemRoleKey,
)

from repositories.company import (
    get_companies,
)
from repositories.membership_roles import (
    get_membership_roles,
)
from repositories.permissions import (
    get_permissions,
)
from repositories.roles import (
    get_system_role_by_key,
)
from repositories.users import (
    get_user_by_username,
)

import services.installation as (
    installation_service
)

from services.installation import (
    InstallationInitializationResult,
    InstallationNotAllowedError,
    get_installation_status,
    initialize_installation,
)


@pytest.mark.asyncio
async def test_initialize_installation_creates_complete_first_run(
    db_session: AsyncSession,
):
    result = await initialize_installation(
        db_session,
        company_name="Main Company",
        company_short_name="MAIN",
        username="Admin",
        password="password123",
    )

    assert (
        result.company.name
        == "Main Company"
    )

    assert (
        result.company.short_name
        == "MAIN"
    )

    #
    # Username нормализуется.
    #
    assert result.user.username == "admin"

    assert verify_password(
        "password123",
        result.user.password_hash,
    )

    assert (
        result.membership.company_id
        == result.company.id
    )

    assert (
        result.membership.user_id
        == result.user.id
    )

    assert (
        result.administrator_role.system_key
        == (
            SystemRoleKey
            .ADMINISTRATOR
            .value
        )
    )

    membership_roles = (
        await get_membership_roles(
            db_session,
            result.membership.id,
        )
    )

    assert {
        role.id
        for role
        in membership_roles
    } == {
        result.administrator_role.id
    }

    #
    # Все четыре system roles существуют.
    #
    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        role = (
            await get_system_role_by_key(
                db_session,
                company_id=(
                    result.company.id
                ),
                system_key=(
                    template.key.value
                ),
            )
        )

        assert role is not None

    status = (
        await get_installation_status(
            db_session
        )
    )

    assert (
        status.state
        == InstallationState.INSTALLED
    )

    assert status.setup_allowed is False
    assert status.has_administrator is True


@pytest.mark.asyncio
async def test_second_installation_is_rejected(
    db_session: AsyncSession,
):
    await initialize_installation(
        db_session,
        company_name="Main Company",
        company_short_name=None,
        username="admin",
        password="password123",
    )

    with pytest.raises(
        InstallationNotAllowedError
    ) as exc:
        await initialize_installation(
            db_session,
            company_name="Second Company",
            company_short_name=None,
            username="second-admin",
            password="password456",
        )

    assert (
        exc.value.state
        == InstallationState.INSTALLED
    )

    companies = await get_companies(
        db_session
    )

    assert len(companies) == 1

    second_user = (
        await get_user_by_username(
            db_session,
            "second-admin",
        )
    )

    assert second_user is None


@pytest.mark.asyncio
async def test_failed_installation_rolls_back_entire_bootstrap(
    db_session: AsyncSession,
    monkeypatch,
):
    async def fail_membership_roles(
        *args,
        **kwargs,
    ):
        raise RuntimeError(
            "Simulated bootstrap failure"
        )

    monkeypatch.setattr(
        installation_service,
        "create_membership_roles",
        fail_membership_roles,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated bootstrap failure",
    ):
        await initialize_installation(
            db_session,
            company_name="Broken Company",
            company_short_name=None,
            username="broken-admin",
            password="password123",
        )

    #
    # Даже permissions должны откатиться,
    # поскольку intermediate COMMIT больше нет.
    #
    permissions = await get_permissions(
        db_session,
        active_only=True,
    )

    assert permissions == []

    companies = await get_companies(
        db_session
    )

    assert companies == []

    user = await get_user_by_username(
        db_session,
        "broken-admin",
    )

    assert user is None

    status = (
        await get_installation_status(
            db_session
        )
    )

    assert (
        status.state
        == InstallationState.READY
    )

    assert status.setup_allowed is True


@pytest.mark.asyncio
async def test_concurrent_installation_allows_only_one_initializer(
    db_session: AsyncSession,
):
    bind = db_session.bind

    assert bind is not None

    session_factory = (
        async_sessionmaker(
            bind=bind,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    )

    async def run_installation(
        username: str,
    ):
        async with (
            session_factory()
        ) as session:
            return (
                await initialize_installation(
                    session,
                    company_name=(
                        f"Company {username}"
                    ),
                    company_short_name=None,
                    username=username,
                    password="password123",
                )
            )

    results = await asyncio.gather(
        run_installation(
            "admin-one"
        ),
        run_installation(
            "admin-two"
        ),
        return_exceptions=True,
    )

    successful = [
        result
        for result in results
        if isinstance(
            result,
            InstallationInitializationResult,
        )
    ]

    rejected = [
        result
        for result in results
        if isinstance(
            result,
            InstallationNotAllowedError,
        )
    ]

    assert len(successful) == 1
    assert len(rejected) == 1

    assert (
        rejected[0].state
        == InstallationState.INSTALLED
    )

    companies = await get_companies(
        db_session
    )

    assert len(companies) == 1

    status = (
        await get_installation_status(
            db_session
        )
    )

    assert (
        status.state
        == InstallationState.INSTALLED
    )