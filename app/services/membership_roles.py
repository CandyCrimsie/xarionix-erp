from sqlalchemy.ext.asyncio import AsyncSession

from models.roles import Role

from repositories.company_memberships import (
    get_company_membership_by_id,
)

from repositories.membership_roles import (
    create_membership_roles,
    delete_membership_roles,
    get_membership_roles,
)

from repositories.roles import (
    get_roles_by_ids,
)

from services.authorization import (
    invalidate_membership_permissions,
)

from services.role_assignment_policy import (
    ensure_role_changes_are_delegated,
)


class CompanyMembershipNotFoundError(Exception):
    pass


class CompanyMembershipInactiveError(Exception):
    pass


class InvalidRolesError(Exception):
    def __init__(
        self,
        role_ids: list[int],
    ) -> None:
        self.role_ids = role_ids

        super().__init__(
            "Invalid role IDs"
        )


def _normalize_role_ids(
    role_ids: list[int],
) -> list[int]:
    return list(
        dict.fromkeys(
            role_ids
        )
    )


async def _validate_role_ids(
    session: AsyncSession,
    *,
    company_id: int,
    role_ids: list[int],
) -> list[int]:
    normalized_role_ids = (
        _normalize_role_ids(
            role_ids
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

    invalid_ids = [
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

    if invalid_ids:
        raise InvalidRolesError(
            invalid_ids
        )

    return normalized_role_ids


async def _persist_membership_roles(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    role_ids: list[int],
) -> list[Role]:
    try:
        await delete_membership_roles(
            session,
            company_membership_id,
        )

        await create_membership_roles(
            session,
            company_membership_id=(
                company_membership_id
            ),
            role_ids=role_ids,
        )

        await session.commit()

    except Exception:
        await session.rollback()
        raise

    await invalidate_membership_permissions(
        company_id=company_id,
        company_membership_id=(
            company_membership_id
        ),
    )

    return await get_membership_roles(
        session,
        company_membership_id,
    )


async def _get_company_membership(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
):
    membership = await get_company_membership_by_id(
        session,
        company_membership_id,
    )

    if (
        membership is None
        or membership.company_id != company_id
    ):
        raise CompanyMembershipNotFoundError

    return membership


async def list_membership_roles(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
) -> list[Role]:
    await _get_company_membership(
        session,
        company_id=company_id,
        company_membership_id=company_membership_id,
    )

    return await get_membership_roles(
        session,
        company_membership_id,
    )


async def replace_membership_roles(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    role_ids: list[int],
) -> list[Role]:
    membership = await _get_company_membership(
        session,
        company_id=company_id,
        company_membership_id=(
            company_membership_id
        ),
    )

    if not membership.is_active:
        raise CompanyMembershipInactiveError

    normalized_role_ids = (
        await _validate_role_ids(
            session,
            company_id=company_id,
            role_ids=role_ids,
        )
    )

    return await _persist_membership_roles(
        session,
        company_id=company_id,
        company_membership_id=(
            company_membership_id
        ),
        role_ids=normalized_role_ids,
    )


async def replace_membership_roles_with_delegation(
    session: AsyncSession,
    *,
    company_id: int,
    actor_membership_id: int,
    company_membership_id: int,
    role_ids: list[int],
) -> list[Role]:
    actor_membership = (
        await _get_company_membership(
            session,
            company_id=company_id,
            company_membership_id=(
                actor_membership_id
            ),
        )
    )

    if not actor_membership.is_active:
        raise CompanyMembershipInactiveError

    target_membership = (
        await _get_company_membership(
            session,
            company_id=company_id,
            company_membership_id=(
                company_membership_id
            ),
        )
    )

    if not target_membership.is_active:
        raise CompanyMembershipInactiveError

    normalized_role_ids = (
        await _validate_role_ids(
            session,
            company_id=company_id,
            role_ids=role_ids,
        )
    )

    current_roles = await get_membership_roles(
        session,
        company_membership_id,
    )

    current_role_ids = {
        role.id
        for role in current_roles
    }

    requested_role_ids = set(
        normalized_role_ids
    )

    #
    # Если фактически ничего не поменялось,
    # не делаем DELETE + INSERT и не трогаем
    # authorization cache.
    #
    if (
        current_role_ids
        == requested_role_ids
    ):
        return current_roles

    await ensure_role_changes_are_delegated(
        session,
        company_id=company_id,
        actor_membership_id=(
            actor_membership_id
        ),
        current_role_ids=(
            current_role_ids
        ),
        requested_role_ids=(
            requested_role_ids
        ),
    )

    return await _persist_membership_roles(
        session,
        company_id=company_id,
        company_membership_id=(
            company_membership_id
        ),
        role_ids=normalized_role_ids,
    )