"""Startup bootstrap: advisory lock -> Alembic upgrade -> checkpointer setup -> release.

Single critical section. Postgres session-level advisory locks are released
when the holding connection ends, so a crashed holder never leaves a stale lock.
"""

import asyncio
import logging
import time
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config

from app.db.checkpointer import setup_checkpointer
from app.db.config import get_database_url

logger = logging.getLogger(__name__)

# Fixed 64-bit key identifying the api bootstrap critical section.
BOOTSTRAP_LOCK_KEY = 7_265_300_117_001
LOCK_TIMEOUT_SECONDS = 60.0
LOCK_POLL_SECONDS = 0.25


class BootstrapError(RuntimeError):
    pass


class BootstrapLockTimeout(BootstrapError):
    pass


def _alembic_config(database_url: str) -> Config:
    for base in (Path(__file__).resolve().parents[2], Path.cwd()):
        ini = base / "alembic.ini"
        if ini.is_file():
            cfg = Config(str(ini))
            cfg.set_main_option("script_location", str(base / "alembic"))
            cfg.attributes["database_url"] = database_url
            return cfg
    raise BootstrapError("alembic.ini not found (expected next to app/ or in cwd)")


def _upgrade_head(database_url: str) -> None:
    command.upgrade(_alembic_config(database_url), "head")


async def run_alembic_upgrade(database_url: str) -> None:
    await asyncio.to_thread(_upgrade_head, database_url)


async def run_checkpointer_setup(database_url: str) -> None:
    await setup_checkpointer(database_url)


async def _acquire_lock(conn: psycopg.AsyncConnection, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        cur = await conn.execute(
            "SELECT pg_try_advisory_lock(%s)", (BOOTSTRAP_LOCK_KEY,)
        )
        row = await cur.fetchone()
        if row and row[0]:
            return
        if time.monotonic() >= deadline:
            raise BootstrapLockTimeout(
                f"timed out after {timeout:g}s waiting for bootstrap advisory lock "
                f"{BOOTSTRAP_LOCK_KEY}; another api instance may be migrating or stuck"
            )
        await asyncio.sleep(LOCK_POLL_SECONDS)


async def bootstrap(
    database_url: str | None = None, lock_timeout: float | None = None
) -> None:
    """Run the full migrate + checkpointer-setup sequence under one lock.

    Raises on any failure; callers must not serve traffic unless this returns.
    """
    url = database_url or get_database_url()
    timeout = LOCK_TIMEOUT_SECONDS if lock_timeout is None else lock_timeout
    try:
        conn = await psycopg.AsyncConnection.connect(url, autocommit=True)
    except psycopg.Error as exc:
        raise BootstrapError(f"cannot connect to Postgres for bootstrap: {exc}") from exc
    try:
        await _acquire_lock(conn, timeout)
        logger.info("bootstrap: lock acquired; running alembic upgrade head")
        try:
            await run_alembic_upgrade(url)
        except Exception as exc:
            raise BootstrapError(f"alembic upgrade failed: {exc}") from exc
        logger.info("bootstrap: running checkpointer setup")
        try:
            await run_checkpointer_setup(url)
        except Exception as exc:
            raise BootstrapError(f"checkpointer setup failed: {exc}") from exc
        logger.info("bootstrap: complete")
    except psycopg.Error as exc:
        raise BootstrapError(f"bootstrap lock failed: {exc}") from exc
    finally:
        await conn.close()  # ends the session -> releases the advisory lock
