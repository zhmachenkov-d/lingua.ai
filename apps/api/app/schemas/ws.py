"""AD-6 WebSocket turn envelopes (field extras; kinds are closed)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TurnRequestKind = Literal["turn_request"]
ServerEventKind = Literal["token_delta", "turn_complete", "error"]
ErrorCode = Literal[
    "llm_misconfigured",
    "llm_unavailable",
    "invalid_turn_request",
    "checkpointer_write_failed",
]


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: TurnRequestKind
    text: str
    turn_id: str | None = None


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
