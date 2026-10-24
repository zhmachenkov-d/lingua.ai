import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class ErrorLog(Base):
    """LTM — D5 §5.4. Append-only; Tutor / Vocabulary / Review may append (AD-4)."""

    __tablename__ = "error_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learner_profile.id"))
    error_type: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    vocab_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vocabulary_item.id")
    )
    rule_id: Mapped[str | None] = mapped_column(Text)
    # Optional trace to the non-authoritative Session mirror; not STM SoT.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("session.id", ondelete="SET NULL")
    )
    unit_ref: Mapped[str | None] = mapped_column(Text)
    count_7d: Mapped[int | None] = mapped_column(Integer)
