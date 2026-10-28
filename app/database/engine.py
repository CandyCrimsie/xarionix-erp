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


async def _extend_development_schema(connection) -> None:
    """Apply additive compatibility changes until formal migrations are enabled."""
    await connection.execute(
        text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_type
                    WHERE typname = 'address_type_category'
                ) AND NOT EXISTS (
                    SELECT 1
                    FROM pg_type AS type
                    JOIN pg_enum AS value ON value.enumtypid = type.oid
                    WHERE type.typname = 'address_type_category'
                      AND value.enumlabel = 'territory'
                ) THEN
                    ALTER TYPE address_type_category ADD VALUE 'territory';
                END IF;
            END
            $$;
            """
        )
    )


async def initialize_database() -> None:
    import models

    async with engine.begin() as connection:
        await connection.execute(text("SELECT 1"))
        await connection.execute(
            text("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        )
        await _extend_development_schema(connection)
        from database.map_upgrade import upgrade_map_schema
        report = await upgrade_map_schema(connection)
        if report["upgrade_required"]:
            print("Map schema upgrade:", report)
        await connection.run_sync(Base.metadata.create_all)


async def close_database() -> None:
    await engine.dispose()
