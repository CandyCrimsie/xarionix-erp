import json

from sqlalchemy.ext.asyncio import AsyncSession

from core.authorization.cache import (
    AUTHORIZATION_CACHE_PREFIX,
    AUTHORIZATION_CACHE_TTL_SECONDS,
)
from core.permissions.codes import PermissionCode

from database.redis import redis_client

from repositories.authorization import (
    get_effective_permission_codes,
    get_membership_ids_by_role
)

from repositories.roles import (
    get_role_by_id,
)


class AuthorizationService:
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    @staticmethod
    def _get_cache_key(
        *,
        company_id: int,
        company_membership_id: int,
    ) -> str:
        return (
            f"{AUTHORIZATION_CACHE_PREFIX}:"
            f"{company_id}:"
            f"{company_membership_id}"
        )

    async def get_effective_permissions(
        self,
        *,
        company_id: int,
        company_membership_id: int,
    ) -> set[str]:
        cache_key = self._get_cache_key(
            company_id=company_id,
            company_membership_id=(
                company_membership_id
            ),
        )

        cached = await redis_client.get(
            cache_key
        )

        if cached is not None:
            return set(
                json.loads(cached)
            )

        permissions = (
            await get_effective_permission_codes(
                self.session,
                company_id=company_id,
                company_membership_id=(
                    company_membership_id
                ),
            )
        )

        await redis_client.set(
            cache_key,
            json.dumps(
                sorted(permissions)
            ),
            ex=AUTHORIZATION_CACHE_TTL_SECONDS,
        )

        return permissions

    async def has_permission(
        self,
        *,
        company_id: int,
        company_membership_id: int,
        permission: PermissionCode | str,
    ) -> bool:
        permission_code = (
            permission.value
            if isinstance(
                permission,
                PermissionCode,
            )
            else permission
        )

        permissions = (
            await self.get_effective_permissions(
                company_id=company_id,
                company_membership_id=(
                    company_membership_id
                ),
            )
        )

        return (
            permission_code
            in permissions
        )


async def invalidate_membership_permissions(
    *,
    company_id: int,
    company_membership_id: int,
) -> None:
    cache_key = (
        f"{AUTHORIZATION_CACHE_PREFIX}:"
        f"{company_id}:"
        f"{company_membership_id}"
    )

    await redis_client.delete(
        cache_key
    )


async def invalidate_role_permissions(
    session: AsyncSession,
    *,
    role_id: int,
) -> None:
    role = await get_role_by_id(
        session,
        role_id,
    )

    if role is None:
        return

    membership_ids = (
        await get_membership_ids_by_role(
            session,
            role_id,
        )
    )

    if not membership_ids:
        return

    keys = [
        (
            f"{AUTHORIZATION_CACHE_PREFIX}:"
            f"{role.company_id}:"
            f"{membership_id}"
        )
        for membership_id
        in membership_ids
    ]

    await redis_client.delete(
        *keys
    )


async def clear_authorization_cache() -> None:
    pattern = (
        f"{AUTHORIZATION_CACHE_PREFIX}:*"
    )

    async for key in redis_client.scan_iter(
        match=pattern,
    ):
        await redis_client.delete(
            key
        )