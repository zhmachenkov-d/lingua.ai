"""learner LTM tables + non-authoritative Session mirror (research-package D5)

Revision ID: 0001
Revises:

Does NOT create LangGraph checkpointer tables (AsyncPostgresSaver.setup() owns
them). `session` is a non-authoritative mirror — not STM SoT (AD-3).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UUID_PK = dict(
    primary_key=True, server_default=sa.text("gen_random_uuid()")
)
NOW = sa.text("now()")
EMPTY_ARRAY = sa.text("'{}'::text[]")
EMPTY_OBJ = sa.text("'{}'::jsonb")


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def _ts(name: str, **kw) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def upgrade() -> None:
    op.create_table(
        "learner_profile",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column("cefr_by_skill", pg.JSONB, nullable=False, server_default=EMPTY_OBJ),
        sa.Column("goals", pg.ARRAY(sa.Text), nullable=False, server_default=EMPTY_ARRAY),
        sa.Column("constraints", pg.JSONB, nullable=False, server_default=EMPTY_OBJ),
        _ts("created_at", nullable=False, server_default=NOW),
        _ts("updated_at", nullable=False, server_default=NOW),
    )

    # Session first: ErrorLog / ReviewRecord carry nullable FKs to it.
    op.create_table(
        "session",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column(
            "learner_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("learner_profile.id"),
            nullable=False,
        ),
        sa.Column(
            "active_agent",
            _enum("session_active_agent", "Router", "Tutor", "Vocabulary", "Review"),
            nullable=False,
        ),
        sa.Column("touched_lemmas", pg.ARRAY(sa.Text), nullable=False, server_default=EMPTY_ARRAY),
        sa.Column("touched_rule_ids", pg.ARRAY(sa.Text), nullable=False, server_default=EMPTY_ARRAY),
        sa.Column(
            "tblt_phase",
            _enum("session_tblt_phase", "none", "pre", "main", "post"),
            nullable=True,
        ),
        sa.Column("drafts", pg.JSONB, nullable=False, server_default=EMPTY_OBJ),
        sa.Column("unit_ref", sa.Text, nullable=True),
        _ts("started_at", nullable=False, server_default=NOW),
        _ts("updated_at", nullable=False, server_default=NOW),
        comment="NON-AUTHORITATIVE mirror; LangGraph checkpointer is STM SoT (AD-3)",
    )

    op.create_table(
        "vocabulary_item",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column(
            "learner_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("learner_profile.id"),
            nullable=False,
        ),
        sa.Column("lemma", sa.Text, nullable=False),
        sa.Column(
            "source",
            _enum("vocabulary_item_source", "textbook", "lexicon"),
            nullable=False,
        ),
        sa.Column(
            "lexicon_provider",
            _enum("vocabulary_item_lexicon_provider", "free_dictionary", "oxford"),
            nullable=True,
        ),
        sa.Column("textbook_id", sa.Text, nullable=True),
        sa.Column("unit_ref", sa.Text, nullable=True),
        sa.Column(
            "status",
            _enum(
                "vocabulary_item_status", "Unseen", "Learning", "Review", "Mastered"
            ),
            nullable=False,
        ),
        sa.Column("difficulty", sa.Float, nullable=True),
        sa.Column("stability", sa.Float, nullable=True),
        _ts("next_review", nullable=False, server_default=NOW),
        sa.Column("retrievability", sa.Float, nullable=True),
        sa.Column("learned", sa.Boolean, nullable=False, server_default=sa.false()),
        _ts("learned_checked_at", nullable=True),
        _ts("created_at", nullable=False, server_default=NOW),
        _ts("updated_at", nullable=False, server_default=NOW),
        sa.UniqueConstraint("learner_id", "lemma"),
    )

    op.create_table(
        "error_log",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column(
            "learner_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("learner_profile.id"),
            nullable=False,
        ),
        sa.Column("error_type", sa.Text, nullable=False),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=False),
        _ts("occurred_at", nullable=False, server_default=NOW),
        sa.Column(
            "vocab_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("vocabulary_item.id"),
            nullable=True,
        ),
        sa.Column("rule_id", sa.Text, nullable=True),
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("unit_ref", sa.Text, nullable=True),
        sa.Column("count_7d", sa.Integer, nullable=True),
    )

    op.create_table(
        "review_record",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column(
            "learner_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("learner_profile.id"),
            nullable=False,
        ),
        sa.Column(
            "vocab_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("vocabulary_item.id"),
            nullable=False,
        ),
        sa.Column(
            "rating",
            _enum("review_record_rating", "Again", "Hard", "Good", "Easy"),
            nullable=False,
        ),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column(
            "drill_modality",
            _enum(
                "review_record_drill_modality",
                "translate_en_ru",
                "translate_ru_en",
                "match",
                "write",
                "cloze",
                "listen_and_spell",
            ),
            nullable=False,
        ),
        _ts("reviewed_at", nullable=False, server_default=NOW),
        sa.Column(
            "session_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "error_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("error_log.id"),
            nullable=True,
        ),
        sa.Column("stability_after", sa.Float, nullable=True),
        sa.Column("difficulty_after", sa.Float, nullable=True),
        _ts("next_review_after", nullable=True),
    )
