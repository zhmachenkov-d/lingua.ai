"""Tutor handoff: CEFR gate → lex-min SB bind → teach or empty-rag / no-ready."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.corpus.query import get_ready_unit_chunks
from app.tutor.bind import first_ready_sb_unit_ref
from app.tutor.cefr_gate import read_overall_cefr
from app.tutor.copy import CEFR_MISSING, EMPTY_RAG, NO_READY
from app.tutor.teach import grounded_teach_message

AGENT_CTAS: Final = ("tutor", "vocabulary", "review")
CEFR_GATE_CTAS: Final = ("cefr", "vocabulary", "review")


@dataclass(frozen=True, slots=True)
class TutorOutcome:
    message: str
    ctas: tuple[str, ...]
    session_patch: dict[str, Any]
    active_agent: str | None
    emit_token_delta: bool


async def handle_tutor(session: AsyncSession) -> TutorOutcome:
    """Run Ready Tutor path. Returns namespaced patch only — Router owns ``aput``."""
    overall = await read_overall_cefr(session)
    if overall is None:
        return TutorOutcome(
            message=CEFR_MISSING,
            ctas=CEFR_GATE_CTAS,
            session_patch={},
            active_agent=None,
            emit_token_delta=False,
        )

    unit_ref = await first_ready_sb_unit_ref(session)
    if unit_ref is None:
        return TutorOutcome(
            message=NO_READY,
            ctas=AGENT_CTAS,
            session_patch={},
            active_agent=None,
            emit_token_delta=False,
        )

    patch: dict[str, Any] = {"tutor": {"active_unit_ref": unit_ref}}
    corpus = await get_ready_unit_chunks(session, unit_ref)
    if corpus is None:
        return TutorOutcome(
            message=EMPTY_RAG,
            ctas=AGENT_CTAS,
            session_patch=patch,
            active_agent="Tutor",
            emit_token_delta=False,
        )

    return TutorOutcome(
        message=grounded_teach_message(corpus),
        ctas=(),
        session_patch=patch,
        active_agent="Tutor",
        emit_token_delta=True,
    )
