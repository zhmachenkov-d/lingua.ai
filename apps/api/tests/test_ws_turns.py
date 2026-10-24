"""WebSocket turn skeleton — mocked LLM/checkpointer (no live DeepSeek)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from app.api.routes import ws as ws_mod
from app.llm.adapter import (
    BACKUP_NOTICE,
    ClassifyResult,
    LlmMisconfigured,
    LlmUnavailable,
)
from app.main import app
from app.router.turn import CTA_MESSAGE, CTAS, TurnError, TurnSuccess, handle_turn
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse


@pytest.fixture(autouse=True)
def _reset_ws_gate() -> Iterator[None]:
    ws_mod.reset_ws_gate_for_tests()
    yield
    ws_mod.reset_ws_gate_for_tests()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch("app.main.bootstrap", new_callable=AsyncMock):
        with TestClient(app) as c:
            yield c


def _cta_success(
    *,
    turn_id: str | None = None,
    backup_notice: str | None = None,
) -> TurnSuccess:
    return TurnSuccess(
        message=CTA_MESSAGE,
        ctas=CTAS,
        clarify=None,
        backup_notice=backup_notice,
        turn_id=turn_id,
        last_user_text="x",
    )


def test_happy_cta_turn_complete_no_token_delta(client: TestClient) -> None:
    with patch(
        "app.api.routes.ws.handle_turn",
        new_callable=AsyncMock,
        return_value=_cta_success(turn_id="t-1"),
    ) as mocked:
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {"kind": "turn_request", "text": "хочу урок", "turn_id": "t-1"}
            )
            event = ws.receive_json()
    mocked.assert_awaited_once()
    assert event["kind"] == "turn_complete"
    assert event["message"] == CTA_MESSAGE
    assert event["ctas"] == list(CTAS)
    assert event["clarify"] is None
    assert event["backup_notice"] is None
    assert event["turn_id"] == "t-1"


def test_blank_skips_llm_and_returns_cta(client: TestClient) -> None:
    with (
        patch("app.router.turn.classify_turn", new_callable=AsyncMock) as classify,
        patch(
            "app.router.turn.write_turn_snapshot",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"kind": "turn_request", "text": "   \n\t  "})
            event = ws.receive_json()
    classify.assert_not_awaited()
    assert event["kind"] == "turn_complete"
    assert event["ctas"] == list(CTAS)
    assert event["backup_notice"] is None
    assert "turn_id" not in event


def test_turn_id_echo_on_error(client: TestClient) -> None:
    with patch(
        "app.api.routes.ws.handle_turn",
        new_callable=AsyncMock,
        return_value=TurnError(
            code="llm_unavailable",
            message="down",
            turn_id="e-9",
        ),
    ):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"kind": "turn_request", "text": "hi", "turn_id": "e-9"})
            event = ws.receive_json()
    assert event == {
        "kind": "error",
        "message": "down",
        "code": "llm_unavailable",
        "turn_id": "e-9",
    }


def test_invalid_non_json(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_text("not-json{")
        event = ws.receive_json()
    assert event["kind"] == "error"
    assert event["code"] == "invalid_turn_request"


def test_invalid_kind(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"kind": "token_delta", "text": "x", "turn_id": "a"})
        event = ws.receive_json()
    assert event["code"] == "invalid_turn_request"
    assert event["turn_id"] == "a"


def test_invalid_missing_text(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"kind": "turn_request", "turn_id": "b"})
        event = ws.receive_json()
    assert event["code"] == "invalid_turn_request"
    assert event["turn_id"] == "b"


def test_overlapping_inflight_turn(client: TestClient) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_turn(
        text: str, *, turn_id: str | None = None, **_: object
    ) -> TurnSuccess:
        started.set()
        await release.wait()
        return _cta_success(turn_id=turn_id)

    with patch("app.api.routes.ws.handle_turn", side_effect=slow_turn):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"kind": "turn_request", "text": "one", "turn_id": "1"})
            for _ in range(100):
                if started.is_set():
                    break
                time.sleep(0.01)
            assert started.is_set()
            ws.send_json({"kind": "turn_request", "text": "two", "turn_id": "2"})
            overlap = ws.receive_json()
            release.set()
            complete = ws.receive_json()
    assert overlap["code"] == "invalid_turn_request"
    assert overlap["turn_id"] == "2"
    assert complete["kind"] == "turn_complete"
    assert complete["turn_id"] == "1"


def test_second_ws_409_while_first_open(client: TestClient) -> None:
    with patch(
        "app.router.turn.write_turn_snapshot",
        new_callable=AsyncMock,
        return_value={},
    ):
        with client.websocket_connect("/ws") as first:
            with pytest.raises(WebSocketDenialResponse) as exc_info:
                with client.websocket_connect("/ws"):
                    pass
            assert exc_info.value.status_code == 409
            first.send_json({"kind": "turn_request", "text": " "})
            event = first.receive_json()
            assert event["kind"] == "turn_complete"


def test_missing_key_error_code(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with patch(
        "app.router.turn.classify_turn",
        new_callable=AsyncMock,
        side_effect=LlmMisconfigured("missing"),
    ):
        with patch(
            "app.router.turn.write_turn_snapshot", new_callable=AsyncMock
        ) as write:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"kind": "turn_request", "text": "hello"})
                event = ws.receive_json()
    write.assert_not_awaited()
    assert event["kind"] == "error"
    assert event["code"] == "llm_misconfigured"


def test_both_down_error_code(client: TestClient) -> None:
    with patch(
        "app.router.turn.classify_turn",
        new_callable=AsyncMock,
        side_effect=LlmUnavailable("down"),
    ):
        with patch(
            "app.router.turn.write_turn_snapshot", new_callable=AsyncMock
        ) as write:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"kind": "turn_request", "text": "hello"})
                event = ws.receive_json()
    write.assert_not_awaited()
    assert event["code"] == "llm_unavailable"


def test_escalation_sets_backup_notice(client: TestClient) -> None:
    with patch(
        "app.router.turn.classify_turn",
        new_callable=AsyncMock,
        return_value=ClassifyResult(handoff=None, used_backup=True),
    ):
        with patch(
            "app.router.turn.write_turn_snapshot",
            new_callable=AsyncMock,
            return_value={},
        ):
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"kind": "turn_request", "text": "hello"})
                event = ws.receive_json()
    assert event["kind"] == "turn_complete"
    assert event["backup_notice"] == BACKUP_NOTICE
    assert event["message"] == CTA_MESSAGE
    assert BACKUP_NOTICE not in event["message"]


def test_aput_fail_no_turn_complete(client: TestClient) -> None:
    with patch(
        "app.router.turn.classify_turn",
        new_callable=AsyncMock,
        return_value=ClassifyResult(handoff=None, used_backup=False),
    ):
        with patch(
            "app.router.turn.write_turn_snapshot",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db down"),
        ):
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"kind": "turn_request", "text": "hello", "turn_id": "z"})
                event = ws.receive_json()
    assert event["kind"] == "error"
    assert event["code"] == "checkpointer_write_failed"
    assert event["turn_id"] == "z"


def test_invalid_inbound_does_not_call_llm(client: TestClient) -> None:
    with patch("app.router.turn.classify_turn", new_callable=AsyncMock) as classify:
        with patch(
            "app.router.turn.write_turn_snapshot", new_callable=AsyncMock
        ) as write:
            with client.websocket_connect("/ws") as ws:
                ws.send_text("{")
                event = ws.receive_json()
    classify.assert_not_awaited()
    write.assert_not_awaited()
    assert event["code"] == "invalid_turn_request"


def test_handle_turn_blank_no_llm() -> None:
    with (
        patch("app.router.turn.classify_turn", new_callable=AsyncMock) as classify,
        patch(
            "app.router.turn.write_turn_snapshot",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        result = asyncio.run(handle_turn(""))
    classify.assert_not_awaited()
    assert isinstance(result, TurnSuccess)
    assert result.backup_notice is None
    assert result.message == CTA_MESSAGE


def test_disconnect_mid_turn_cancels_without_snapshot(client: TestClient) -> None:
    """Client disconnect mid-LLM → abandon; no turn_complete; no snapshot write."""
    started = asyncio.Event()
    release = asyncio.Event()
    write = AsyncMock(return_value={})

    async def slow_classify(*_a: object, **_k: object) -> ClassifyResult:
        started.set()
        await release.wait()
        return ClassifyResult(handoff=None, used_backup=False)

    with (
        patch("app.router.turn.classify_turn", side_effect=slow_classify),
        patch("app.router.turn.write_turn_snapshot", write),
    ):
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"kind": "turn_request", "text": "hello"})
            for _ in range(100):
                if started.is_set():
                    break
                time.sleep(0.01)
            assert started.is_set()
            # Closing the context disconnects before release — cancel in-flight.
        release.set()
        time.sleep(0.05)
    write.assert_not_awaited()
