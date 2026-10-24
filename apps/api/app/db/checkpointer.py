from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


async def setup_checkpointer(database_url: str) -> None:
    """Create/upgrade LangGraph checkpointer tables (library-owned DDL, idempotent).

    Never mirror these tables in Alembic.
    """
    async with AsyncPostgresSaver.from_conn_string(database_url) as saver:
        await saver.setup()
