"""Overall CEFR gate read — empty/invalid → None; no silent seed."""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.constants import MVP_LEARNER_ID
from app.models.learner_profile import LearnerProfile
from app.schemas.cefr import CefrBySkill, CefrLevel


async def read_overall_cefr(session: AsyncSession) -> CefrLevel | None:
    """Return valid overall CEFR, or None when missing / invalid (do not seed)."""
    profile = await session.get(LearnerProfile, MVP_LEARNER_ID)
    if profile is None:
        return None
    raw = profile.cefr_by_skill or {}
    try:
        mapped = CefrBySkill.model_validate(raw)
    except ValidationError:
        return None
    return mapped.overall
