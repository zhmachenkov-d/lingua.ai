import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk

RATINGS = ("Again", "Hard", "Good", "Easy")
DRILL_MODALITIES = (
    "translate_en_ru",
    "translate_ru_en",
    "match",
    "write",
    "cloze",
    "listen_and_spell",
)


class ReviewRecord(Base):
    """LTM — D5 §5.7. Append-only event log (AD-4); not a schedule store."""

    __tablename__ = "review_record"

    id: Mapped[uuid.UUID] = uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learner_profile.id"))
    vocab_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vocabulary_item.id"))
    rating: Mapped[str] = mapped_column(
        Enum(
            *RATINGS,
            name="review_record_rating",
            native_enum=False,
            create_constraint=True,
        )
    )
    success: Mapped[bool] = mapped_column(Boolean)
    drill_modality: Mapped[str] = mapped_column(
        Enum(
            *DRILL_MODALITIES,
            name="review_record_drill_modality",
            native_enum=False,
            create_constraint=True,
        )
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Optional trace to the non-authoritative Session mirror; not STM SoT.
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("session.id", ondelete="SET NULL")
    )
    error_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("error_log.id"))
    stability_after: Mapped[float | None] = mapped_column(Float)
    difficulty_after: Mapped[float | None] = mapped_column(Float)
    next_review_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
