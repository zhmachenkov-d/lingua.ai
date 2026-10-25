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
CONNECT_TIMEOUT_SECONDS = 10
# Work timeout fails startup loudly, but the lock is held until the in-flight
# migrate/setup worker finishes (_drain). A hung worker pins the lock until the
# process/session dies; peers are bounded by LOCK_TIMEOUT_SECONDS.
WORK_TIMEOUT_SECONDS = 120.0


class BootstrapError(RuntimeError):
    pass


class BootstrapLockTimeout(BootstrapError):
    pass


class BootstrapWorkTimeout(BootstrapError):
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


async def _drain(task: asyncio.Future) -> None:
    """Wait for ``task`` to finish; a cancel during the wait is re-raised after."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            cancelled = True
    if not task.cancelled():
        task.exception()  # mark retrieved; the caller reports its own error
    if cancelled:
        raise asyncio.CancelledError


async def _run_under_lock(work, what: str) -> None:
    """Run ``work`` bounded by WORK_TIMEOUT_SECONDS without ever abandoning it.

    ``wait_for`` cancelling the awaiter does not stop an Alembic thread, and the
    caller's ``finally`` releases the advisory lock. So the work runs as a shielded
    task and, on timeout (or cancel), is joined before returning control: the lock
    stays held until the in-flight worker has actually finished.
    """
    task = asyncio.ensure_future(work)
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=WORK_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        if task.done():
            # Finished at the deadline (or raised TimeoutError itself): use its
            # real outcome, not wait_for's TimeoutError.
            task.result()
            return
        logger.warning(
            "bootstrap: %s exceeded work timeout; holding lock until it finishes", what
        )
        await _drain(task)
        raise BootstrapWorkTimeout(
            f"{what} exceeded {WORK_TIMEOUT_SECONDS:g}s under lock"
        ) from exc
    except BaseException:
        await _drain(task)
        raise


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
        # TCP keepalive keeps the lock session alive while Alembic uses a
        # separate engine connection under the same critical section.
        conn = await psycopg.AsyncConnection.connect(
            url,
            autocommit=True,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
    except psycopg.Error as exc:
        raise BootstrapError(
            f"cannot connect to Postgres for bootstrap: {exc}"
        ) from exc
    try:
        await _acquire_lock(conn, timeout)
        logger.info("bootstrap: lock acquired; running alembic upgrade head")
        try:
            await _run_under_lock(run_alembic_upgrade(url), "alembic upgrade")
        except BootstrapError:
            raise
        except Exception as exc:
            raise BootstrapError(f"alembic upgrade failed: {exc}") from exc
        logger.info("bootstrap: running checkpointer setup")
        try:
            await _run_under_lock(run_checkpointer_setup(url), "checkpointer setup")
        except BootstrapError:
            raise
        except Exception as exc:
            raise BootstrapError(f"checkpointer setup failed: {exc}") from exc
        logger.info("bootstrap: complete")
    except psycopg.Error as exc:
        raise BootstrapError(f"bootstrap lock failed: {exc}") from exc
    finally:
        await conn.close()  # ends the session -> releases the advisory lock
