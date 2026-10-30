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
from app.router.turn import (
    BLANK_INPUT,
    CTA_MESSAGE,
    CTAS,
    UNKNOWN_INTENT,
    TurnError,
    TurnSuccess,
    handle_turn,
)
from app.schemas.ws import MAX_TURN_TEXT_LENGTH
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


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


def test_teach_emits_token_delta_then_turn_complete(client: TestClient) -> None:
    teach = TurnSuccess(
        message="Разберём unit ef4-beg-sb/1A",
        ctas=(),
        clarify=None,
        backup_notice=None,
        turn_id="teach-1",
        last_user_text="tutor_unit",
        emit_token_delta=True,
    )
    with patch(
        "app.api.routes.ws.handle_turn",
        new_callable=AsyncMock,
        return_value=teach,
    ):
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {"kind": "turn_request", "text": "tutor_unit", "turn_id": "teach-1"}
            )
            delta = ws.receive_json()
            complete = ws.receive_json()
    assert delta == {
        "kind": "token_delta",
        "text": "Разберём unit ef4-beg-sb/1A",
        "turn_id": "teach-1",
    }
    assert complete["kind"] == "turn_complete"
    assert complete["message"] == teach.message
    assert complete["ctas"] == []
    assert complete["turn_id"] == "teach-1"


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
    assert event["message"] == BLANK_INPUT
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


def test_second_ws_conflict_while_first_open(client: TestClient) -> None:
    with patch(
        "app.router.turn.write_turn_snapshot",
        new_callable=AsyncMock,
        return_value={},
    ):
        with client.websocket_connect("/ws") as first:
            with client.websocket_connect("/ws") as second:
                conflict = second.receive_json()
                assert conflict["kind"] == "error"
                assert conflict["code"] == "ws_already_open"
                assert "message" in conflict
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    second.receive_json()
                assert exc_info.value.code == ws_mod.WS_ALREADY_OPEN_CLOSE_CODE
            first.send_json({"kind": "turn_request", "text": " "})
            event = first.receive_json()
            assert event["kind"] == "turn_complete"
        # Rejectee never held occupancy — a new client can claim after first closes.
        with client.websocket_connect("/ws") as third:
            third.send_json({"kind": "turn_request", "text": " "})
            again = third.receive_json()
            assert again["kind"] == "turn_complete"


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
        return_value=ClassifyResult(intent=None, band="unknown", used_backup=True),
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
    assert event["message"] == UNKNOWN_INTENT
    assert BACKUP_NOTICE not in event["message"]


def test_aput_fail_no_turn_complete(client: TestClient) -> None:
    with patch(
        "app.router.turn.classify_turn",
        new_callable=AsyncMock,
        return_value=ClassifyResult(intent=None, band="unknown", used_backup=False),
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


def test_parse_inbound_uses_turn_request_model() -> None:
    with patch.object(
        ws_mod.TurnRequest,
        "model_validate",
        wraps=ws_mod.TurnRequest.model_validate,
    ) as validate:
        result = ws_mod._parse_inbound(
            '{"kind":"turn_request","text":"hi","turn_id":"t"}'
        )
    validate.assert_called_once()
    assert result == ("hi", "t")


def test_over_limit_text_rejected_without_llm(client: TestClient) -> None:
    over = "x" * (MAX_TURN_TEXT_LENGTH + 1)
    with patch("app.api.routes.ws.handle_turn", new_callable=AsyncMock) as mocked:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"kind": "turn_request", "text": over, "turn_id": "too-long"})
            event = ws.receive_json()
    mocked.assert_not_awaited()
    assert event["kind"] == "error"
    assert event["code"] == "invalid_turn_request"
    assert event["turn_id"] == "too-long"


def test_at_limit_text_follows_turn_path(client: TestClient) -> None:
    at_limit = "y" * MAX_TURN_TEXT_LENGTH
    with patch(
        "app.api.routes.ws.handle_turn",
        new_callable=AsyncMock,
        return_value=_cta_success(turn_id="at-limit"),
    ) as mocked:
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "kind": "turn_request",
                    "text": at_limit,
                    "turn_id": "at-limit",
                }
            )
            event = ws.receive_json()
    mocked.assert_awaited_once()
    assert mocked.await_args is not None
    assert mocked.await_args.args[0] == at_limit
    assert event["kind"] == "turn_complete"
    assert event["turn_id"] == "at-limit"


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
    assert result.message == BLANK_INPUT


