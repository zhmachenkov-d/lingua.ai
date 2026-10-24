import asyncio
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import create_engine

import app.db.bootstrap as bootstrap_mod
from app.db.bootstrap import (
    BOOTSTRAP_LOCK_KEY,
    BootstrapError,
    BootstrapLockTimeout,
    bootstrap,
)
from app.db.config import DatabaseConfigError, get_database_url, to_sqlalchemy_url
from app.main import app
from app.models import Base, Session

pytestmark = pytest.mark.integration_db

REPO_ROOT = Path(__file__).resolve().parents[3]
NON_SOT = re.compile(r"non-authoritative", re.I)
NOT_SOT = re.compile(r"not (?:the )?(?:source of truth|SoT)|not SoT", re.I)

LTM_TABLES = {
    "learner_profile",
    "vocabulary_item",
    "review_record",
    "error_log",
    "session",
}
CHECKPOINT_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}

EXPECTED_COLUMNS = {
    "learner_profile": {"id", "cefr_by_skill", "goals", "constraints", "created_at", "updated_at"},
    "vocabulary_item": {
        "id", "learner_id", "lemma", "source", "lexicon_provider", "textbook_id",
        "unit_ref", "status", "difficulty", "stability", "next_review",
        "retrievability", "learned", "learned_checked_at", "created_at", "updated_at",
    },
    "error_log": {
        "id", "learner_id", "error_type", "topic", "context", "occurred_at",
        "vocab_id", "rule_id", "session_id", "unit_ref", "count_7d",
    },
    "review_record": {
        "id", "learner_id", "vocab_id", "rating", "success", "drill_modality",
        "reviewed_at", "session_id", "error_id", "stability_after",
        "difficulty_after", "next_review_after",
    },
    "session": {
        "id", "learner_id", "active_agent", "touched_lemmas", "touched_rule_ids",
        "tblt_phase", "drafts", "unit_ref", "started_at", "updated_at",
    },
}


def _tables(url: str) -> set[str]:
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public'"
        ).fetchall()
    return {r[0] for r in rows}


def _columns(url: str, table: str) -> dict[str, tuple[str, str]]:
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


@pytest.fixture
def migrated_url(fresh_db_url: str) -> str:
    asyncio.run(bootstrap(fresh_db_url, lock_timeout=10))
    return fresh_db_url


def test_bootstrap_creates_ltm_session_and_checkpointer_tables(migrated_url: str) -> None:
    tables = _tables(migrated_url)
    assert LTM_TABLES <= tables
    assert {"checkpoints", "checkpoint_blobs", "checkpoint_writes"} <= tables
    assert "alembic_version" in tables


def test_bootstrap_is_idempotent(migrated_url: str) -> None:
    asyncio.run(bootstrap(migrated_url, lock_timeout=10))
    with psycopg.connect(migrated_url) as conn:
        assert conn.execute("SELECT count(*) FROM alembic_version").fetchone() == (1,)


def test_alembic_does_not_manage_checkpointer_tables() -> None:
    assert not CHECKPOINT_TABLES & set(Base.metadata.tables)


def test_d5_columns_present(migrated_url: str) -> None:
    for table, expected in EXPECTED_COLUMNS.items():
        assert expected <= set(_columns(migrated_url, table)), table
    vocab = _columns(migrated_url, "vocabulary_item")
    assert vocab["difficulty"][0] == "double precision"
    assert vocab["stability"][0] == "double precision"
    assert vocab["next_review"][0] == "timestamp with time zone"
    assert vocab["next_review"][1] == "NO"
    assert vocab["difficulty"][1] == "YES"
    assert vocab["stability"][1] == "YES"
    session = _columns(migrated_url, "session")
    assert session["touched_lemmas"][0] == "ARRAY"
    assert session["drafts"][0] == "jsonb"


def test_session_fks_are_nullable_on_delete_set_null(migrated_url: str) -> None:
    for table in ("error_log", "review_record"):
        assert _columns(migrated_url, table)["session_id"][1] == "YES"
    with psycopg.connect(migrated_url) as conn:
        rows = conn.execute(
            "SELECT conrelid::regclass::text, confdeltype FROM pg_constraint "
            "WHERE contype = 'f' AND confrelid = 'session'::regclass"
        ).fetchall()
    by_table = {r[0]: r[1] for r in rows}
    assert by_table.get("error_log") == "n"
    assert by_table.get("review_record") == "n"


def test_models_match_migration(migrated_url: str) -> None:
    engine = create_engine(to_sqlalchemy_url(migrated_url))
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "include_object": lambda obj, name, type_, reflected, compare_to: (
                        type_ != "table" or name in Base.metadata.tables
                    ),
                },
            )
            diff = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()
    assert diff == []


def test_checkpointer_round_trip(migrated_url: str) -> None:
    thread_id = "learner:42/session:ünï-🙂 thread"
    checkpoint = {
        "v": 4,
        "id": "1ef4f797-8335-6428-8001-8a1503f9b875",
        "ts": "2026-10-24T10:00:00+00:00",
        # non-primitive value -> serialized into checkpoint_blobs
        "channel_values": {
            "active_agent": "Tutor",
            "n": 3,
            "touched_lemmas": ["apple", "pear"],
            "drafts": {"reply": {"text": "hi", "tokens": [1, 2, 3]}},
            "when": datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc),
        },
        "channel_versions": {
            "active_agent": "1",
            "n": "1",
            "touched_lemmas": "1",
            "drafts": "1",
            "when": "1",
        },
        "versions_seen": {"__input__": {}, "node:router": {"active_agent": "1"}},
        "updated_channels": ["active_agent", "n", "touched_lemmas", "drafts", "when"],
    }
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

    async def run():
        async with AsyncPostgresSaver.from_conn_string(migrated_url) as saver:
            written = await saver.aput(
                config, checkpoint, {"source": "input", "step": 0}, checkpoint["channel_versions"]
            )
            return await saver.aget(written)

    got = asyncio.run(run())
    assert got is not None
    for key in checkpoint:
        assert got[key] == checkpoint[key], key

    with psycopg.connect(migrated_url) as conn:
        blobs = conn.execute(
            "SELECT count(*) FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,)
        ).fetchone()
    assert blobs and blobs[0] > 0

    async def other_thread():
        async with AsyncPostgresSaver.from_conn_string(migrated_url) as saver:
            return await saver.aget(
                {"configurable": {"thread_id": "other", "checkpoint_ns": ""}}
            )

    assert asyncio.run(other_thread()) is None


