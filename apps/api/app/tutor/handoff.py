"""Tutor handoff: CEFR → unit resolve / refuse precedence → teach or empty-rag.

Path→type producer map for story 5 (this module does not append ErrorLog):
teaching ← no-ready|workbook-only|null-unit; RAG ← ready-loss; off-unit ← off-unit;
empty-rag ← story 1; mid-session → type of the branch taken.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.corpus.query import get_ready_unit_chunks
from app.mixins.cefr import read_overall_cefr
from app.schemas.cefr import CefrLevel
from app.tutor.bind import UnitKind, classify_unit_ref, first_ready_sb_unit_ref
from app.tutor.copy import (
    CEFR_MISSING,
    EMPTY_RAG,
    NO_READY,
    NULL_UNIT,
    OFF_UNIT,
    READY_LOSS,
    UNIT_CHANGE_CONFIRM,
    WORKBOOK_ONLY,
)
from app.tutor.teach import compose_teach_message

AGENT_CTAS: Final = ("tutor", "vocabulary", "review")
CEFR_GATE_CTAS: Final = ("cefr", "vocabulary", "review")
UNIT_CHANGE_CTAS: Final = ("confirm_unit", "decline_unit")

# Sentinel: request omitted ``unit_ref`` (distinct from JSON null clear).
UNSET: Final = object()

CONFIRM_UNIT: Final = "confirm_unit"
DECLINE_UNIT: Final = "decline_unit"
_ON_PATH_TEXTS: Final = frozenset(
    {
        "tutor_unit",
        "tutor",
        CONFIRM_UNIT,
        DECLINE_UNIT,
    }
)
_TOKEN_RE: Final = re.compile(r"\w+", re.UNICODE)

# Refuse precedence (Always): null-unit > no-ready|workbook-only > ready-loss > off-unit
_PRECEDENCE: Final = (
    "null-unit",
    "no-ready",
    "workbook-only",
    "ready-loss",
    "off-unit",
)


@dataclass(frozen=True, slots=True)
class TutorOutcome:
    message: str
    ctas: tuple[str, ...]
    session_patch: dict[str, Any]
    active_agent: str | None
    emit_token_delta: bool
    # True when this turn attempted a mid-session unit chrome switch (persist-fail RU).
    unit_switch_attempt: bool = False


def pick_refuse_key(flags: Mapping[str, bool]) -> str | None:
    """Return the single refuse key for true flags under Always precedence."""
    for key in _PRECEDENCE:
        if flags.get(key):
            return key
    return None


def content_tokens(text: str) -> frozenset[str]:
    return frozenset(_TOKEN_RE.findall(text.casefold()))


def is_off_unit_text(text: str, chunk_texts: list[str]) -> bool:
    """True when free text has no casefold content-token overlap with Ready chunks."""
    stripped = text.strip()
    if not stripped or stripped.casefold() in _ON_PATH_TEXTS:
        return False
    text_toks = content_tokens(stripped)
    if not text_toks:
        return False
    chunk_toks: set[str] = set()
    for chunk in chunk_texts:
        chunk_toks.update(content_tokens(chunk))
    return text_toks.isdisjoint(chunk_toks)


def _tutor_patch(
    *,
    active_unit_ref: str | None = None,
    pending_unit_ref: str | None = None,
    include_pending: bool = False,
) -> dict[str, Any]:
    tutor: dict[str, Any] = {}
    if active_unit_ref is not None:
        tutor["active_unit_ref"] = active_unit_ref
    if include_pending and pending_unit_ref is not None:
        tutor["pending_unit_ref"] = pending_unit_ref
    return {"tutor": tutor}


def _refuse(
    message: str,
    *,
    patch: dict[str, Any] | None = None,
    ctas: tuple[str, ...] = AGENT_CTAS,
    active_agent: str | None = None,
    unit_switch_attempt: bool = False,
) -> TutorOutcome:
    return TutorOutcome(
        message=message,
        ctas=ctas,
        session_patch=patch if patch is not None else {},
        active_agent=active_agent,
        emit_token_delta=False,
        unit_switch_attempt=unit_switch_attempt,
    )


def _kind_to_refuse_message(kind: UnitKind) -> str | None:
    if kind in ("null", "unknown"):
        return NULL_UNIT
    if kind == "workbook":
        return WORKBOOK_ONLY
    if kind == "sb_non_ready":
        return NO_READY
    return None


async def _teach_or_empty(
    session: AsyncSession,
    unit_ref: str,
    *,
    overall: CefrLevel,
    text: str,
    check_off_unit: bool,
) -> TutorOutcome:
    corpus = await get_ready_unit_chunks(session, unit_ref)
    if corpus is None:
        return _refuse(
            EMPTY_RAG,
            patch=_tutor_patch(active_unit_ref=unit_ref),
            active_agent="Tutor",
        )
    if check_off_unit and is_off_unit_text(
        text, [c.content for c in corpus.chunks]
    ):
        return _refuse(
            OFF_UNIT,
            patch=_tutor_patch(active_unit_ref=unit_ref),
            active_agent="Tutor",
        )
    return TutorOutcome(
        message=await compose_teach_message(corpus, overall),
        ctas=(),
        session_patch=_tutor_patch(active_unit_ref=unit_ref),
        active_agent="Tutor",
        emit_token_delta=True,
    )


async def _ready_loss_or_teach(
    session: AsyncSession,
    unit_ref: str,
    *,
    overall: CefrLevel,
    text: str,
    had_active_session: bool,
) -> TutorOutcome:
    kind = await classify_unit_ref(session, unit_ref)
    if kind == "sb_ready":
        return await _teach_or_empty(
            session,
            unit_ref,
            overall=overall,
            text=text,
            check_off_unit=had_active_session,
        )
    if had_active_session and kind == "sb_non_ready":
        # Current STM unit lost Ready (not chrome switch-away).
        return _refuse(
            READY_LOSS,
            patch=_tutor_patch(active_unit_ref=unit_ref),
            active_agent="Tutor",
        )
    msg = _kind_to_refuse_message(kind)
    assert msg is not None
    return _refuse(msg)


async def handle_tutor(
    session: AsyncSession,
    *,
    text: str = "",
    prior_tutor: Mapping[str, Any] | None = None,
    request_unit_ref: Any = UNSET,
) -> TutorOutcome:
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

    prior = dict(prior_tutor) if prior_tutor else {}
    active = prior.get("active_unit_ref")
    active_ref = active if isinstance(active, str) and active.strip() else None
    pending_raw = prior.get("pending_unit_ref")
    pending_ref = (
        pending_raw if isinstance(pending_raw, str) and pending_raw.strip() else None
    )
    key = text.strip().casefold()
    chrome = request_unit_ref is not UNSET

    # confirm / decline short-circuit (pending Ready→Ready change).
    if key == CONFIRM_UNIT and pending_ref:
        kind = await classify_unit_ref(session, pending_ref)
        if kind != "sb_ready":
            msg = _kind_to_refuse_message(kind) or NO_READY
            return _refuse(msg, patch=_tutor_patch(active_unit_ref=active_ref))
        return await _teach_or_empty(
            session,
            pending_ref,
            overall=overall,
            text=text,
            check_off_unit=False,
        )
    if key == DECLINE_UNIT:
        if active_ref is None:
            return _refuse(NULL_UNIT)
        return await _teach_or_empty(
            session,
            active_ref,
            overall=overall,
            text=text,
            check_off_unit=False,
        )

    # Mid-session chrome change: finish this turn's branch; never RAG on stale unit.
    if chrome:
        proposed: str | None
        if request_unit_ref is None:
            proposed = None
        elif isinstance(request_unit_ref, str):
            proposed = request_unit_ref.strip() or None
        else:
            proposed = None
        kind = await classify_unit_ref(session, proposed)
        switch = active_ref is not None

        if kind in ("null", "unknown"):
            return _refuse(
                NULL_UNIT,
                patch={"tutor": {}},
                unit_switch_attempt=switch,
            )
        if kind == "workbook":
            return _refuse(
                WORKBOOK_ONLY,
                patch=_tutor_patch(active_unit_ref=active_ref)
                if active_ref
                else {},
                unit_switch_attempt=switch,
            )
        if kind == "sb_non_ready":
            return _refuse(
                NO_READY,
                patch=_tutor_patch(active_unit_ref=active_ref)
                if active_ref
                else {},
                unit_switch_attempt=switch,
            )
        # Ready SB
        assert proposed is not None
        if switch and proposed != active_ref:
            return _refuse(
                UNIT_CHANGE_CONFIRM,
                patch=_tutor_patch(
                    active_unit_ref=active_ref,
                    pending_unit_ref=proposed,
                    include_pending=True,
                ),
                ctas=UNIT_CHANGE_CTAS,
                active_agent="Tutor",
                unit_switch_attempt=True,
            )
        # Cold explicit Ready chrome, or re-select same Ready unit.
        return await _teach_or_empty(
            session,
            proposed,
            overall=overall,
            text=text,
            check_off_unit=False,
        )

    # No request unit_ref: pending|STM active|cold auto-bind.
    if active_ref is not None:
        return await _ready_loss_or_teach(
            session,
            active_ref,
            overall=overall,
            text=text,
            had_active_session=True,
        )

    unit_ref = await first_ready_sb_unit_ref(session)
    if unit_ref is None:
        return _refuse(NO_READY)

    return await _teach_or_empty(
        session,
        unit_ref,
        overall=overall,
        text=text,
        check_off_unit=False,
    )
