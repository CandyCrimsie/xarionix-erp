from sqlalchemy.ext.asyncio import AsyncSession

from models.role_delegations import (
    RoleDelegation,
)

from repositories.role_delegations import (
    get_role_delegations,
    replace_role_delegations,
)

from repositories.roles import (
    get_role_by_id,
    get_roles_by_ids,
)


class RoleNotFoundError(Exception):
    pass


class RoleInactiveError(Exception):
    pass


class InvalidAssignableRolesError(Exception):
    def __init__(
        self,
        role_ids: list[int],
    ) -> None:
        self.role_ids = role_ids

        super().__init__(
            "Invalid assignable role IDs"
        )


async def list_role_delegations(
    session: AsyncSession,
    *,
    company_id: int,
    manager_role_id: int,
) -> list[RoleDelegation]:
    manager_role = await get_role_by_id(
        session,
        manager_role_id,
    )

    if (
        manager_role is None
        or manager_role.company_id != company_id
    ):
        raise RoleNotFoundError

    return await get_role_delegations(
        session,
        manager_role_id=manager_role_id,
    )


async def replace_role_delegations_for_role(
    session: AsyncSession,
    *,
    company_id: int,
    manager_role_id: int,
    assignable_role_ids: list[int],
) -> list[RoleDelegation]:
    manager_role = await get_role_by_id(
        session,
        manager_role_id,
    )

    if (
        manager_role is None
        or manager_role.company_id != company_id
    ):
        raise RoleNotFoundError

    if not manager_role.is_active:
        raise RoleInactiveError

    #
    # Убираем дубликаты, сохраняя порядок.
    #
    normalized_role_ids = list(
        dict.fromkeys(
            assignable_role_ids
        )
    )

    roles = await get_roles_by_ids(
        session,
        normalized_role_ids,
    )

    roles_by_id = {
        role.id: role
        for role in roles
    }

    invalid_role_ids = [
        role_id
        for role_id in normalized_role_ids
        if (
            role_id not in roles_by_id
            or (
                roles_by_id[role_id].company_id
                != company_id
            )
            or not roles_by_id[role_id].is_active
        )
    ]

    if invalid_role_ids:
        raise InvalidAssignableRolesError(
            invalid_role_ids
        )

    try:
        await replace_role_delegations(
            session,
            manager_role_id=manager_role_id,
            assignable_role_ids=(
                normalized_role_ids
            ),
        )

        await session.commit()

    except Exception:
        await session.rollback()
        raise

    return await get_role_delegations(
        session,
        manager_role_id=manager_role_id,
    )