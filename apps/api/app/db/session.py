"""Request-scoped async SQLAlchemy session (via get_database_url())."""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.config import get_database_url, to_sqlalchemy_url

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(to_sqlalchemy_url(get_database_url()))
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def _factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI Depends — one AsyncSession per request."""
    async with _factory()() as session:
        yield session


async def probe_database() -> None:
    """Cheap connectivity check for readiness (raises if Postgres is unreachable)."""
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))


async def dispose_engine() -> None:
    """Drop the cached engine (lifespan shutdown / test isolation)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
