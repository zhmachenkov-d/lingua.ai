"""Router checkpointer: three integration_db tests + LLM-error skip unit."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from app.db.bootstrap import bootstrap
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
