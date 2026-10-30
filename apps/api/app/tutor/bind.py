"""Lex-min Ready SB auto-bind + ``unit_ref`` classify (Party C-Ord1 / R3)."""

from __future__ import annotations

from typing import Literal

from lingua_ids import EF4_BEG_SB_ID, EF4_BEG_WB_ID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.corpus.query import get_unit_row
from app.models.textbook_unit import TextbookUnit

UnitKind = Literal["null", "workbook", "sb_non_ready", "sb_ready", "unknown"]


async def first_ready_sb_unit_ref(session: AsyncSession) -> str | None:
    """Lexicographically minimal Ready SB ``unit_ref``, or None when none exist."""
    return await session.scalar(
        select(TextbookUnit.unit_ref)
        .where(
            TextbookUnit.textbook_id == EF4_BEG_SB_ID,
            TextbookUnit.status == "Ready",
        )
        .order_by(TextbookUnit.unit_ref.asc())
        .limit(1)
    )


def classify_unit_ref_pure(
    unit_ref: str | None,
    *,
    textbook_id: str | None,
    status: str | None,
    exists: bool,
) -> UnitKind:
    """Pure classify over inputs (Hypothesis-friendly)."""
    if unit_ref is None or not str(unit_ref).strip():
        return "null"
    ref = str(unit_ref).strip()
    tb = textbook_id
    if tb is None and "/" in ref:
        tb = ref.split("/", 1)[0]
    if (
        tb == EF4_BEG_WB_ID
        or ref == EF4_BEG_WB_ID
        or ref.startswith(f"{EF4_BEG_WB_ID}/")
    ):
        return "workbook"
    if not exists:
        return "unknown"
    if textbook_id != EF4_BEG_SB_ID:
        return "unknown"
    if status == "Ready":
        return "sb_ready"
    return "sb_non_ready"


async def classify_unit_ref(session: AsyncSession, unit_ref: str | None) -> UnitKind:
    """Classify a proposed ``unit_ref`` for Tutor refuse / bind branching."""
    if unit_ref is None or not str(unit_ref).strip():
        return "null"
    ref = str(unit_ref).strip()
    # Workbook prefix is authoritative even without a DB row.
    if ref.startswith(f"{EF4_BEG_WB_ID}/") or ref == EF4_BEG_WB_ID:
        return "workbook"
    row = await get_unit_row(session, ref)
    if row is None:
        return classify_unit_ref_pure(
            ref, textbook_id=None, status=None, exists=False
        )
    return classify_unit_ref_pure(
        ref,
        textbook_id=row.textbook_id,
        status=row.status,
        exists=True,
    )
