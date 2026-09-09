from dataclasses import (
    dataclass,
)

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.installation import (
    InstallationState,
)

from repositories.installation import (
    has_active_administrator_membership,
    has_companies,
    has_company_memberships,
    has_users,
)


@dataclass(
    slots=True,
    frozen=True,
)
class InstallationStatus:
    state: InstallationState

    setup_allowed: bool

    has_users: bool
    has_companies: bool
    has_memberships: bool

    has_administrator: bool


async def get_installation_status(
    session: AsyncSession,
) -> InstallationStatus:
    users_exist = await has_users(
        session
    )

    companies_exist = await has_companies(
        session
    )

    memberships_exist = (
        await has_company_memberships(
            session
        )
    )

    administrator_exists = (
        await has_active_administrator_membership(
            session
        )
    )

    #
    # Единственное состояние, в котором
    # разрешена первоначальная установка:
    # абсолютно пустая business DB.
    #
    if (
        not users_exist
        and not companies_exist
        and not memberships_exist
    ):
        return InstallationStatus(
            state=InstallationState.READY,
            setup_allowed=True,
            has_users=False,
            has_companies=False,
            has_memberships=False,
            has_administrator=False,
        )

    #
    # Наличие полноценного активного
    # Administrator membership означает,
    # что установка завершена.
    #
    if administrator_exists:
        return InstallationStatus(
            state=(
                InstallationState.INSTALLED
            ),
            setup_allowed=False,
            has_users=users_exist,
            has_companies=companies_exist,
            has_memberships=(
                memberships_exist
            ),
            has_administrator=True,
        )

    #
    # Какие-то production данные уже есть,
    # но полноценного Administrator нет.
    #
    # Автоматически bootstrap здесь
    # запрещён из соображений безопасности.
    #
    return InstallationStatus(
        state=(
            InstallationState.INCONSISTENT
        ),
        setup_allowed=False,
        has_users=users_exist,
        has_companies=companies_exist,
        has_memberships=(
            memberships_exist
        ),
        has_administrator=False,
    )