def test_session_non_sot_wording_in_model_and_readme() -> None:
    doc = Session.__doc__ or ""
    assert NON_SOT.search(doc) and NOT_SOT.search(doc) and "checkpointer" in doc
    readme = (REPO_ROOT / "README.md").read_text()
    assert NON_SOT.search(readme) and NOT_SOT.search(readme)
    assert re.search(r"Session[^\n]*checkpointer|checkpointer[^\n]*Session", readme)


def test_missing_database_url_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(DatabaseConfigError, match="DATABASE_URL"):
        get_database_url()
    with pytest.raises(DatabaseConfigError):
        asyncio.run(bootstrap())


def test_unreachable_db_fails_loudly() -> None:
    with pytest.raises(BootstrapError, match="cannot connect"):
        asyncio.run(
            bootstrap("postgresql://nobody:x@127.0.0.1:1/none?connect_timeout=2", 1)
        )


def test_upgrade_ok_setup_fails_then_restart_recovers(
    fresh_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(_: str) -> None:
        raise RuntimeError("simulated setup failure")

    monkeypatch.setattr(bootstrap_mod, "run_checkpointer_setup", boom)
    with pytest.raises(BootstrapError, match="checkpointer setup failed"):
        asyncio.run(bootstrap(fresh_db_url, lock_timeout=10))
    tables = _tables(fresh_db_url)
    assert LTM_TABLES <= tables and "checkpoints" not in tables

    monkeypatch.undo()
    asyncio.run(bootstrap(fresh_db_url, lock_timeout=10))  # lock was released
    assert "checkpoints" in _tables(fresh_db_url)


def test_upgrade_fails_setup_not_run_then_restart_recovers(
    fresh_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = []

    async def boom(_: str) -> None:
        raise RuntimeError("simulated upgrade failure")

    async def spy(url: str) -> None:
        called.append(url)

    monkeypatch.setattr(bootstrap_mod, "run_alembic_upgrade", boom)
    monkeypatch.setattr(bootstrap_mod, "run_checkpointer_setup", spy)
    with pytest.raises(BootstrapError, match="alembic upgrade failed"):
        asyncio.run(bootstrap(fresh_db_url, lock_timeout=10))
    assert called == []

    monkeypatch.undo()
    asyncio.run(bootstrap(fresh_db_url, lock_timeout=10))
    assert LTM_TABLES <= _tables(fresh_db_url)


def test_lock_wait_is_bounded_and_loud(fresh_db_url: str) -> None:
    with psycopg.connect(fresh_db_url, autocommit=True) as holder:
        holder.execute("SELECT pg_advisory_lock(%s)", (BOOTSTRAP_LOCK_KEY,))
        started = time.monotonic()
        with pytest.raises(BootstrapLockTimeout, match="timed out"):
            asyncio.run(bootstrap(fresh_db_url, lock_timeout=1))
        assert time.monotonic() - started < 10
    assert "learner_profile" not in _tables(fresh_db_url)  # nothing ran unlocked


def test_concurrent_bootstraps_are_serialized(
    fresh_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, str]] = []
    orig_upgrade = bootstrap_mod.run_alembic_upgrade
    orig_setup = bootstrap_mod.run_checkpointer_setup

    def wrap(name, fn):
        async def inner(url: str) -> None:
            events.append(("start", name))
            await asyncio.sleep(0.5)  # widen the window an unlocked overlap would hit
            await fn(url)
            events.append(("end", name))

        return inner

    monkeypatch.setattr(bootstrap_mod, "run_alembic_upgrade", wrap("upgrade", orig_upgrade))
    monkeypatch.setattr(bootstrap_mod, "run_checkpointer_setup", wrap("setup", orig_setup))

    async def both() -> None:
        await asyncio.gather(
            bootstrap(fresh_db_url, lock_timeout=30),
            bootstrap(fresh_db_url, lock_timeout=30),
        )

    asyncio.run(both())

    # Two full critical sections, never interleaved.
    unit = [("start", "upgrade"), ("end", "upgrade"), ("start", "setup"), ("end", "setup")]
    assert events == unit + unit
    assert LTM_TABLES <= _tables(fresh_db_url)
    assert "checkpoints" in _tables(fresh_db_url)
    with psycopg.connect(fresh_db_url) as conn:
        assert conn.execute("SELECT count(*) FROM alembic_version").fetchone() == (1,)


def test_lifespan_bootstraps_then_health_ok(
    fresh_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", fresh_db_url)
    with TestClient(app) as client:
        assert "checkpoints" in _tables(fresh_db_url)  # already done before serving
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_failure_means_no_serving(
    fresh_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(_: str) -> None:
        raise RuntimeError("simulated setup failure")

    monkeypatch.setenv("DATABASE_URL", fresh_db_url)
    monkeypatch.setattr(bootstrap_mod, "run_checkpointer_setup", boom)
    with pytest.raises(BootstrapError):
        with TestClient(app):
            pytest.fail("app must not start serving")
