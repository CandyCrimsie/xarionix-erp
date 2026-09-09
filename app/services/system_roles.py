from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.system_roles import (
    SYSTEM_ROLE_TEMPLATES,
    SystemRoleTemplate,
)

from models.permissions import Permission

from repositories.permissions import (
    get_permissions,
)
from repositories.role_permissions import (
    create_role_permissions,
    delete_role_permissions,
    get_role_permissions,
)

from services.authorization import (
    invalidate_role_permissions,
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

from repositories.role_delegations import (
    get_role_delegations,
    replace_role_delegations,
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


class SystemRolePermissionUnavailableError(
    Exception
):
    def __init__(
        self,
        permission_codes: list[str],
    ) -> None:
        self.permission_codes = (
            permission_codes
        )

        super().__init__(
            (
                "System role permissions "
                "are unavailable"
            )
        )


async def _get_active_permissions_by_code(
    session: AsyncSession,
) -> dict[str, Permission]:
    permissions = await get_permissions(
        session,
        active_only=True,
    )

    permissions_by_code = {
        permission.code: permission
        for permission in permissions
    }

    required_codes = {
        item.code.value
        for template
        in SYSTEM_ROLE_TEMPLATES
        for item
        in template.permissions
    }

    missing_codes = sorted(
        required_codes
        - set(permissions_by_code)
    )

    if missing_codes:
        raise (
            SystemRolePermissionUnavailableError(
                missing_codes
            )
        )

    return permissions_by_code


async def _sync_role_permissions(
    session: AsyncSession,
    *,
    role: Role,
    template: SystemRoleTemplate,
    permissions_by_code: dict[
        str,
        Permission,
    ],
) -> bool:
    current_rows = (
        await get_role_permissions(
            session,
            role.id,
        )
    )

    current_permissions = {
        permission.code: scope
        for permission, scope
        in current_rows
    }

    desired_permissions = {
        item.code.value: item.scope
        for item
        in template.permissions
    }

    #
    # Ничего не изменилось:
    # не трогаем строки и не инвалидируем cache.
    #
    if (
        current_permissions
        == desired_permissions
    ):
        return False

    #
    # Template является полным source of truth.
    #
    await delete_role_permissions(
        session,
        role.id,
    )

    await create_role_permissions(
        session,
        role_id=role.id,
        permissions=[
            (
                permissions_by_code[
                    code
                ].id,
                scope,
            )
            for code, scope
            in desired_permissions.items()
        ],
    )

    return True


async def _sync_role_delegations(
    session: AsyncSession,
    *,
    role: Role,
    template: SystemRoleTemplate,
    roles_by_key: dict[
        str,
        Role,
    ],
) -> bool:
    current_rows = (
        await get_role_delegations(
            session,
            manager_role_id=role.id,
        )
    )

    current_role_ids = {
        delegation.assignable_role_id
        for delegation
        in current_rows
    }

    desired_role_ids = {
        roles_by_key[
            key.value
        ].id
        for key
        in template.assignable_role_keys
    }

    if (
        current_role_ids
        == desired_role_ids
    ):
        return False

    await replace_role_delegations(
        session,
        manager_role_id=role.id,
        assignable_role_ids=sorted(
            desired_role_ids
        ),
    )

    return True


async def _sync_system_roles_for_company(
    session: AsyncSession,
    *,
    company_id: int,
) -> tuple[
    list[Role],
    set[int],
]:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise SystemRoleCompanyNotFoundError

    permissions_by_code = (
        await _get_active_permissions_by_code(
            session
        )
    )

    synchronized_roles: list[
        Role
    ] = []

    authorization_changed_role_ids: set[
        int
    ] = set()

    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        role = await get_system_role_by_key(
            session,
            company_id=company_id,
            system_key=template.key.value,
        )

        role_with_template_name = (
            await get_role_by_name(
                session,
                company_id=company_id,
                name=template.name,
            )
        )

        role_authorization_changed = False

        if role is None:
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
            # Reactivation влияет на authorization.
            #
            if not role.is_active:
                role_authorization_changed = (
                    True
                )

            role.name = template.name
            role.description = (
                template.description
            )
            role.is_active = True

        permissions_changed = (
            await _sync_role_permissions(
                session,
                role=role,
                template=template,
                permissions_by_code=(
                    permissions_by_code
                ),
            )
        )

        if (
            role_authorization_changed
            or permissions_changed
        ):
            authorization_changed_role_ids.add(
                role.id
            )

        synchronized_roles.append(
            role
        )

    roles_by_key = {
        role.system_key: role
        for role in synchronized_roles
    }

    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        role = roles_by_key[
            template.key.value
        ]

        await _sync_role_delegations(
            session,
            role=role,
            template=template,
            roles_by_key=roles_by_key,
        )    

    await session.flush()

    return (
        synchronized_roles,
        authorization_changed_role_ids,
    )


async def sync_system_roles_for_company_in_transaction(
    session: AsyncSession,
    *,
    company_id: int,
) -> tuple[
    list[Role],
    set[int],
]:
    return (
        await sync_system_roles_for_company_in_transaction(
            session,
            company_id=company_id,
        )
    )


async def sync_system_roles_for_company(
    session: AsyncSession,
    *,
    company_id: int,
) -> list[Role]:
    try:
        (
            roles,
            changed_role_ids,
        ) = (
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

    except Exception:
        await session.rollback()
        raise

    #
    # Только после успешного COMMIT.
    #
    for role_id in changed_role_ids:
        await invalidate_role_permissions(
            session,
            role_id=role_id,
        )

    return roles


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

    changed_role_ids: set[int] = set()

    try:
        for company in companies:
            company_id = company.id

            (
                roles,
                company_changed_role_ids,
            ) = (
                await sync_system_roles_for_company_in_transaction(
                    session,
                    company_id=company_id,
                )
            )

            synchronized[
                company_id
            ] = roles

            changed_role_ids.update(
                company_changed_role_ids
            )

        await session.commit()

        for roles in synchronized.values():
            for role in roles:
                await session.refresh(
                    role
                )

    except Exception:
        await session.rollback()
        raise

    for role_id in changed_role_ids:
        await invalidate_role_permissions(
            session,
            role_id=role_id,
        )

    return synchronized