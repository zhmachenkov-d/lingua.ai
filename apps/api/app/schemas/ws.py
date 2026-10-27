"""AD-6 WebSocket turn envelopes (field extras; kinds are closed)."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

TurnRequestKind = Literal["turn_request"]
ServerEventKind = Literal["token_delta", "turn_complete", "error"]
ErrorCode = Literal[
    "llm_misconfigured",
    "llm_unavailable",
    "invalid_turn_request",
    "checkpointer_write_failed",
    "ws_already_open",
]

# Align with apps/web MAX_MESSAGE_LENGTH (chat.copy.ts).
MAX_TURN_TEXT_LENGTH = 2000


def _coerce_optional_str(value: object) -> str | None:
    """Match hand-parser: keep string turn_id, treat anything else as absent."""
    if isinstance(value, str):
        return value
    return None


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: TurnRequestKind
    text: str = Field(max_length=MAX_TURN_TEXT_LENGTH)
    turn_id: Annotated[str | None, BeforeValidator(_coerce_optional_str)] = None


class TurnCompleteEvent(BaseModel):
    kind: Literal["turn_complete"] = "turn_complete"
    message: str
    ctas: list[str]
    clarify: None = None
    backup_notice: str | None = None
    turn_id: str | None = None

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "message": self.message,
            "ctas": list(self.ctas),
            "clarify": None,
            "backup_notice": self.backup_notice,
        }
        if self.turn_id is not None:
            payload["turn_id"] = self.turn_id
        return payload


class ErrorEvent(BaseModel):
    kind: Literal["error"] = "error"
    message: str
    code: ErrorCode
    turn_id: str | None = None

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "message": self.message,
            "code": self.code,
        }
        if self.turn_id is not None:
            payload["turn_id"] = self.turn_id
        return payload


class TokenDeltaEvent(BaseModel):
    """Reserved AD-6 kind — unused on CTA/blank skeleton paths."""

    kind: Literal["token_delta"] = "token_delta"
    text: str = Field(default="")
    turn_id: str | None = None
