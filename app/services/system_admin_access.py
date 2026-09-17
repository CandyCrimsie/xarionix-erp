from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.system_roles import (
    SystemRoleKey,
)

from repositories.company import (
    get_companies,
)

from repositories.company_memberships import (
    create_company_membership,
    get_company_membership_by_user,
)

from repositories.membership_roles import (
    create_membership_roles,
    get_membership_roles,
)

from repositories.roles import (
    get_system_role_by_key,
)

from repositories.users import (
    get_system_administrators,
)


class SystemAdministratorRoleUnavailableError(
    Exception
):
    pass


async def ensure_system_administrators_access_for_company_in_transaction(
    session: AsyncSession,
    *,
    company_id: int,
) -> None:
    administrator_role = (
        await get_system_role_by_key(
            session,
            company_id=company_id,
            system_key=(
                SystemRoleKey
                .ADMINISTRATOR
                .value
            ),
        )
    )


    if administrator_role is None:
        raise (
            SystemAdministratorRoleUnavailableError
        )


    system_administrators = (
        await get_system_administrators(
            session
        )
    )


    for user in system_administrators:
        membership = (
            await get_company_membership_by_user(
                session,
                company_id=company_id,
                user_id=user.id,
            )
        )


        if membership is None:
            membership = (
                await create_company_membership(
                    session,
                    user_id=user.id,
                    company_id=company_id,
                )
            )

        elif not membership.is_active:
            membership.is_active = True

            await session.flush()


        roles = await get_membership_roles(
            session,
            membership.id,
        )


        role_ids = {
            role.id
            for role in roles
        }


        if (
            administrator_role.id
            not in role_ids
        ):
            await create_membership_roles(
                session,
                company_membership_id=(
                    membership.id
                ),
                role_ids=[
                    administrator_role.id,
                ],
            )


async def sync_system_administrator_company_access(
    session: AsyncSession,
) -> None:
    companies = await get_companies(
        session
    )


    try:
        for company in companies:
            await (
                ensure_system_administrators_access_for_company_in_transaction(
                    session,
                    company_id=(
                        company.id
                    ),
                )
            )


        await session.commit()

    except Exception:
        await session.rollback()
        raise