def test_disconnect_mid_turn_cancels_without_snapshot(client: TestClient) -> None:
    """Client disconnect mid-LLM → abandon; no turn_complete; no snapshot write."""
    started = asyncio.Event()
    release = asyncio.Event()
    write = AsyncMock(return_value={})

    async def slow_classify(*_a: object, **_k: object) -> ClassifyResult:
        started.set()
        await release.wait()
        return ClassifyResult(intent=None, band="unknown", used_backup=False)

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


def test_abnormal_cleanup_releases_only_after_inflight_settled() -> None:
    """finally-equivalent cleanup must not clear occupancy while in_flight runs."""

    async def run() -> None:
        ws_mod.reset_ws_gate_for_tests()
        assert await ws_mod._try_claim_ws()

        started = asyncio.Event()
        hold = asyncio.Event()

        async def slow_turn(
            *_a: object, turn_id: str | None = None, **_k: object
        ) -> TurnSuccess:
            started.set()
            await hold.wait()
            return _cta_success(turn_id=turn_id)

        in_flight = asyncio.create_task(slow_turn("hi", turn_id="t-abn"))
        await started.wait()

        release_while_unfinished = False
        real_release = ws_mod._release_ws

        async def tracked_release() -> None:
            nonlocal release_while_unfinished
            if not in_flight.done():
                release_while_unfinished = True
            await real_release()

        with patch.object(ws_mod, "_release_ws", tracked_release):
            await ws_mod._drain_inflight(in_flight, reason="abnormal")
            await ws_mod._release_ws()

        assert in_flight.done()
        assert release_while_unfinished is False
        # Gate free only after drain+release — a new claim succeeds.
        assert await ws_mod._try_claim_ws()

    asyncio.run(run())


def test_second_claim_blocked_until_abnormal_drain_finishes() -> None:
    """Second /ws claim stays rejected until canceled in-flight turn settles."""

    async def run() -> None:
        ws_mod.reset_ws_gate_for_tests()
        assert await ws_mod._try_claim_ws()

        started = asyncio.Event()

        async def sticky_turn(
            *_a: object, turn_id: str | None = None, **_k: object
        ) -> TurnSuccess:
            started.set()
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                await asyncio.sleep(0.05)
                raise
            return _cta_success(turn_id=turn_id)

        in_flight = asyncio.create_task(sticky_turn("hi", turn_id="t-hold"))
        await started.wait()

        cleanup = asyncio.create_task(
            _abnormal_cleanup_then_release(in_flight),
        )
        # While drain awaits the sticky cancel path, occupancy must stay held.
        await asyncio.sleep(0)
        assert not await ws_mod._try_claim_ws()
        await cleanup
        assert in_flight.done()
        assert await ws_mod._try_claim_ws()

    asyncio.run(run())


async def _abnormal_cleanup_then_release(
    in_flight: asyncio.Task[TurnSuccess | TurnError],
) -> None:
    await ws_mod._drain_inflight(in_flight, reason="abnormal")
    await ws_mod._release_ws()


def test_drain_noop_when_inflight_unset_still_allows_release() -> None:
    async def run() -> None:
        ws_mod.reset_ws_gate_for_tests()
        assert await ws_mod._try_claim_ws()
        await ws_mod._drain_inflight(None, reason="abnormal")
        await ws_mod._release_ws()
        assert await ws_mod._try_claim_ws()

    asyncio.run(run())


def test_outer_cancel_mid_drain_still_awaits_inflight() -> None:
    """Handler cancel during drain must not release until in_flight is done."""

    async def run() -> None:
        ws_mod.reset_ws_gate_for_tests()
        assert await ws_mod._try_claim_ws()

        started = asyncio.Event()

        async def sticky_turn(
            *_a: object, turn_id: str | None = None, **_k: object
        ) -> TurnSuccess:
            started.set()
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                await asyncio.sleep(0.08)
                raise
            return _cta_success(turn_id=turn_id)

        in_flight = asyncio.create_task(sticky_turn("hi", turn_id="t-mid"))
        await started.wait()

        release_while_unfinished = False
        real_release = ws_mod._release_ws

        async def tracked_release() -> None:
            nonlocal release_while_unfinished
            if not in_flight.done():
                release_while_unfinished = True
            await real_release()

        async def cleanup() -> None:
            with patch.object(ws_mod, "_release_ws", tracked_release):
                await ws_mod._drain_inflight(in_flight, reason="abnormal")
                await ws_mod._release_ws()

        cleanup_task = asyncio.create_task(cleanup())
        await asyncio.sleep(0)
        cleanup_task.cancel()
        # Drain swallows CancelledError so release can run; task may finish normally.
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        assert in_flight.done()
        assert release_while_unfinished is False
        assert await ws_mod._try_claim_ws()

    asyncio.run(run())


