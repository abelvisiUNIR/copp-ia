"""Acceso async a PostgreSQL (SQLAlchemy 2 + asyncpg)."""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from teleflow.common.config import Settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_db(settings: Settings) -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    assert _sessionmaker is not None
    return _sessionmaker


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("init_db() no fue llamado")
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI."""
    maker = get_sessionmaker()
    async with maker() as session:
        yield session


async def dispose_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


async def db_ping() -> bool:
    from sqlalchemy import text

    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(text("SELECT 1"))
    return True
