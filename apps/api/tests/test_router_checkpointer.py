"""Router checkpointer: integration_db tip writes + unit coverage."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import psycopg
import pytest
from app.db.bootstrap import bootstrap
from app.db.checkpointer import open_checkpointer
from app.db.constants import MVP_LEARNER_ID
from app.llm.adapter import ClassifyResult
from app.router.turn import (
    THREAD_ID,
    TurnError,
    TurnSuccess,
    get_turn_snapshot,
    handle_turn,
    write_turn_snapshot,
)


@pytest.fixture
def migrated_url(fresh_db_url: str) -> str:
    asyncio.run(bootstrap(fresh_db_url, lock_timeout=10))
    return fresh_db_url


async def _channel_versions(database_url: str) -> dict[str, object]:
    config = {"configurable": {"thread_id": THREAD_ID, "checkpoint_ns": ""}}
    async with open_checkpointer(database_url) as saver:
        got = await saver.aget(config)  # type: ignore[arg-type]
    assert got is not None
    versions = got["channel_versions"]
    assert isinstance(versions, dict)
    return dict(versions)


@pytest.mark.integration_db
def test_router_checkpointer_round_trip(migrated_url: str) -> None:
    assert THREAD_ID == str(MVP_LEARNER_ID)
    written = asyncio.run(
        write_turn_snapshot(last_user_text="hello unit", database_url=migrated_url)
    )
    assert written["last_user_text"] == "hello unit"
    assert written["active_agent"] is None
    assert isinstance(written["turn_at"], str)

    got = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert got is not None
    assert got["last_user_text"] == "hello unit"
    assert got["active_agent"] is None
    assert got["turn_at"] == written["turn_at"]


@pytest.mark.integration_db
def test_channel_versions_monotonic_across_turns(migrated_url: str) -> None:
    asyncio.run(write_turn_snapshot(last_user_text="first", database_url=migrated_url))
    first = asyncio.run(_channel_versions(migrated_url))
    asyncio.run(write_turn_snapshot(last_user_text="second", database_url=migrated_url))
    second = asyncio.run(_channel_versions(migrated_url))
    tip = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert tip is not None
    assert tip["last_user_text"] == "second"
    for key in ("last_user_text", "active_agent", "turn_at"):
        assert isinstance(first[key], str)
        assert isinstance(second[key], str)
        assert second[key] > first[key]


def _version_prefix(version: object) -> int:
    return int(str(version).split(".", 1)[0])


async def _all_channel_version_prefixes(database_url: str, key: str) -> list[int]:
    config = {"configurable": {"thread_id": THREAD_ID, "checkpoint_ns": ""}}
    prefixes: list[int] = []
    async with open_checkpointer(database_url) as saver:
        async for item in saver.alist(config):  # type: ignore[arg-type]
            versions = item.checkpoint.get("channel_versions")
            assert isinstance(versions, dict)
            prefixes.append(_version_prefix(versions[key]))
    return prefixes


@pytest.mark.integration_db
def test_overlapping_writers_do_not_duplicate_channel_versions(
    migrated_url: str,
) -> None:
    """Advisory lock serializes aget→aput; delay would collide without the lock."""

    async def delay_after_aget() -> None:
        await asyncio.sleep(0.05)

    async def race() -> None:
        with patch(
            "app.router.turn._after_snapshot_aget",
            new=delay_after_aget,
        ):
            await asyncio.gather(
                write_turn_snapshot(
                    last_user_text="writer-a", database_url=migrated_url
                ),
                write_turn_snapshot(
                    last_user_text="writer-b", database_url=migrated_url
                ),
            )

    asyncio.run(race())
    prefixes = asyncio.run(
        _all_channel_version_prefixes(migrated_url, "last_user_text")
    )
    assert len(prefixes) == 2
    assert len(set(prefixes)) == 2
    assert max(prefixes) == 2
    tip = asyncio.run(_channel_versions(migrated_url))
    assert _version_prefix(tip["last_user_text"]) == 2


@pytest.mark.integration_db
def test_channel_versions_advance_from_legacy_plain_one(
    migrated_url: str,
) -> None:
    """Prior tip with legacy Router plain "1" stamps must still advance."""
    from langgraph.checkpoint.base.id import uuid6

    legacy = {
        "v": 4,
        "id": str(uuid6()),
        "ts": "2026-10-26T00:00:00+00:00",
        "channel_values": {
            "last_user_text": "legacy",
            "active_agent": None,
            "turn_at": "2026-10-26T00:00:00+00:00",
        },
        "channel_versions": {
            "last_user_text": "1",
            "active_agent": "1",
            "turn_at": "1",
        },
        "versions_seen": {},
        "updated_channels": ["last_user_text", "active_agent", "turn_at"],
    }
    config = {"configurable": {"thread_id": THREAD_ID, "checkpoint_ns": ""}}

    async def seed() -> None:
        async with open_checkpointer(migrated_url) as saver:
            await saver.aput(
                config,  # type: ignore[arg-type]
                legacy,  # type: ignore[arg-type]
                {"source": "update", "step": 0, "parents": {}},
                legacy["channel_versions"],
            )

    asyncio.run(seed())
    asyncio.run(
        write_turn_snapshot(last_user_text="after-legacy", database_url=migrated_url)
    )
    versions = asyncio.run(_channel_versions(migrated_url))
    tip = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert tip is not None
    assert tip["last_user_text"] == "after-legacy"
    for key in ("last_user_text", "active_agent", "turn_at"):
        assert isinstance(versions[key], str)
        assert versions[key] != "1"
        assert int(str(versions[key]).split(".", 1)[0]) == 2


@pytest.mark.integration_db
def test_handle_turn_blank_persists_snapshot(migrated_url: str) -> None:
    with patch("app.router.turn.classify_turn", new_callable=AsyncMock) as classify:
        result = asyncio.run(handle_turn("  \t ", database_url=migrated_url))
    classify.assert_not_awaited()
    assert isinstance(result, TurnSuccess)
    snap = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert snap is not None
    assert snap["last_user_text"] == ""
    assert snap["active_agent"] is None


@pytest.mark.integration_db
def test_handle_turn_success_persists_after_classify(migrated_url: str) -> None:
    with patch(
        "app.router.turn.classify_turn",
        new_callable=AsyncMock,
        return_value=ClassifyResult(handoff=None, used_backup=False),
    ):
        result = asyncio.run(
            handle_turn("study", turn_id="r1", database_url=migrated_url)
        )
    assert isinstance(result, TurnSuccess)
    assert result.turn_id == "r1"
    snap = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert snap is not None
    assert snap["last_user_text"] == "study"


@pytest.mark.integration_db
def test_handle_turn_multiturn_updates_last_user_text(migrated_url: str) -> None:
    classify = AsyncMock(
        return_value=ClassifyResult(handoff=None, used_backup=False),
    )
    with patch("app.router.turn.classify_turn", classify):
        first = asyncio.run(
            handle_turn("first turn", turn_id="t1", database_url=migrated_url)
        )
        second = asyncio.run(
            handle_turn("second turn", turn_id="t2", database_url=migrated_url)
        )
    assert isinstance(first, TurnSuccess)
    assert isinstance(second, TurnSuccess)
    assert classify.await_count == 2
    snap = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert snap is not None
    assert snap["last_user_text"] == "second turn"
    assert snap["active_agent"] is None


@pytest.mark.integration_db
def test_handle_turn_blank_after_nonblank_wipes_last_user_text(
    migrated_url: str,
) -> None:
    classify = AsyncMock(
        return_value=ClassifyResult(handoff=None, used_backup=False),
    )
    with patch("app.router.turn.classify_turn", classify):
        first = asyncio.run(
            handle_turn("kept until blank", turn_id="t1", database_url=migrated_url)
        )
        blank = asyncio.run(
            handle_turn("  \t ", turn_id="t2", database_url=migrated_url)
        )
    assert isinstance(first, TurnSuccess)
    assert isinstance(blank, TurnSuccess)
    assert classify.await_count == 1
    snap = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert snap is not None
    assert snap["last_user_text"] == ""
    assert snap["active_agent"] is None


def _session_mirror_rows(database_url: str) -> list[tuple[object, ...]]:
    with psycopg.connect(database_url) as conn:
        return list(
            conn.execute(
                "SELECT id, learner_id, active_agent, updated_at FROM session "
                "WHERE learner_id = %s ORDER BY started_at",
                (str(MVP_LEARNER_ID),),
            ).fetchall()
        )


@pytest.mark.integration_db
def test_successful_snapshot_upserts_session_mirror(migrated_url: str) -> None:
    asyncio.run(
        write_turn_snapshot(last_user_text="mirror-1", database_url=migrated_url)
    )
    rows = _session_mirror_rows(migrated_url)
    assert len(rows) == 1
    assert str(rows[0][1]) == str(MVP_LEARNER_ID)
    assert rows[0][2] == "Router"
    first_updated = rows[0][3]
    assert isinstance(first_updated, datetime)

    asyncio.run(
        write_turn_snapshot(last_user_text="mirror-2", database_url=migrated_url)
    )
    rows_after = _session_mirror_rows(migrated_url)
    assert len(rows_after) == 1
    assert rows_after[0][0] == rows[0][0]
    assert rows_after[0][2] == "Router"
    assert rows_after[0][3] > first_updated


def test_handle_turn_llm_error_skips_snapshot() -> None:
    from app.llm.adapter import LlmUnavailable

    with (
        patch(
            "app.router.turn.classify_turn",
            new_callable=AsyncMock,
            side_effect=LlmUnavailable("x"),
        ),
        patch("app.router.turn.write_turn_snapshot", new_callable=AsyncMock) as write,
    ):
        result = asyncio.run(handle_turn("hi", turn_id="t"))
    write.assert_not_awaited()
    assert isinstance(result, TurnError)
    assert result.code == "llm_unavailable"


@asynccontextmanager
async def _noop_snapshot_write_lock(_database_url: str | None = None):
    yield


def _hung_checkpointer_open():
    """Async context manager yielding a saver whose ``aput`` never completes."""

    async def hung_aput(*_a: object, **_k: object) -> None:
        await asyncio.sleep(60)

    saver = MagicMock()
    saver.aget = AsyncMock(return_value=None)
    saver.aput = hung_aput
    saver.get_next_version = MagicMock(
        return_value="00000000000000000000000000000001.0.0"
    )

    @asynccontextmanager
    async def fake_open(_database_url: str | None = None):
        yield saver

    return fake_open


def test_write_turn_snapshot_times_out_on_hung_aput() -> None:
    with (
        patch("app.router.turn._snapshot_write_lock", _noop_snapshot_write_lock),
        patch("app.router.turn.open_checkpointer", _hung_checkpointer_open()),
        patch("app.router.turn.CHECKPOINTER_WRITE_TIMEOUT_SECONDS", 0.05),
    ):
        with pytest.raises(TimeoutError):
            asyncio.run(write_turn_snapshot(last_user_text="hung"))


def test_handle_turn_maps_snapshot_timeout_to_checkpointer_write_failed() -> None:
    with (
        patch("app.router.turn._snapshot_write_lock", _noop_snapshot_write_lock),
        patch("app.router.turn.open_checkpointer", _hung_checkpointer_open()),
        patch("app.router.turn.CHECKPOINTER_WRITE_TIMEOUT_SECONDS", 0.05),
    ):
        # Blank path skips LLM and still writes the snapshot.
        result = asyncio.run(handle_turn("  \t ", turn_id="to"))
    assert isinstance(result, TurnError)
    assert result.code == "checkpointer_write_failed"
    assert result.turn_id == "to"


def _ok_checkpointer_open():
    """Async context manager yielding a saver that completes ``aput``."""

    saver = MagicMock()
    saver.aget = AsyncMock(return_value=None)
    saver.aput = AsyncMock(return_value=None)
    saver.get_next_version = MagicMock(
        return_value="00000000000000000000000000000001.0.0"
    )

    @asynccontextmanager
    async def fake_open(_database_url: str | None = None):
        yield saver

    return fake_open, saver


def test_write_turn_snapshot_succeeds_when_mirror_fails() -> None:
    fake_open, saver = _ok_checkpointer_open()
    with (
        patch("app.router.turn._snapshot_write_lock", _noop_snapshot_write_lock),
        patch("app.router.turn.open_checkpointer", fake_open),
        patch(
            "app.router.turn.upsert_session_mirror",
            new_callable=AsyncMock,
            side_effect=RuntimeError("mirror down"),
        ) as mirror,
    ):
        written = asyncio.run(write_turn_snapshot(last_user_text="still ok"))
    mirror.assert_awaited_once()
    saver.aput.assert_awaited_once()
    assert written["last_user_text"] == "still ok"
    assert written["active_agent"] is None


def test_handle_turn_succeeds_when_mirror_fails() -> None:
    fake_open, saver = _ok_checkpointer_open()
    with (
        patch("app.router.turn._snapshot_write_lock", _noop_snapshot_write_lock),
        patch("app.router.turn.open_checkpointer", fake_open),
        patch(
            "app.router.turn.upsert_session_mirror",
            new_callable=AsyncMock,
            side_effect=RuntimeError("mirror down"),
        ),
    ):
        result = asyncio.run(handle_turn("  \t ", turn_id="m1"))
    assert isinstance(result, TurnSuccess)
    assert result.turn_id == "m1"
    saver.aput.assert_awaited_once()
