from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.codes import (
    get_permission_definition,
)
from core.permissions.effects import (
    PermissionOverrideEffect,
)
from core.permissions.scopes import (
    PermissionScope,
)

from models.membership_permission_overrides import (
    MembershipPermissionOverride,
)

from repositories.company_memberships import (
    get_company_membership_by_id,
)
from repositories.permissions import (
    get_permission_by_id,
)
from repositories.membership_permission_overrides import (
    create_membership_permission_override
    as create_override,
    delete_membership_permission_override
    as delete_override,
    get_membership_permission_override
    as get_override,
    get_membership_permission_overrides
    as get_overrides,
    update_membership_permission_override
    as update_override,
)

from services.authorization import (
    invalidate_membership_permissions,
)


class CompanyMembershipNotFoundError(
    Exception
):
    pass


class CompanyMembershipInactiveError(
    Exception
):
    pass


class PermissionNotFoundError(
    Exception
):
    pass


class PermissionInactiveError(
    Exception
):
    pass


class InvalidPermissionOverrideError(
    Exception
):
    pass


class InvalidPermissionScopeError(
    Exception
):
    def __init__(
        self,
        *,
        permission_id: int,
        code: str,
        scope: PermissionScope,
        allowed_scopes: list[
            PermissionScope
        ],
    ) -> None:
        self.permission_id = permission_id
        self.code = code
        self.scope = scope
        self.allowed_scopes = (
            allowed_scopes
        )

        super().__init__(
            "Invalid permission scope"
        )


class PermissionOverrideNotFoundError(
    Exception
):
    pass


async def _get_company_membership(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    require_active: bool,
):
    membership = (
        await get_company_membership_by_id(
            session,
            company_membership_id,
        )
    )

    if (
        membership is None
        or membership.company_id
        != company_id
    ):
        raise CompanyMembershipNotFoundError

    if (
        require_active
        and not membership.is_active
    ):
        raise CompanyMembershipInactiveError

    return membership


async def _get_active_permission(
    session: AsyncSession,
    *,
    permission_id: int,
):
    permission = await get_permission_by_id(
        session,
        permission_id,
    )

    if permission is None:
        raise PermissionNotFoundError

    if not permission.is_active:
        raise PermissionInactiveError

    return permission


def _validate_override(
    *,
    permission,
    effect: PermissionOverrideEffect,
    scope: PermissionScope | None,
) -> None:
    if (
        effect
        == PermissionOverrideEffect.DENY
    ):
        if scope is not None:
            raise InvalidPermissionOverrideError(
                "DENY override must not have scope"
            )

        return

    if (
        effect
        != PermissionOverrideEffect.ALLOW
    ):
        raise InvalidPermissionOverrideError(
            "Unsupported override effect"
        )

    if scope is None:
        raise InvalidPermissionOverrideError(
            "ALLOW override requires scope"
        )

    definition = get_permission_definition(
        permission.code
    )

    if (
        definition is None
        or scope
        not in definition.allowed_scopes
    ):
        raise InvalidPermissionScopeError(
            permission_id=permission.id,
            code=permission.code,
            scope=scope,
            allowed_scopes=(
                list(
                    definition.allowed_scopes
                )
                if definition is not None
                else []
            ),
        )


async def list_membership_permission_overrides(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
) -> list[MembershipPermissionOverride]:
    await _get_company_membership(
        session,
        company_id=company_id,
        company_membership_id=(
            company_membership_id
        ),
        require_active=False,
    )

    return await get_overrides(
        session,
        company_membership_id=(
            company_membership_id
        ),
    )


async def set_membership_permission_override(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    permission_id: int,
    effect: PermissionOverrideEffect,
    scope: PermissionScope | None,
) -> MembershipPermissionOverride:
    await _get_company_membership(
        session,
        company_id=company_id,
        company_membership_id=(
            company_membership_id
        ),
        require_active=True,
    )

    permission = await _get_active_permission(
        session,
        permission_id=permission_id,
    )

    _validate_override(
        permission=permission,
        effect=effect,
        scope=scope,
    )

    existing = await get_override(
        session,
        company_membership_id=(
            company_membership_id
        ),
        permission_id=permission_id,
    )

    #
    # Exact no-op.
    #
    if (
        existing is not None
        and existing.effect == effect
        and existing.scope == scope
    ):
        return existing

    try:
        if existing is None:
            permission_override = (
                await create_override(
                    session,
                    company_membership_id=(
                        company_membership_id
                    ),
                    permission_id=(
                        permission_id
                    ),
                    effect=effect,
                    scope=scope,
                )
            )

        else:
            permission_override = (
                await update_override(
                    session,
                    permission_override=(
                        existing
                    ),
                    effect=effect,
                    scope=scope,
                )
            )

        await session.commit()

        await session.refresh(
            permission_override
        )

    except Exception:
        await session.rollback()
        raise

    await invalidate_membership_permissions(
        company_id=company_id,
        company_membership_id=(
            company_membership_id
        ),
    )

    return permission_override


async def delete_membership_permission_override(
    session: AsyncSession,
    *,
    company_id: int,
    company_membership_id: int,
    permission_id: int,
) -> None:
    await _get_company_membership(
        session,
        company_id=company_id,
        company_membership_id=(
            company_membership_id
        ),
        require_active=True,
    )

    existing = await get_override(
        session,
        company_membership_id=(
            company_membership_id
        ),
        permission_id=permission_id,
    )

    if existing is None:
        raise PermissionOverrideNotFoundError

    try:
        await delete_override(
            session,
            company_membership_id=(
                company_membership_id
            ),
            permission_id=permission_id,
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