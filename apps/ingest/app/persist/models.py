"""Ingest-local ORM mirror of api corpus tables (0003). Never import apps.api."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

UNIT_STATUSES = ("Ready", "NotReady", "Review")
EMBEDDING_DIMS = 1024


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Textbook(Base):
    __tablename__ = "textbook"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()


class TextbookUnit(Base):
    __tablename__ = "textbook_unit"
    __table_args__ = (UniqueConstraint("unit_ref"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
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
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Chunk(Base):
    __tablename__ = "chunk"

    id: Mapped[uuid.UUID] = _uuid_pk()
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("textbook_unit.id"))
    textbook_id: Mapped[str] = mapped_column(Text)
    unit_ref: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)


class Embedding(Base):
    __tablename__ = "embedding"
    __table_args__ = (
        UniqueConstraint("chunk_id"),
        CheckConstraint(f"dims = {EMBEDDING_DIMS}", name="embedding_dims_check"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunk.id"))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS))
    model_name: Mapped[str] = mapped_column(Text)
    dims: Mapped[int] = mapped_column(Integer)
