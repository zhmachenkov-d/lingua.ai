"""Corpus Ready / embedding ORM — single SoT for api and ingest."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from lingua_ids import EMBEDDING_DIMS
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from lingua_corpus.base import Base, created_at_col, updated_at_col, uuid_pk

UNIT_STATUSES = ("Ready", "NotReady", "Review")

__all__ = [
    "EMBEDDING_DIMS",
    "UNIT_STATUSES",
    "Chunk",
    "Embedding",
    "Textbook",
    "TextbookUnit",
]


class Textbook(Base):
    """Corpus catalog — textbook identity (AD-11). Ingest is the sole writer."""

    __tablename__ = "textbook"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()


class TextbookUnit(Base):
    """Corpus Ready gate row — status + auditable gate_metrics (R4).

    Ingest is the sole writer; api owns schema / Alembic only.
    """

    __tablename__ = "textbook_unit"
    __table_args__ = (UniqueConstraint("unit_ref"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    textbook_id: Mapped[str] = mapped_column(Text, ForeignKey("textbook.id"))
    unit_ref: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Enum(
            *UNIT_STATUSES,
            name="textbook_unit_status",
            native_enum=False,
            create_constraint=True,
        )
    )
    gate_reason: Mapped[str | None] = mapped_column(Text)
    gate_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Chunk(Base):
    """RAG chunk belonging to a TextbookUnit. Ingest is the sole writer."""

    __tablename__ = "chunk"

    id: Mapped[uuid.UUID] = uuid_pk()
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("textbook_unit.id"))
    textbook_id: Mapped[str] = mapped_column(Text)
    unit_ref: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)


class Embedding(Base):
    """pgvector embedding for a chunk (dims stamped; AD-12). Ingest sole writer."""

    __tablename__ = "embedding"
    __table_args__ = (
        UniqueConstraint("chunk_id"),
        CheckConstraint(f"dims = {EMBEDDING_DIMS}", name="embedding_dims_check"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunk.id"))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))
    model_name: Mapped[str] = mapped_column(Text)
    dims: Mapped[int] = mapped_column(Integer)
