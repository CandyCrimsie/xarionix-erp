from dataclasses import (
    dataclass,
)

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
from models.roles import Role
from models.users import User

from repositories.company import (
    create_company,
)
from repositories.company_memberships import (
    create_company_membership,
)
from repositories.installation import (
    acquire_installation_lock,
    has_active_administrator_membership,
    has_companies,
    has_company_memberships,
    has_users,
)
from repositories.membership_roles import (
    create_membership_roles,
)
from repositories.users import (
    create_user,
)

from services.permissions import (
    sync_permissions_in_transaction,
)
from services.system_roles import (
    sync_system_roles_for_company_in_transaction,
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


@dataclass(
    slots=True,
    frozen=True,
)
class InstallationInitializationResult:
    company: Company

    user: User
    membership: CompanyMembership

    administrator_role: Role


class InstallationNotAllowedError(
    Exception
):
    def __init__(
        self,
        state: InstallationState,
    ) -> None:
        self.state = state

        super().__init__(
            (
                "Installation is not "
                f"allowed in state: "
                f"{state.value}"
            )
        )


class AdministratorSystemRoleUnavailableError(
    Exception
):
    pass


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


async def initialize_installation(
    session: AsyncSession,
    *,
    company_name: str,
    company_short_name: str | None,
    username: str,
    password: str,
) -> InstallationInitializationResult:
    try:
        #
        # Два параллельных installer request
        # больше не смогут одновременно
        # увидеть READY.
        #
        await acquire_installation_lock(
            session
        )

        #
        # Проверяем состояние обязательно
        # ПОСЛЕ получения lock.
        #
        status = (
            await get_installation_status(
                session
            )
        )

        if not status.setup_allowed:
            raise InstallationNotAllowedError(
                status.state
            )

        #
        # Permission catalog создаётся
        # внутри той же транзакции.
        #
        await sync_permissions_in_transaction(
            session
        )

        company_name = (
            company_name.strip()
        )

        company_short_name = (
            company_short_name.strip()
            if company_short_name
            is not None
            else None
        )

        if not company_short_name:
            company_short_name = None

        company = await create_company(
            session,
            name=company_name,
            short_name=company_short_name,
            parent_id=None,
        )

        (
            system_roles,
            _,
        ) = (
            await sync_system_roles_for_company_in_transaction(
                session,
                company_id=company.id,
            )
        )

        administrator_role = next(
            (
                role
                for role in system_roles
                if (
                    role.system_key
                    == (
                        SystemRoleKey
                        .ADMINISTRATOR
                        .value
                    )
                )
            ),
            None,
        )

        if administrator_role is None:
            raise (
                AdministratorSystemRoleUnavailableError
            )

        normalized_username = (
            username.strip().lower()
        )

        user = await create_user(
            session,
            username=normalized_username,
            password_hash=hash_password(
                password
            ),
        )

        membership = (
            await create_company_membership(
                session,
                user_id=user.id,
                company_id=company.id,
            )
        )

        await create_membership_roles(
            session,
            company_membership_id=(
                membership.id
            ),
            role_ids=[
                administrator_role.id,
            ],
        )

        #
        # ЕДИНСТВЕННЫЙ COMMIT
        # всей initial installation.
        #
        await session.commit()

    except Exception:
        await session.rollback()
        raise

    await session.refresh(
        company
    )
    await session.refresh(
        user
    )
    await session.refresh(
        membership
    )
    await session.refresh(
        administrator_role
    )

    return (
        InstallationInitializationResult(
            company=company,
            user=user,
            membership=membership,
            administrator_role=(
                administrator_role
            ),
        )
    )