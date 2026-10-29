"""Corpus Ready + embedding tables (vector 1024)

Revision ID: 0003
Revises: 0002

Schema only — no textbook seed, no Ready mint. Ingest is the sole writer.
"""

import sqlalchemy as sa
from alembic import op
from lingua_corpus import EMBEDDING_DIMS, UNIT_STATUSES
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UUID_PK = dict(primary_key=True, server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")
EMPTY_OBJ = sa.text("'{}'::jsonb")


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def _ts(name: str, **kw) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "textbook",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        _ts("created_at", nullable=False, server_default=NOW),
    )

    op.create_table(
        "textbook_unit",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column(
            "textbook_id",
            sa.Text,
            sa.ForeignKey("textbook.id"),
            nullable=False,
        ),
        sa.Column("unit_ref", sa.Text, nullable=False),
        sa.Column(
            "status",
            _enum("textbook_unit_status", *UNIT_STATUSES),
            nullable=False,
        ),
        sa.Column("gate_reason", sa.Text, nullable=True),
        sa.Column(
            "gate_metrics",
            pg.JSONB,
            nullable=False,
            server_default=EMPTY_OBJ,
        ),
        _ts("created_at", nullable=False, server_default=NOW),
        _ts("updated_at", nullable=False, server_default=NOW),
        sa.UniqueConstraint("unit_ref"),
    )

    op.create_table(
        "chunk",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column(
            "unit_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("textbook_unit.id"),
            nullable=False,
        ),
        sa.Column("textbook_id", sa.Text, nullable=False),
        sa.Column("unit_ref", sa.Text, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
    )

    op.create_table(
        "embedding",
        sa.Column("id", pg.UUID(as_uuid=True), **UUID_PK),
        sa.Column(
            "chunk_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("chunk.id"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(EMBEDDING_DIMS), nullable=False),
        sa.Column("model_name", sa.Text, nullable=False),
        sa.Column("dims", sa.Integer, nullable=False),
        sa.UniqueConstraint("chunk_id"),
        sa.CheckConstraint(
            f"dims = {EMBEDDING_DIMS}",
            name="embedding_dims_check",
        ),
    )
