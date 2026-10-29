"""Replaceable Vocabulary stub — namespaced session_patch only (no LTM/FSRS)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

STUB_MESSAGE: Final = "Vocabulary пока в подготовке."


@dataclass(frozen=True, slots=True)
class VocabularyStubOutcome:
    message: str
    session_patch: dict[str, Any]
    active_agent: str


def handle_vocabulary_stub() -> VocabularyStubOutcome:
    """No-op Vocab handoff: honest RU pending + empty namespaced patch."""
    return VocabularyStubOutcome(
        message=STUB_MESSAGE,
        session_patch={"vocabulary": {}},
        active_agent="Vocabulary",
    )
