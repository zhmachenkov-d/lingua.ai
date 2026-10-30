"""AD-6 WebSocket turn envelopes (field extras; kinds are closed)."""

from __future__ import annotations

import json
from pathlib import Path
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
    "lexicon_unavailable",
]

_SOT_NAME = "max-turn-text-length.json"


def _sot_candidates(here: Path) -> list[Path]:
    """Resolve SoT paths without indexing past Path.parents (Docker /app is shallow)."""
    parents = here.parents
    out: list[Path] = []
    # Monorepo: apps/api/app/schemas → repo root (needs parents[4])
    if len(parents) > 4:
        out.append(parents[4] / "apps" / "web" / "src" / "app" / "chat" / _SOT_NAME)
    # Api image: /app/app/schemas → /app/contracts (needs parents[2])
    if len(parents) > 2:
        out.append(parents[2] / "contracts" / _SOT_NAME)
    return out


def _load_max_turn_text_length() -> int:
    """Load shared SoT (web chat JSON; Docker copies it under /app/contracts)."""
    here = Path(__file__).resolve()
    candidates = _sot_candidates(here)
    for path in candidates:
        if not path.is_file():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        value = raw["maxTurnTextLength"]
        if type(value) is not int:
            raise TypeError(
                "maxTurnTextLength in "
                f"{path} must be an int, got {type(value).__name__}"
            )
        return value
    raise FileNotFoundError(
        f"{_SOT_NAME} not found; tried: "
        + (", ".join(str(p) for p in candidates) if candidates else "(none)")
    )


MAX_TURN_TEXT_LENGTH = _load_max_turn_text_length()


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
    # Present (incl. JSON null) is authoritative chrome; omit = no chrome change.
    unit_ref: str | None = None


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
    """AD-6 streaming delta — emitted on Tutor teach before ``turn_complete``."""

    kind: Literal["token_delta"] = "token_delta"
    text: str = Field(default="")
    turn_id: str | None = None

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "text": self.text,
        }
        if self.turn_id is not None:
            payload["turn_id"] = self.turn_id
        return payload
