"""LearnerProfile CEFR read/write — sole LTM writer for CEFR (AD-4).

Singleton ``/profile/cefr`` upserts the MVP learner from
``app.db.constants.MVP_LEARNER_ID`` (AD-10). Domains may read later; ingest and
agents must not invent CEFR.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.constants import MVP_LEARNER_ID
from app.db.session import get_session
from app.models.learner_profile import LearnerProfile
from app.schemas.cefr import CefrBySkill

router = APIRouter(prefix="/profile", tags=["profile"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/cefr")
async def get_cefr(session: SessionDep) -> dict[str, str]:
    """Return the bare CEFR map. No row yet → empty map (no insert)."""
    profile = await session.get(LearnerProfile, MVP_LEARNER_ID)
    if profile is None:
        return {}
    raw = profile.cefr_by_skill or {}
    return {str(k): str(v) for k, v in raw.items()}


@router.put("/cefr", status_code=204)
async def put_cefr(body: CefrBySkill, session: SessionDep) -> None:
    """Full-replace ``cefr_by_skill`` for the MVP learner; other columns untouched."""
    stored = body.to_stored_map()
    stmt = (
        insert(LearnerProfile)
        .values(id=MVP_LEARNER_ID, cefr_by_skill=stored)
        .on_conflict_do_update(
            index_elements=[LearnerProfile.id],
            set_={"cefr_by_skill": stored, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)
    await session.commit()
