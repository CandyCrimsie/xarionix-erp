from sqlalchemy.ext.asyncio import AsyncSession

from models.permissions import Permission

from repositories.permissions import (
    get_permissions_by_ids,
)

from repositories.role_permissions import (
    create_role_permissions,
    delete_role_permissions,
    get_role_permissions,
)

from repositories.roles import (
    get_role_by_id,
)

from services.authorization import (
    invalidate_role_permissions,
)

from schemas.role_permissions import (
    RolePermissionAssignment
)


class RoleNotFoundError(Exception):
    pass


class InvalidPermissionsError(Exception):
    def __init__(
        self,
        permission_ids: list[int],
    ) -> None:
        self.permission_ids = permission_ids

        super().__init__(
            "Invalid permission IDs"
        )


async def _get_company_role(
    session: AsyncSession,
    *,
    company_id: int,
    role_id: int,
):
    role = await get_role_by_id(
        session,
        role_id,
    )

    if (
        role is None
        or role.company_id != company_id
    ):
        raise RoleNotFoundError

    return role


async def list_role_permissions(
    session: AsyncSession,
    *,
    company_id: int,
    role_id: int,
) -> list[Permission]:
    await _get_company_role(
        session,
        company_id=company_id,
        role_id=role_id,
    )

    return await get_role_permissions(
        session,
        role_id,
    )


async def replace_role_permissions(
    session: AsyncSession,
    *,
    company_id: int,
    role_id: int,
    permissions: list[
        RolePermissionAssignment
    ],
):
    role = await _get_company_role(
        session,
        company_id=company_id,
        role_id=role_id,
    )

    permission_ids = [
        item.permission_id
        for item in permissions
    ]

    existing_permissions = (
        await get_permissions_by_ids(
            session,
            permission_ids,
        )
    )

    permissions_by_id = {
        permission.id: permission
        for permission
        in existing_permissions
    }

    invalid_ids = [
        permission_id
        for permission_id
        in permission_ids
        if (
            permission_id
            not in permissions_by_id
            or not permissions_by_id[
                permission_id
            ].is_active
        )
    ]

    if invalid_ids:
        raise InvalidPermissionsError(
            invalid_ids
        )

    role_permissions = [
        (
            item.permission_id,
            item.scope,
        )
        for item in permissions
    ]

    try:
        await delete_role_permissions(
            session,
            role.id,
        )

        await create_role_permissions(
            session,
            role_id=role.id,
            permissions=role_permissions,
        )

        await session.commit()

    except Exception:
        await session.rollback()
        raise

    await invalidate_role_permissions(
        session,
        role_id=role.id,
    )

    return await get_role_permissions(
        session,
        role.id,
    )