import asyncio
import os
import sys
from pathlib import Path

from httpx import (
    ASGITransport,
    AsyncClient,
)

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
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
# Это выполняется ДО imports из app. TEST_* variables позволяют запускать
# один и тот же набор тестов локально и с service-контейнерами GitLab CI.
# Значения по умолчанию соответствуют docker-compose.test.yml.
#

test_postgres_user = os.getenv(
    "TEST_POSTGRES_USER",
    "xarionix_test",
)
test_postgres_password = os.getenv(
    "TEST_POSTGRES_PASSWORD",
    "xarionix_test",
)
test_postgres_db = os.getenv(
    "TEST_POSTGRES_DB",
    "xarionix_test",
)
test_postgres_host = os.getenv(
    "TEST_POSTGRES_HOST",
    "127.0.0.1",
)
test_postgres_port = os.getenv(
    "TEST_POSTGRES_PORT",
    "55432",
)

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    (
        "postgresql+psycopg://"
        f"{test_postgres_user}:"
        f"{test_postgres_password}"
        f"@{test_postgres_host}:"
        f"{test_postgres_port}/"
        f"{test_postgres_db}"
    ),
)

test_redis_host = os.getenv(
    "TEST_REDIS_HOST",
    "127.0.0.1",
)
test_redis_port = os.getenv(
    "TEST_REDIS_PORT",
    "56379",
)
test_redis_password = os.getenv(
    "TEST_REDIS_PASSWORD",
    "xarionix_test",
)
test_redis_db = os.getenv(
    "TEST_REDIS_DB",
    "0",
)

os.environ["HOST"] = "127.0.0.1"
os.environ["PORT"] = "8000"

os.environ["POSTGRES_USER"] = test_postgres_user
os.environ["POSTGRES_PASSWORD"] = (
    test_postgres_password
)
os.environ["POSTGRES_DB"] = test_postgres_db
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

os.environ["REDIS_HOST"] = test_redis_host
os.environ["REDIS_PORT"] = test_redis_port
os.environ["REDIS_PASSWORD"] = (
    test_redis_password
)
os.environ["REDIS_DB"] = test_redis_db

os.environ["JWT_SECRET"] = (
    "0123456789abcdef0123456789abcdef"
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

os.environ[
    "SYSTEM_ADMIN_USERNAME"
] = "admin"
os.environ[
    "SYSTEM_ADMIN_PASSWORD"
] = "password123"
os.environ["MAP_TILES_ENABLED"] = "true"
os.environ["MAP_TILES_SIGNING_SECRET"] = (
    "test-map-signing-secret-0123456789abcdef"
)
os.environ["MAP_TILE_SESSION_TTL_SECONDS"] = "600"
os.environ["MAP_MAX_BUILDINGS_PER_VIEWPORT"] = "2000"


#
# Только теперь импортируем application code.
#

import models  # noqa: E402, F401

from database.base import Base  # noqa: E402

from database.redis import (
    redis_client,
)  # noqa: E402

from dependencies.database import (
    get_session,
)  # noqa: E402

from main import app  # noqa: E402


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
        await connection.execute(
            text("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        )
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


@pytest_asyncio.fixture
async def clean_test_redis():
    await redis_client.flushdb()

    yield

    await redis_client.flushdb()


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[
        get_session
    ] = override_get_session

    transport = ASGITransport(
        app=app,
    )

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.pop(
        get_session,
        None,
    )
