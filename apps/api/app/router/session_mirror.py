"""Best-effort non-SoT Session mirror after successful Router snapshots (AD-3).

Checkpointer remains STM SoT. Mirror failures must never fail the turn.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.config import get_database_url, to_sqlalchemy_url
from app.db.constants import MVP_LEARNER_ID
from app.models.learner_profile import LearnerProfile
from app.models.session import Session

# Skeleton Router turn has checkpointer ``active_agent: None``; Session enum requires a value.
_MIRROR_ACTIVE_AGENT = "Router"


async def ensure_mvp_learner_profile(db: AsyncSession) -> None:
    """Insert MVP learner_profile id with empty CEFR defaults if missing (AD-4)."""
    existing = await db.get(LearnerProfile, MVP_LEARNER_ID)
    if existing is not None:
        return
    # id only — server defaults for cefr_by_skill/goals/constraints; do not invent CEFR.
    db.add(LearnerProfile(id=MVP_LEARNER_ID))
    await db.flush()


async def upsert_session_mirror(*, database_url: str | None = None) -> None:
    """Upsert one Session row for ``MVP_LEARNER_ID`` via an ephemeral engine.

    Prefer ``database_url`` override (same pattern as checkpointer); do not use
    process-global ``get_engine()``.
    """
    url = database_url if database_url is not None else get_database_url()
    engine = create_async_engine(to_sqlalchemy_url(url))
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            await ensure_mvp_learner_profile(db)
            result = await db.execute(
                select(Session).where(Session.learner_id == MVP_LEARNER_ID).limit(1)
            )
            row = result.scalar_one_or_none()
            now = datetime.now(UTC)
            if row is None:
                db.add(
                    Session(
                        learner_id=MVP_LEARNER_ID,
                        active_agent=_MIRROR_ACTIVE_AGENT,
                        updated_at=now,
                    )
                )
            else:
                row.active_agent = _MIRROR_ACTIVE_AGENT
                row.updated_at = now
            await db.commit()
    finally:
        await engine.dispose()
