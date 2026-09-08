import os
import sys
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


ROOT_DIR = Path(
    __file__
).resolve().parents[1]

APP_DIR = ROOT_DIR / "app"

sys.path.insert(
    0,
    str(APP_DIR),
)


#
# Test application configuration.
#
# Это выполняется ДО imports из app.
#

os.environ["HOST"] = "127.0.0.1"
os.environ["PORT"] = "8000"

os.environ["POSTGRES_USER"] = (
    "xarionix_test"
)
os.environ["POSTGRES_PASSWORD"] = (
    "xarionix_test"
)
os.environ["POSTGRES_DB"] = (
    "xarionix_test"
)

os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://"
    "xarionix_test:"
    "xarionix_test"
    "@127.0.0.1:55432/"
    "xarionix_test"
)

os.environ["REDIS_HOST"] = "127.0.0.1"
os.environ["REDIS_PORT"] = "56379"
os.environ["REDIS_PASSWORD"] = (
    "xarionix_test"
)
os.environ["REDIS_DB"] = "0"

os.environ["JWT_SECRET"] = (
    "test-secret-key"
)
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ[
    "JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
] = "15"

os.environ[
    "REFRESH_TOKEN_EXPIRE_DAYS"
] = "30"
os.environ["REFRESH_COOKIE_NAME"] = (
    "refresh_token"
)
os.environ["COOKIE_SECURE"] = "false"


#
# Только теперь импортируем application code.
#

import models  # noqa: E402, F401

from database.base import Base  # noqa: E402

from database.redis import (
    redis_client,
)  # noqa: E402


TEST_DATABASE_URL = os.environ[
    "DATABASE_URL"
]


@pytest_asyncio.fixture(
    scope="session",
    autouse=True,
)
async def redis_lifecycle():
    yield

    await redis_client.aclose()


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    #
    # Каждый тест получает совершенно
    # чистую схему.
    #
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.drop_all
        )

        await connection.run_sync(
            Base.metadata.create_all
        )

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session

        await session.rollback()

    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.drop_all
        )

    await engine.dispose()