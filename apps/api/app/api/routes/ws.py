"""Single learner WebSocket entry via Router (AD-6). Unauthenticated MVP singleton."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.router.turn import ERROR_MESSAGES, TurnError, TurnSuccess, handle_turn
from app.schemas.ws import ErrorEvent, TurnCompleteEvent

router = APIRouter(tags=["ws"])

# Align with apps/web MAX_MESSAGE_LENGTH (chat.copy.ts).
MAX_TURN_TEXT_LENGTH = 2000

# At most one active /ws for the MVP learner (C2).
_ws_lock = asyncio.Lock()
_ws_occupied = False


async def _try_claim_ws() -> bool:
    global _ws_occupied
    async with _ws_lock:
        if _ws_occupied:
            return False
        _ws_occupied = True
        return True


async def _release_ws() -> None:
    global _ws_occupied
    async with _ws_lock:
        _ws_occupied = False


async def _reject_conflict(websocket: WebSocket) -> None:
    """Deny the upgrade with HTTP 409 before accept (ASGI websocket denial)."""
    await websocket.send(
        {"type": "websocket.http.response.start", "status": 409, "headers": []}
    )
    await websocket.send(
        {
            "type": "websocket.http.response.body",
            "body": b"Conflict: MVP learner WebSocket already open",
            "more_body": False,
        }
    )


def _parse_turn_id(raw: object) -> str | None:
    if isinstance(raw, str):
        return raw
    return None


def _invalid_error(*, turn_id: str | None) -> dict[str, Any]:
    return ErrorEvent(
        message=ERROR_MESSAGES["invalid_turn_request"],
        code="invalid_turn_request",
        turn_id=turn_id,
    ).to_wire()


def _parse_inbound(raw_text: str) -> tuple[str, str | None] | dict[str, Any]:
    """Return (text, turn_id) or an error wire payload."""
    turn_id: str | None = None
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return _invalid_error(turn_id=None)
    if not isinstance(data, dict):
        return _invalid_error(turn_id=None)
    turn_id = _parse_turn_id(data.get("turn_id"))
    if data.get("kind") != "turn_request":
        return _invalid_error(turn_id=turn_id)
    text = data.get("text")
    if not isinstance(text, str):
        return _invalid_error(turn_id=turn_id)
    if len(text) > MAX_TURN_TEXT_LENGTH:
        return _invalid_error(turn_id=turn_id)
    return text, turn_id


def _success_wire(result: TurnSuccess) -> dict[str, Any]:
    return TurnCompleteEvent(
        message=result.message,
        ctas=list(result.ctas),
        clarify=None,
        backup_notice=result.backup_notice,
        turn_id=result.turn_id,
    ).to_wire()


def _error_wire(result: TurnError) -> dict[str, Any]:
    return ErrorEvent(
        message=result.message,
        code=result.code,
        turn_id=result.turn_id,
    ).to_wire()


def _unexpected_error(*, turn_id: str | None) -> dict[str, Any]:
    return ErrorEvent(
        message=ERROR_MESSAGES["llm_unavailable"],
        code="llm_unavailable",
        turn_id=turn_id,
    ).to_wire()


async def _deliver_finished(
    websocket: WebSocket,
    task: asyncio.Task[TurnSuccess | TurnError],
    *,
    turn_id: str | None,
) -> None:
    """Send wire event for a completed turn task. Never discard the result."""
    try:
        result = task.result()
    except asyncio.CancelledError:
        raise
    except Exception:
        await websocket.send_json(_unexpected_error(turn_id=turn_id))
        return
    if isinstance(result, TurnError):
        await websocket.send_json(_error_wire(result))
    else:
        await websocket.send_json(_success_wire(result))


@router.websocket("/ws")
async def learner_ws(websocket: WebSocket) -> None:
    if not await _try_claim_ws():
        await _reject_conflict(websocket)
        return

    # Claim held until finally — even if accept() or early setup fails.
    in_flight: asyncio.Task[TurnSuccess | TurnError] | None = None
    in_flight_turn_id: str | None = None
    receive_task: asyncio.Task[Any] | None = None
    try:
        await websocket.accept()
        receive_task = asyncio.create_task(websocket.receive())

        while True:
            assert receive_task is not None
            wait_set: set[asyncio.Task[Any]] = {receive_task}
            if in_flight is not None:
                wait_set.add(in_flight)

            await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

            # Deliver finished turns before handling receive / starting a new one
            # (both may complete in the same wait wake-up).
            if in_flight is not None and in_flight.done():
                try:
                    await _deliver_finished(
                        websocket, in_flight, turn_id=in_flight_turn_id
                    )
                except asyncio.CancelledError:
                    return
                in_flight = None
                in_flight_turn_id = None
                continue

            # receive_task completed (in_flight still running or absent)
            message = receive_task.result()
            receive_task = asyncio.create_task(websocket.receive())

            if message["type"] == "websocket.disconnect":
                if in_flight is not None:
                    in_flight.cancel()
                    try:
                        await in_flight
                    except asyncio.CancelledError:
                        pass
                    in_flight = None
                    in_flight_turn_id = None
                return

            if message["type"] != "websocket.receive":
                continue

            raw = message.get("text")
            if raw is None:
                await websocket.send_json(_invalid_error(turn_id=None))
                continue

            if in_flight is not None and not in_flight.done():
                parsed_preview = _parse_inbound(raw)
                overlap_turn_id: str | None = None
                if isinstance(parsed_preview, dict):
                    overlap_tid = parsed_preview.get("turn_id")
                    overlap_turn_id = (
                        overlap_tid if isinstance(overlap_tid, str) else None
                    )
                else:
                    overlap_turn_id = parsed_preview[1]
                await websocket.send_json(_invalid_error(turn_id=overlap_turn_id))
                continue

            parsed = _parse_inbound(raw)
            if isinstance(parsed, dict):
                await websocket.send_json(parsed)
                continue

            text, turn_id = parsed
            in_flight_turn_id = turn_id
            in_flight = asyncio.create_task(handle_turn(text, turn_id=turn_id))
    except WebSocketDisconnect:
        if in_flight is not None:
            in_flight.cancel()
            try:
                await in_flight
            except asyncio.CancelledError:
                pass
    finally:
        if receive_task is not None and not receive_task.done():
            receive_task.cancel()
            try:
                await receive_task
            except asyncio.CancelledError:
                pass
        if (
            websocket.client_state == WebSocketState.CONNECTED
            and websocket.application_state == WebSocketState.CONNECTED
        ):
            try:
                await websocket.close()
            except RuntimeError:
                pass
        await _release_ws()


def reset_ws_gate_for_tests() -> None:
    """Test helper: clear the singleton occupancy flag."""
    global _ws_occupied
    _ws_occupied = False
