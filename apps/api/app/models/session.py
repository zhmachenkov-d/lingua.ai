import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, updated_at_col, uuid_pk

ACTIVE_AGENTS = ("Router", "Tutor", "Vocabulary", "Review")
TBLT_PHASES = ("none", "pre", "main", "post")


class Session(Base):
    """D5 §5.6 Session shape — a NON-AUTHORITATIVE MIRROR only (AD-3, AD-9).

    NOT the source of truth (not SoT) for short-term memory. The LangGraph
    checkpointer (AsyncPostgresSaver) is the STM source of truth; this table is
    never read as STM and must not be written as if it were authoritative. It
    exists for SQL debugging and as an optional FK target from ErrorLog /
    ReviewRecord. If it disagrees with the checkpointer, the checkpointer wins.
    """

    __tablename__ = "session"
    __table_args__ = {
        "comment": "NON-AUTHORITATIVE mirror; LangGraph checkpointer is STM SoT (AD-3)"
    }

    id: Mapped[uuid.UUID] = uuid_pk()
    learner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learner_profile.id"))
    active_agent: Mapped[str] = mapped_column(
        Enum(*ACTIVE_AGENTS, name="session_active_agent", native_enum=False, create_constraint=True)
    )
    touched_lemmas: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    touched_rule_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    tblt_phase: Mapped[str | None] = mapped_column(
        Enum(*TBLT_PHASES, name="session_tblt_phase", native_enum=False, create_constraint=True)
    )
    drafts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    unit_ref: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = updated_at_col()
