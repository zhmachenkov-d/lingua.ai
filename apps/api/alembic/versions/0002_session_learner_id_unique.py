"""UNIQUE(session.learner_id) after dedupe + FK remap

Revision ID: 0002
Revises: 0001

Collapses duplicate session rows (survivor: newest updated_at, then
started_at, then id), remaps error_log/review_record.session_id onto the
survivor, then adds UNIQUE(learner_id). Remap is always possible while the
survivor row still exists; no NULL fallback needed.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Shared CTE: survivor per learner_id, discarded ids mapped to that survivor.
_DEDUP_CTE = """
WITH ranked AS (
    SELECT id, learner_id,
           ROW_NUMBER() OVER (
               PARTITION BY learner_id
               ORDER BY updated_at DESC, started_at DESC, id DESC
           ) AS rn
    FROM session
),
survivor AS (
    SELECT id AS survivor_id, learner_id FROM ranked WHERE rn = 1
),
discarded AS (
    SELECT r.id AS discarded_id, s.survivor_id
    FROM ranked r
    JOIN survivor s ON s.learner_id = r.learner_id
    WHERE r.rn > 1
)
"""


def upgrade() -> None:
    # Block concurrent writers so a race cannot re-insert a duplicate before UNIQUE.
    op.execute(
        "LOCK TABLE session, error_log, review_record IN ACCESS EXCLUSIVE MODE"
    )
    op.execute(
        f"""
        {_DEDUP_CTE}
        UPDATE error_log AS e
        SET session_id = d.survivor_id
        FROM discarded AS d
        WHERE e.session_id = d.discarded_id
        """
    )
    op.execute(
        f"""
        {_DEDUP_CTE}
        UPDATE review_record AS r
        SET session_id = d.survivor_id
        FROM discarded AS d
        WHERE r.session_id = d.discarded_id
        """
    )
    op.execute(
        f"""
        {_DEDUP_CTE}
        DELETE FROM session AS s
        USING discarded AS d
        WHERE s.id = d.discarded_id
        """
    )
    op.create_unique_constraint(
        "session_learner_id_key",
        "session",
        ["learner_id"],
    )
