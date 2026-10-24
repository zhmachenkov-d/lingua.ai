import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, updated_at_col, uuid_pk


class LearnerProfile(Base):
    """LTM — research-package D5 §5.2.

    ``cefr_by_skill`` is written only via the api ``/profile/cefr`` path (AD-4).
    Domains may read; ingest and agents must not invent CEFR.
    """

    __tablename__ = "learner_profile"

    id: Mapped[uuid.UUID] = uuid_pk()
    cefr_by_skill: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    goals: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    constraints: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()
