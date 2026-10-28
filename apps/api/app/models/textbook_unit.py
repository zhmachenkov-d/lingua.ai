import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Enum, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_col, updated_at_col, uuid_pk

UNIT_STATUSES = ("Ready", "NotReady", "Review")


class TextbookUnit(Base):
    """Corpus Ready gate row — status + auditable gate_metrics (R4).

    Ingest is the sole writer; api owns schema only.
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
