"""Router checkpointer: five integration_db tests + LLM-error skip unit."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

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
    asyncio.run(
        write_turn_snapshot(last_user_text="first", database_url=migrated_url)
    )
    first = asyncio.run(_channel_versions(migrated_url))
    asyncio.run(
        write_turn_snapshot(last_user_text="second", database_url=migrated_url)
    )
    second = asyncio.run(_channel_versions(migrated_url))
    tip = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert tip is not None
    assert tip["last_user_text"] == "second"
    for key in ("last_user_text", "active_agent", "turn_at"):
        assert isinstance(first[key], str)
        assert isinstance(second[key], str)
        assert second[key] > first[key]


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
