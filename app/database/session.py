from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.engine import engine


session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)