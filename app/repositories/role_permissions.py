from sqlalchemy import (
    delete,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from models.permissions import Permission
from models.role_permissions import RolePermission

from core.permissions.scopes import (
    PermissionScope,
)


async def get_role_permissions(
    session: AsyncSession,
    role_id: int,
) -> list[
    tuple[
        Permission,
        PermissionScope,
    ]
]:
    stmt = (
        select(
            Permission,
            RolePermission.scope,
        )
        .join(
            RolePermission,
            RolePermission.permission_id
            == Permission.id,
        )
        .where(
            RolePermission.role_id
            == role_id
        )
        .order_by(
            Permission.module.asc(),
            Permission.code.asc(),
        )
    )

    result = await session.execute(stmt)

    return list(
        result.all()
    )


async def delete_role_permissions(
    session: AsyncSession,
    role_id: int,
) -> None:
    stmt = (
        delete(RolePermission)
        .where(
            RolePermission.role_id
            == role_id
        )
    )

    await session.execute(stmt)


async def create_role_permissions(
    session: AsyncSession,
    *,
    role_id: int,
    permissions: list[
        tuple[int, PermissionScope]
    ],
) -> None:
    if not permissions:
        return

    session.add_all(
        [
            RolePermission(
                role_id=role_id,
                permission_id=permission_id,
                scope=scope,
            )
            for permission_id, scope
            in permissions
        ]
    )

    await session.flush()