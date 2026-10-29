"""Shared embedding pin + Ready-by-unit_ref query contract (story 2.6)."""

from __future__ import annotations

import asyncio

import pytest
from app.corpus import get_ready_unit_chunks
from app.db.bootstrap import bootstrap
from app.db.config import to_sqlalchemy_url
from app.models import Chunk, Embedding, Textbook, TextbookUnit
from app.models.embedding import EMBEDDING_DIMS as API_EMBEDDING_DIMS
from lingua_ids import EF4_BEG_SB_ID, EMBEDDING_DIMS, EMBEDDING_MODEL_NAME
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session


@pytest.fixture
def migrated_url(fresh_db_url: str) -> str:
    asyncio.run(bootstrap(fresh_db_url, lock_timeout=10))
    return fresh_db_url


def test_shared_embedding_pin() -> None:
    """AC: shared SoT pin; api ORM dims matches."""
    assert EMBEDDING_MODEL_NAME == "BAAI/bge-m3"  # shared SoT value
    assert EMBEDDING_DIMS == 1024
    assert API_EMBEDDING_DIMS == EMBEDDING_DIMS
    assert API_EMBEDDING_DIMS == 1024


@pytest.mark.integration_db
def test_ready_unit_query_returns_ordered_stamped_chunks(migrated_url: str) -> None:
    unit_ref = f"{EF4_BEG_SB_ID}/1A"
    vectors = [
        [0.1] * EMBEDDING_DIMS,
        [0.2] * EMBEDDING_DIMS,
    ]
    contents = ["first chunk", "second chunk"]

    engine = create_engine(to_sqlalchemy_url(migrated_url))
    try:
        with Session(engine) as session:
            session.add(Textbook(id=EF4_BEG_SB_ID, title="EF4 Beginner SB"))
            session.flush()
            unit = TextbookUnit(
                textbook_id=EF4_BEG_SB_ID,
                unit_ref=unit_ref,
                status="Ready",
                gate_reason=None,
                gate_metrics={"mean_chars_per_page": 400.0},
            )
            session.add(unit)
            session.flush()
            for ordinal, (content, vector) in enumerate(
                zip(contents, vectors, strict=True)
            ):
                chunk = Chunk(
                    unit_id=unit.id,
                    textbook_id=EF4_BEG_SB_ID,
                    unit_ref=unit_ref,
                    ordinal=ordinal,
                    content=content,
                )
                session.add(chunk)
                session.flush()
                session.add(
                    Embedding(
                        chunk_id=chunk.id,
                        embedding=vector,
                        model_name=EMBEDDING_MODEL_NAME,
                        dims=EMBEDDING_DIMS,
                    )
                )
            session.commit()
    finally:
        engine.dispose()

    async def _run() -> None:
        async_engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(async_engine, expire_on_commit=False)
        try:
            async with factory() as session:
                result = await get_ready_unit_chunks(session, unit_ref)
            assert result is not None
            assert result.unit_ref == unit_ref
            assert result.status == "Ready"
            assert [c.ordinal for c in result.chunks] == [0, 1]
            assert [c.content for c in result.chunks] == contents
            for chunk in result.chunks:
                assert len(chunk.embedding) == EMBEDDING_DIMS
                assert chunk.model_name == EMBEDDING_MODEL_NAME
                assert chunk.dims == EMBEDDING_DIMS
        finally:
            await async_engine.dispose()

    asyncio.run(_run())


@pytest.mark.integration_db
def test_unknown_and_not_ready_unit_query_return_none(migrated_url: str) -> None:
    not_ready_ref = f"{EF4_BEG_SB_ID}/9Z"
    review_ref = f"{EF4_BEG_SB_ID}/review"

    engine = create_engine(to_sqlalchemy_url(migrated_url))
    try:
        with Session(engine) as session:
            session.add(Textbook(id=EF4_BEG_SB_ID, title="EF4 Beginner SB"))
            session.flush()
            session.add(
                TextbookUnit(
                    textbook_id=EF4_BEG_SB_ID,
                    unit_ref=not_ready_ref,
                    status="NotReady",
                    gate_reason="mean_chars_per_page",
                    gate_metrics={"mean_chars_per_page": 10.0},
                )
            )
            session.add(
                TextbookUnit(
                    textbook_id=EF4_BEG_SB_ID,
                    unit_ref=review_ref,
                    status="Review",
                    gate_reason=None,
                    gate_metrics={},
                )
            )
            session.commit()
    finally:
        engine.dispose()

    async def _run() -> None:
        async_engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(async_engine, expire_on_commit=False)
        try:
            async with factory() as session:
                assert await get_ready_unit_chunks(session, not_ready_ref) is None
                assert await get_ready_unit_chunks(session, review_ref) is None
                assert (
                    await get_ready_unit_chunks(session, f"{EF4_BEG_SB_ID}/missing")
                    is None
                )
        finally:
            await async_engine.dispose()

    asyncio.run(_run())
