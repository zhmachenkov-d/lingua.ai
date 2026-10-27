"""Unit coverage for best-effort Session mirror (matrix rows without live Postgres)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.db.constants import MVP_LEARNER_ID
from app.models.learner_profile import LearnerProfile
from app.models.session import Session
from app.router.session_mirror import ensure_mvp_learner_profile, upsert_session_mirror


def test_ensure_mvp_learner_profile_inserts_when_missing() -> None:
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.flush = AsyncMock()

    asyncio.run(ensure_mvp_learner_profile(db))

    db.get.assert_awaited_once_with(LearnerProfile, MVP_LEARNER_ID)
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert isinstance(added, LearnerProfile)
    assert added.id == MVP_LEARNER_ID
    db.flush.assert_awaited_once()


def test_ensure_mvp_learner_profile_noop_when_present() -> None:
    db = AsyncMock()
    db.get = AsyncMock(return_value=LearnerProfile(id=MVP_LEARNER_ID))
    db.add = MagicMock()

    asyncio.run(ensure_mvp_learner_profile(db))

    db.add.assert_not_called()


def _patch_ephemeral_db(db: AsyncMock):
    """Wire create_async_engine / async_sessionmaker to yield ``db``."""

    engine = MagicMock()
    engine.dispose = AsyncMock()

    @asynccontextmanager
    async def _session_cm():
        yield db

    factory = MagicMock(return_value=_session_cm())
    return patch.multiple(
        "app.router.session_mirror",
        create_async_engine=MagicMock(return_value=engine),
        async_sessionmaker=MagicMock(return_value=factory),
        get_database_url=MagicMock(return_value="postgresql://x/y"),
        to_sqlalchemy_url=MagicMock(side_effect=lambda u: u),
    ), engine


def test_upsert_session_mirror_inserts_row_when_none() -> None:
    db = AsyncMock()
    db.get = AsyncMock(return_value=LearnerProfile(id=MVP_LEARNER_ID))
    db.add = MagicMock()
    db.commit = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    patches, engine = _patch_ephemeral_db(db)
    with patches:
        asyncio.run(upsert_session_mirror(database_url="postgresql://test/db"))

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert isinstance(added, Session)
    assert added.learner_id == MVP_LEARNER_ID
    assert added.active_agent == "Router"
    db.commit.assert_awaited_once()
    engine.dispose.assert_awaited_once()


def test_upsert_session_mirror_updates_existing_without_second_insert() -> None:
    existing = Session(
        id=uuid4(),
        learner_id=MVP_LEARNER_ID,
        active_agent="Tutor",
        updated_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=LearnerProfile(id=MVP_LEARNER_ID))
    db.add = MagicMock()
    db.commit = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    db.execute = AsyncMock(return_value=result)

    patches, _engine = _patch_ephemeral_db(db)
    with patches:
        asyncio.run(upsert_session_mirror())

    db.add.assert_not_called()
    assert existing.active_agent == "Router"
    assert existing.updated_at > datetime(2020, 1, 1, tzinfo=UTC)
    db.commit.assert_awaited_once()


def test_upsert_session_mirror_ensures_profile_when_missing() -> None:
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    patches, _engine = _patch_ephemeral_db(db)
    with patches:
        asyncio.run(upsert_session_mirror(database_url="postgresql://test/db"))

    kinds = [type(c[0][0]) for c in db.add.call_args_list]
    assert LearnerProfile in kinds
    assert Session in kinds
    profile = next(c[0][0] for c in db.add.call_args_list if isinstance(c[0][0], LearnerProfile))
    assert profile.id == MVP_LEARNER_ID
