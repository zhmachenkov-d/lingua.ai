"""Replaceable Review stub — namespaced session_patch only (no LTM/FSRS)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

STUB_MESSAGE: Final = "Review пока в подготовке."


@dataclass(frozen=True, slots=True)
class ReviewStubOutcome:
    message: str
    session_patch: dict[str, Any]
    active_agent: str


def handle_review_stub() -> ReviewStubOutcome:
    """No-op Review handoff: honest RU pending + empty namespaced patch."""
    return ReviewStubOutcome(
        message=STUB_MESSAGE,
        session_patch={"review": {}},
        active_agent="Review",
    )
