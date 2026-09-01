from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from database.engine import initialize_database, close_database
from database.redis import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    print("Запуск инициализации...")
    await initialize_database()

    print("Проверка redis...")
    await redis_client.ping()

    yield

    print("Закрываю redis...")
    await redis_client.aclose()

    print("Закрываю Postgres...")
    await close_database()
    
    print("Приложение остановлено")