from sqlalchemy.ext.asyncio import AsyncSession

from repositories.membership_roles import (
    get_membership_roles,
)

from repositories.role_delegations import (
    get_assignable_role_ids,
)


class RoleAssignmentNotAllowedError(
    Exception
):
    def __init__(
        self,
        role_ids: list[int],
    ) -> None:
        self.role_ids = role_ids

        super().__init__(
            "Role assignment is not allowed"
        )


async def get_membership_assignable_role_ids(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
) -> set[int]:
    roles = await get_membership_roles(
        session,
        company_membership_id,
    )

    manager_role_ids = [
        role.id
        for role in roles
        if (
            role.company_id == company_id
            and role.is_active
        )
    ]

    return await get_assignable_role_ids(
        session,
        manager_role_ids=manager_role_ids,
    )


def get_changed_role_ids(
    *,
    current_role_ids: set[int],
    requested_role_ids: set[int],
) -> set[int]:
    return (
        current_role_ids
        ^ requested_role_ids
    )


async def ensure_role_changes_are_delegated(
    session: AsyncSession,
    *,
    company_id: int,
    actor_membership_id: int,
    current_role_ids: set[int],
    requested_role_ids: set[int],
) -> None:
    changed_role_ids = get_changed_role_ids(
        current_role_ids=current_role_ids,
        requested_role_ids=requested_role_ids,
    )

    if not changed_role_ids:
        return

    assignable_role_ids = (
        await get_membership_assignable_role_ids(
            session,
            company_id=company_id,
            company_membership_id=(
                actor_membership_id
            ),
        )
    )

    forbidden_role_ids = sorted(
        changed_role_ids
        - assignable_role_ids
    )

    if forbidden_role_ids:
        raise RoleAssignmentNotAllowedError(
            forbidden_role_ids
        )