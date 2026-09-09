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
        await sync_authorization_baseline(
            session
        )

    print(
        "Очистка кэша прав..."
    )

    await clear_authorization_cache()

    try:
        yield

    finally:
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