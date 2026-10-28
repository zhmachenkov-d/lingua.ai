"""Best-effort non-SoT Session mirror after successful Router snapshots (AD-3).

Checkpointer remains STM SoT. Mirror failures must never fail the turn.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.config import get_database_url, to_sqlalchemy_url
from app.db.constants import MVP_LEARNER_ID
from app.models.learner_profile import LearnerProfile
from app.models.session import Session

# Router turn checkpointer has active_agent None; Session enum needs a value.
_MIRROR_ACTIVE_AGENT = "Router"


async def ensure_mvp_learner_profile(db: AsyncSession) -> None:
    """Insert MVP learner_profile id with empty CEFR defaults if missing (AD-4).

    Conflict-safe: concurrent upserts must not abort on profile PK.
    """
    # id only — server defaults for cefr_by_skill/goals/constraints; do not invent CEFR.
    stmt = (
        insert(LearnerProfile)
        .values(id=MVP_LEARNER_ID)
        .on_conflict_do_nothing(index_elements=[LearnerProfile.id])
    )
    await db.execute(stmt)


async def upsert_session_mirror(*, database_url: str | None = None) -> None:
    """Upsert one Session row for ``MVP_LEARNER_ID`` via an ephemeral engine.

    Prefer ``database_url`` override (same pattern as checkpointer); do not use
    process-global ``get_engine()``. Concurrent first writes converge via
    UNIQUE(learner_id) + ON CONFLICT DO UPDATE.
    """
    url = database_url if database_url is not None else get_database_url()
    engine = create_async_engine(to_sqlalchemy_url(url))
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            await ensure_mvp_learner_profile(db)
            stmt = (
                insert(Session)
                .values(
                    learner_id=MVP_LEARNER_ID,
                    active_agent=_MIRROR_ACTIVE_AGENT,
                )
                .on_conflict_do_update(
                    index_elements=[Session.learner_id],
                    set_={
                        "active_agent": _MIRROR_ACTIVE_AGENT,
                        "updated_at": func.now(),
                    },
                )
            )
            await db.execute(stmt)
            await db.commit()
    finally:
        await engine.dispose()
