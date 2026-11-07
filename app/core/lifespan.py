from collections.abc import (
    AsyncGenerator,
)
from contextlib import (
    asynccontextmanager,
)

from fastapi import FastAPI

from database.engine import (
    close_database,
    initialize_database,
)
from database.redis import (
    redis_client,
)
from database.session import (
    session_factory,
)

from services.authorization import (
    clear_authorization_cache,
)
from services.authorization_bootstrap import (
    sync_authorization_baseline,
)
from services.system_admin_access import (
    sync_system_administrator_company_access,
)
from services.address_types import (
    sync_system_address_types,
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncGenerator[None, None]:
    print(
        "Запуск инициализации..."
    )

    await initialize_database()

    #
    # System-role synchronization может
    # инвалидировать authorization cache,
    # поэтому Redis проверяем заранее.
    #
    print(
        "Проверка Redis..."
    )

    await redis_client.ping()

    print(
        "Синхронизация RBAC..."
    )

    async with session_factory() as session:
        await sync_system_address_types(
            session
        )

        await sync_authorization_baseline(
            session
        )

        await (
            sync_system_administrator_company_access(
                session
            )
        )

    print(
        "Очистка кэша прав..."
    )

    await clear_authorization_cache()

    # Separate, TLS-verifying client. No cookies, redirects, env proxy or secret logs.
    import httpx
    from core.config import config
    from services.platform_identity import PlatformProvider
    platform_client = httpx.AsyncClient(
        timeout=5, trust_env=False, follow_redirects=False,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    ) if config.PLATFORM_OIDC_ENABLED else None
    app.state.platform_provider = PlatformProvider(platform_client) if platform_client else None
    try:
        yield

    finally:
        if platform_client is not None:
            await platform_client.aclose()
        print(
            "Закрываю Redis..."
        )

        await redis_client.aclose()

        print(
            "Закрываю Postgres..."
        )

        await close_database()

        print(
            "Приложение остановлено"
        )
