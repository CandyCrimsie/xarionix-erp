from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from database.engine import initialize_database, close_database
from database.redis import redis_client
from database.session import session_factory

from services.permissions import sync_permissions
from services.authorization import clear_authorization_cache


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    print("Запуск инициализации...")

    await initialize_database()

    print("Добавление прав...")

    async with session_factory() as session:
        await sync_permissions(session)

    print("Очистка кэша прав...")

    await clear_authorization_cache()

    print("Проверка Redis...")

    await redis_client.ping()

    try:
        yield

    finally:
        print("Закрываю Redis...")
        await redis_client.aclose()

        print("Закрываю Postgres...")
        await close_database()

        print(
            "Приложение остановлено"
        )