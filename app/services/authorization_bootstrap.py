from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from models.roles import Role

from services.permissions import (
    sync_permissions,
)
from services.system_roles import (
    sync_system_roles,
)


async def sync_authorization_baseline(
    session: AsyncSession,
) -> dict[int, list[Role]]:
    #
    # System roles зависят от глобального
    # permission catalog.
    #
    await sync_permissions(
        session
    )

    return await sync_system_roles(
        session
    )