def test_learner_ws_cancel_drains_before_release() -> None:
    """Cancel of learner_ws with a live turn drains in_flight before the gate opens."""

    async def run() -> None:
        import json

        from starlette.websockets import WebSocketState

        ws_mod.reset_ws_gate_for_tests()
        started = asyncio.Event()
        receive_n = 0
        live_turn: asyncio.Task[TurnSuccess] | None = None
        release_while_unfinished = False
        real_release = ws_mod._release_ws

        async def sticky_turn(
            *_a: object, turn_id: str | None = None, **_k: object
        ) -> TurnSuccess:
            nonlocal live_turn
            live_turn = asyncio.current_task()  # type: ignore[assignment]
            started.set()
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                await asyncio.sleep(0.05)
                raise
            return _cta_success(turn_id=turn_id)

        async def tracked_release() -> None:
            nonlocal release_while_unfinished
            if live_turn is not None and not live_turn.done():
                release_while_unfinished = True
            await real_release()

        async def fake_receive() -> dict[str, object]:
            nonlocal receive_n
            receive_n += 1
            if receive_n == 1:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps(
                        {
                            "kind": "turn_request",
                            "text": "hello",
                            "turn_id": "t-h",
                        }
                    ),
                }
            await asyncio.Event().wait()
            return {"type": "websocket.disconnect"}

        fake_ws = AsyncMock()
        fake_ws.accept = AsyncMock()
        fake_ws.receive = fake_receive
        fake_ws.send_json = AsyncMock()
        fake_ws.close = AsyncMock()
        fake_ws.client_state = WebSocketState.CONNECTED
        fake_ws.application_state = WebSocketState.CONNECTED

        with (
            patch("app.api.routes.ws.handle_turn", side_effect=sticky_turn),
            patch.object(ws_mod, "_release_ws", tracked_release),
        ):
            handler = asyncio.create_task(ws_mod.learner_ws(fake_ws))
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert started.is_set()
            assert not await ws_mod._try_claim_ws()
            handler.cancel()
            with pytest.raises(asyncio.CancelledError):
                await handler
        assert live_turn is not None and live_turn.done()
        assert release_while_unfinished is False
        assert await ws_mod._try_claim_ws()

    asyncio.run(run())


def test_learner_ws_close_disconnect_still_drains_and_releases() -> None:
    """WebSocketDisconnect from close() must not skip drain or occupancy release."""

    async def run() -> None:
        import json

        from starlette.websockets import WebSocketState

        ws_mod.reset_ws_gate_for_tests()
        started = asyncio.Event()
        receive_n = 0

        async def sticky_turn(
            *_a: object, turn_id: str | None = None, **_k: object
        ) -> TurnSuccess:
            started.set()
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                await asyncio.sleep(0.02)
                raise
            return _cta_success(turn_id=turn_id)

        async def fake_receive() -> dict[str, object]:
            nonlocal receive_n
            receive_n += 1
            if receive_n == 1:
                return {
                    "type": "websocket.receive",
                    "text": json.dumps(
                        {
                            "kind": "turn_request",
                            "text": "hello",
                            "turn_id": "t-close",
                        }
                    ),
                }
            await asyncio.Event().wait()
            return {"type": "websocket.disconnect"}

        fake_ws = AsyncMock()
        fake_ws.accept = AsyncMock()
        fake_ws.receive = fake_receive
        fake_ws.send_json = AsyncMock()
        fake_ws.close = AsyncMock(side_effect=WebSocketDisconnect())
        fake_ws.client_state = WebSocketState.CONNECTED
        fake_ws.application_state = WebSocketState.CONNECTED

        with patch("app.api.routes.ws.handle_turn", side_effect=sticky_turn):
            handler = asyncio.create_task(ws_mod.learner_ws(fake_ws))
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert started.is_set()
            handler.cancel()
            with pytest.raises(asyncio.CancelledError):
                await handler
        assert await ws_mod._try_claim_ws()

    asyncio.run(run())
