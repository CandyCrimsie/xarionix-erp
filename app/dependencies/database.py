from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from database.session import session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise