from sqlalchemy.ext.asyncio import AsyncSession

from repositories.permissions import (
    create_permission,
    get_all_permissions,
    get_permissions,
)

from core.permissions.codes import (
    PERMISSION_DEFINITIONS,
    get_permission_definition,
)

from schemas.permissions import (
    PermissionResponse,
)


async def list_permissions(
    session: AsyncSession,
) -> list[PermissionResponse]:
    permissions = await get_permissions(
        session,
        active_only=True,
    )

    result: list[
        PermissionResponse
    ] = []

    for permission in permissions:
        definition = (
            get_permission_definition(
                permission.code
            )
        )

        if definition is None:
            continue

        result.append(
            PermissionResponse(
                id=permission.id,
                code=permission.code,
                name=permission.name,
                module=permission.module,
                description=(
                    permission.description
                ),
                is_active=permission.is_active,
                allowed_scopes=list(
                    definition.allowed_scopes
                ),
            )
        )

    return result


async def sync_permissions(
    session: AsyncSession,
) -> None:
    existing_permissions = (
        await get_all_permissions(session)
    )

    permissions_by_code = {
        permission.code: permission
        for permission in existing_permissions
    }

    active_codes: set[str] = set()

    for definition in PERMISSION_DEFINITIONS:
        code = definition.code.value

        active_codes.add(code)

        existing = permissions_by_code.get(
            code
        )

        if existing is None:
            await create_permission(
                session,
                code=code,
                name=definition.name,
                module=definition.module,
                description=definition.description,
            )

            continue

        existing.name = definition.name
        existing.module = definition.module
        existing.description = (
            definition.description
        )
        existing.is_active = True

    for permission in existing_permissions:
        if permission.code not in active_codes:
            permission.is_active = False

    await session.commit()