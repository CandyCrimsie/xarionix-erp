from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.system_roles import (
    SYSTEM_ROLE_TEMPLATES,
)

from models.roles import Role

from repositories.company import (
    get_companies,
    get_company_by_id,
)
from repositories.roles import (
    create_role,
    get_role_by_name,
    get_system_role_by_key,
)


class SystemRoleCompanyNotFoundError(
    Exception
):
    pass


class SystemRoleNameConflictError(
    Exception
):
    def __init__(
        self,
        *,
        company_id: int,
        role_name: str,
        existing_role_id: int,
    ) -> None:
        self.company_id = company_id
        self.role_name = role_name
        self.existing_role_id = (
            existing_role_id
        )

        super().__init__(
            (
                "System role name conflicts "
                "with an existing role"
            )
        )


async def _sync_system_roles_for_company(
    session: AsyncSession,
    *,
    company_id: int,
) -> list[Role]:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise SystemRoleCompanyNotFoundError

    synchronized_roles: list[
        Role
    ] = []

    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        role = await get_system_role_by_key(
            session,
            company_id=company_id,
            system_key=template.key.value,
        )

        #
        # Проверяем, не занято ли canonical
        # имя другой ролью.
        #
        role_with_template_name = (
            await get_role_by_name(
                session,
                company_id=company_id,
                name=template.name,
            )
        )

        if role is None:
            #
            # Обычную пользовательскую роль
            # с таким же именем автоматически
            # системной НЕ делаем.
            #
            if (
                role_with_template_name
                is not None
            ):
                raise (
                    SystemRoleNameConflictError(
                        company_id=company_id,
                        role_name=template.name,
                        existing_role_id=(
                            role_with_template_name.id
                        ),
                    )
                )

            role = await create_role(
                session,
                company_id=company_id,
                name=template.name,
                description=(
                    template.description
                ),
                is_system=True,
                system_key=(
                    template.key.value
                ),
            )

        else:
            #
            # Системная роль уже существует,
            # но canonical name может быть
            # занят другой ролью.
            #
            if (
                role_with_template_name
                is not None
                and (
                    role_with_template_name.id
                    != role.id
                )
            ):
                raise (
                    SystemRoleNameConflictError(
                        company_id=company_id,
                        role_name=template.name,
                        existing_role_id=(
                            role_with_template_name.id
                        ),
                    )
                )

            #
            # Template является source of truth
            # для metadata системной роли.
            #
            role.name = template.name
            role.description = (
                template.description
            )
            role.is_active = True

        synchronized_roles.append(
            role
        )

    await session.flush()

    return synchronized_roles


async def sync_system_roles_for_company(
    session: AsyncSession,
    *,
    company_id: int,
) -> list[Role]:
    try:
        roles = (
            await _sync_system_roles_for_company(
                session,
                company_id=company_id,
            )
        )

        await session.commit()

        for role in roles:
            await session.refresh(
                role
            )

        return roles

    except Exception:
        await session.rollback()
        raise


async def sync_system_roles(
    session: AsyncSession,
) -> dict[int, list[Role]]:
    companies = await get_companies(
        session
    )

    synchronized: dict[
        int,
        list[Role],
    ] = {}

    try:
        for company in companies:
            synchronized[
                company.id
            ] = (
                await _sync_system_roles_for_company(
                    session,
                    company_id=company.id,
                )
            )

        #
        # Все компании синхронизируются
        # одной транзакцией.
        #
        await session.commit()

        return synchronized

    except Exception:
        await session.rollback()
        raise