"""Lex-min Ready Students' Book ``unit_ref`` auto-bind (Party C-Ord1)."""

from __future__ import annotations

from lingua_ids import EF4_BEG_SB_ID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.textbook_unit import TextbookUnit


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
