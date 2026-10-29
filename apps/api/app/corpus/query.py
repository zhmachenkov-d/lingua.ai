"""Ready-by-``unit_ref`` chunk + embedding reader for epic-tutor-mixins.

Call ``get_ready_unit_chunks`` with an ``AsyncSession`` and a corpus
``unit_ref``. On Ready, you get ordinal-ordered chunks whose vectors and
``model_name`` / ``dims`` stamps come from persisted ingest rows (shared
AD-12 SoT). Missing, non-Ready, or Ready-with-empty-join units yield ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.embedding import Embedding
from app.models.textbook_unit import TextbookUnit


@dataclass(frozen=True, slots=True)
class ReadyChunk:
    """One Tutor-usable chunk with its stamped dense embedding."""

    ordinal: int
    content: str
    embedding: list[float]
    model_name: str
    dims: int


@dataclass(frozen=True, slots=True)
class ReadyUnitCorpus:
    """Ready unit payload: ``unit_ref``, status, and ordered chunks."""

    unit_ref: str
    status: str
    chunks: list[ReadyChunk]


async def get_ready_unit_chunks(
    session: AsyncSession,
    unit_ref: str,
) -> ReadyUnitCorpus | None:
    """Return Ready chunks+embeddings for ``unit_ref``, else ``None``.

    Read-only against ``textbook_unit`` / ``chunk`` / ``embedding``. Does not
    raise for unknown, non-Ready, or Ready-with-empty-join refs — callers
    treat ``None`` as absence.
    """
    unit = await session.scalar(
        select(TextbookUnit).where(TextbookUnit.unit_ref == unit_ref)
    )
    if unit is None or unit.status != "Ready":
        return None

    rows = (
        await session.execute(
            select(Chunk, Embedding)
            .join(Embedding, Embedding.chunk_id == Chunk.id)
            .where(Chunk.unit_id == unit.id)
            .order_by(Chunk.ordinal.asc())
        )
    ).all()

    if not rows:
        return None

    chunks = [
        ReadyChunk(
            ordinal=chunk.ordinal,
            content=chunk.content,
            embedding=[float(x) for x in embedding.embedding],
            model_name=embedding.model_name,
            dims=int(embedding.dims),
        )
        for chunk, embedding in rows
    ]
    return ReadyUnitCorpus(unit_ref=unit.unit_ref, status="Ready", chunks=chunks)
