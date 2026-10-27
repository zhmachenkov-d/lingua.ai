"""Unit + integration_db coverage for conflict-safe Session mirror upsert."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from app.db.bootstrap import _alembic_config, bootstrap
from app.db.constants import MVP_LEARNER_ID
from app.router.session_mirror import ensure_mvp_learner_profile, upsert_session_mirror
from sqlalchemy.dialects import postgresql


def _compile(stmt: object) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_ensure_mvp_learner_profile_conflict_safe_insert() -> None:
    db = AsyncMock()
    db.execute = AsyncMock()

    asyncio.run(ensure_mvp_learner_profile(db))

    db.execute.assert_awaited_once()
    sql = _compile(db.execute.call_args[0][0])
    assert "INSERT INTO learner_profile" in sql
    assert "ON CONFLICT" in sql
    assert "DO NOTHING" in sql


def _patch_ephemeral_db(db: AsyncMock):
    """Wire create_async_engine / async_sessionmaker to yield ``db``."""

    engine = MagicMock()
    engine.dispose = AsyncMock()

    @asynccontextmanager
    async def _session_cm():
        yield db

    factory = MagicMock(return_value=_session_cm())
    return patch.multiple(
        "app.router.session_mirror",
        create_async_engine=MagicMock(return_value=engine),
        async_sessionmaker=MagicMock(return_value=factory),
        get_database_url=MagicMock(return_value="postgresql://x/y"),
        to_sqlalchemy_url=MagicMock(side_effect=lambda u: u),
    ), engine


def test_upsert_session_mirror_uses_on_conflict_do_update() -> None:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    patches, engine = _patch_ephemeral_db(db)
    with patches:
        asyncio.run(upsert_session_mirror(database_url="postgresql://test/db"))

    assert db.execute.await_count == 2
    profile_sql = _compile(db.execute.call_args_list[0][0][0])
    assert "ON CONFLICT" in profile_sql and "DO NOTHING" in profile_sql

    upsert_sql = _compile(db.execute.call_args_list[1][0][0])
    assert "INSERT INTO session" in upsert_sql
    assert "ON CONFLICT (learner_id)" in upsert_sql
    assert "DO UPDATE" in upsert_sql
    assert "active_agent" in upsert_sql
    assert "updated_at" in upsert_sql
    db.commit.assert_awaited_once()
    engine.dispose.assert_awaited_once()


def test_upsert_session_mirror_uses_default_database_url() -> None:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    patches, _engine = _patch_ephemeral_db(db)
    with patches:
        asyncio.run(upsert_session_mirror())

    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()


def _session_count(url: str, learner_id: object | None = None) -> int:
    lid = learner_id if learner_id is not None else MVP_LEARNER_ID
    with psycopg.connect(url) as conn:
        row = conn.execute(
            "SELECT count(*) FROM session WHERE learner_id = %s",
            (str(lid),),
        ).fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.integration_db
def test_concurrent_first_upserts_one_session_row(fresh_db_url: str) -> None:
    """AC1/AC3: parallel first upserts → one row; neither aborts on UniqueViolation."""

    async def race() -> None:
        await bootstrap(fresh_db_url, lock_timeout=10)
        await asyncio.gather(
            upsert_session_mirror(database_url=fresh_db_url),
            upsert_session_mirror(database_url=fresh_db_url),
        )

    asyncio.run(race())
    assert _session_count(fresh_db_url) == 1


@pytest.mark.integration_db
def test_upsert_after_existing_updates_same_row(fresh_db_url: str) -> None:
    """Matrix: upsert after existing row keeps a single updated mirror row."""

    async def first() -> None:
        await bootstrap(fresh_db_url, lock_timeout=10)
        await upsert_session_mirror(database_url=fresh_db_url)

    asyncio.run(first())
    with psycopg.connect(fresh_db_url) as conn:
        rows = conn.execute(
            "SELECT id, active_agent, updated_at FROM session WHERE learner_id = %s",
            (str(MVP_LEARNER_ID),),
        ).fetchall()
    assert len(rows) == 1
    first_id, first_agent, first_updated = rows[0]
    assert first_agent == "Router"

    asyncio.run(upsert_session_mirror(database_url=fresh_db_url))
    with psycopg.connect(fresh_db_url) as conn:
        rows_after = conn.execute(
            "SELECT id, active_agent, updated_at FROM session WHERE learner_id = %s",
            (str(MVP_LEARNER_ID),),
        ).fetchall()
    assert len(rows_after) == 1
    assert rows_after[0][0] == first_id
    assert rows_after[0][1] == "Router"
    assert rows_after[0][2] > first_updated


@pytest.mark.integration_db
def test_migration_0002_dedupes_and_remaps_session_fks(fresh_db_url: str) -> None:
    """AC2: dedupe by survivor rule, remap FKs, then UNIQUE(learner_id)."""
    cfg = _alembic_config(fresh_db_url)
    command.upgrade(cfg, "0001")

    survivor_id = uuid4()
    discarded_id = uuid4()
    error_id = uuid4()
    review_id = uuid4()
    vocab_id = uuid4()

    with psycopg.connect(fresh_db_url) as conn:
        conn.execute(
            "INSERT INTO learner_profile (id) VALUES (%s)",
            (str(MVP_LEARNER_ID),),
        )
        # Discarded: older updated_at; survivor: newer → keep survivor.
        conn.execute(
            "INSERT INTO session (id, learner_id, active_agent, started_at, updated_at) "
            "VALUES "
            "(%s, %s, 'Tutor', "
            " '2020-01-01 00:00:00+00'::timestamptz, "
            " '2020-01-01 00:00:00+00'::timestamptz), "
            "(%s, %s, 'Router', "
            " '2020-01-02 00:00:00+00'::timestamptz, "
            " '2020-01-03 00:00:00+00'::timestamptz)",
            (
                str(discarded_id),
                str(MVP_LEARNER_ID),
                str(survivor_id),
                str(MVP_LEARNER_ID),
            ),
        )
        conn.execute(
            "INSERT INTO vocabulary_item (id, learner_id, lemma, source, status) "
            "VALUES (%s, %s, 'test', 'textbook', 'Unseen')",
            (str(vocab_id), str(MVP_LEARNER_ID)),
        )
        conn.execute(
            "INSERT INTO error_log "
            "(id, learner_id, error_type, topic, context, session_id) "
            "VALUES (%s, %s, 'grammar', 'articles', 'a', %s)",
            (str(error_id), str(MVP_LEARNER_ID), str(discarded_id)),
        )
        conn.execute(
            "INSERT INTO review_record "
            "(id, learner_id, vocab_id, rating, success, drill_modality, session_id) "
            "VALUES (%s, %s, %s, 'Good', true, 'match', %s)",
            (str(review_id), str(MVP_LEARNER_ID), str(vocab_id), str(discarded_id)),
        )
        conn.commit()

    command.upgrade(cfg, "0002")

    with psycopg.connect(fresh_db_url) as conn:
        sessions = conn.execute(
            "SELECT id FROM session WHERE learner_id = %s",
            (str(MVP_LEARNER_ID),),
        ).fetchall()
        assert len(sessions) == 1
        assert sessions[0][0] == survivor_id

        err_sid = conn.execute(
            "SELECT session_id FROM error_log WHERE id = %s",
            (str(error_id),),
        ).fetchone()
        assert err_sid is not None and err_sid[0] == survivor_id

        rev_sid = conn.execute(
            "SELECT session_id FROM review_record WHERE id = %s",
            (str(review_id),),
        ).fetchone()
        assert rev_sid is not None and rev_sid[0] == survivor_id

        uniq = conn.execute(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname = 'session_learner_id_key' AND contype = 'u'"
        ).fetchone()
        assert uniq is not None
