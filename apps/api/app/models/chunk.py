import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class Chunk(Base):
    """RAG chunk belonging to a TextbookUnit. Ingest is the sole writer."""

    __tablename__ = "chunk"

    id: Mapped[uuid.UUID] = uuid_pk()
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("textbook_unit.id"))
    textbook_id: Mapped[str] = mapped_column(Text)
    unit_ref: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
