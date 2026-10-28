import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk

EMBEDDING_DIMS = 1024


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
