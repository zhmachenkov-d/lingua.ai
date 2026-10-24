import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, updated_at_col, uuid_pk

SOURCES = ("textbook", "lexicon")
LEXICON_PROVIDERS = ("free_dictionary", "oxford")
STATUSES = ("Unseen", "Learning", "Review", "Mastered")


class VocabularyItem(Base):
    """LTM — D5 §5.3. Owned by Vocabulary (AD-4).

    The FSRS schedule fields (difficulty, stability, next_review, optional
    retrievability) live here and are the only schedule store; no parallel
    schedule table. The FSRS adapter is a later story.
    """

    __tablename__ = "vocabulary_item"
    __table_args__ = (UniqueConstraint("learner_id", "lemma"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learner_profile.id"))
    lemma: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(
        Enum(*SOURCES, name="vocabulary_item_source", native_enum=False, create_constraint=True)
    )
    lexicon_provider: Mapped[str | None] = mapped_column(
        Enum(
            *LEXICON_PROVIDERS,
            name="vocabulary_item_lexicon_provider",
            native_enum=False, create_constraint=True,
        )
    )
    textbook_id: Mapped[str | None] = mapped_column(Text)
    unit_ref: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Enum(*STATUSES, name="vocabulary_item_status", native_enum=False, create_constraint=True)
    )
    # FSRS schedule fields. difficulty/stability are NULL until first scheduled
    # (py-fsrs Card starts with None); next_review maps to Card.due.
    difficulty: Mapped[float | None] = mapped_column(Float)
    stability: Mapped[float | None] = mapped_column(Float)
    next_review: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    retrievability: Mapped[float | None] = mapped_column(Float)
    learned: Mapped[bool] = mapped_column(Boolean, server_default=false())
    learned_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
