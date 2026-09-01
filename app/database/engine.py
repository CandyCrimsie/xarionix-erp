from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import config
from database.base import Base


engine = create_async_engine(
    url=config.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)


async def initialize_database() -> None:
    import models

    async with engine.begin() as connection:
        await connection.execute(text("SELECT 1"))
        await connection.run_sync(Base.metadata.create_all)


async def close_database() -> None:
    await engine.dispose()