from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.db.config import get_database_url


async def setup_checkpointer(database_url: str) -> None:
    """Create/upgrade LangGraph checkpointer tables (library-owned DDL, idempotent).

    Never mirror these tables in Alembic.
    """
    async with AsyncPostgresSaver.from_conn_string(database_url) as saver:
        await saver.setup()


@asynccontextmanager
async def open_checkpointer(
    database_url: str | None = None,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Runtime saver context for Router-only writes.

    Never call ``aput`` from WS/routes — only the Router module may write.
    """
    url = database_url if database_url is not None else get_database_url()
    async with AsyncPostgresSaver.from_conn_string(url) as saver:
        yield saver
