"""Tutor handoff matrix: CEFR gate, no-ready, empty-rag, happy teach + patch."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from app.corpus.query import ReadyChunk, ReadyUnitCorpus
from app.db.bootstrap import bootstrap
from app.db.config import to_sqlalchemy_url
from app.db.constants import MVP_LEARNER_ID
from app.llm.adapter import ClassifyResult
from app.models import Embedding, Textbook, TextbookUnit
from app.models.chunk import Chunk
from app.models.learner_profile import LearnerProfile
from app.router.turn import (
    AGENT_CTAS,
    BLANK_INPUT,
    CTA_MESSAGE,
    UNKNOWN_INTENT,
    TurnSuccess,
    get_turn_snapshot,
    handle_turn,
)
from app.tutor.copy import CEFR_MISSING, EMPTY_RAG, NO_READY
from app.tutor.handoff import CEFR_GATE_CTAS, handle_tutor
from lingua_ids import EF4_BEG_SB_ID, EMBEDDING_DIMS, EMBEDDING_MODEL_NAME
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session


@pytest.fixture
def migrated_url(fresh_db_url: str) -> str:
    asyncio.run(bootstrap(fresh_db_url, lock_timeout=10))
    return fresh_db_url


def _seed_profile(url: str, cefr: dict | None) -> None:
    engine = create_engine(to_sqlalchemy_url(url))
    try:
        with Session(engine) as session:
            session.add(
                LearnerProfile(id=MVP_LEARNER_ID, cefr_by_skill=cefr or {})
            )
            session.commit()
    finally:
        engine.dispose()


def _seed_ready_unit(
    url: str,
    *,
    unit_ref: str,
    with_chunks: bool,
    textbook_id: str = EF4_BEG_SB_ID,
) -> None:
    engine = create_engine(to_sqlalchemy_url(url))
    try:
        with Session(engine) as session:
            if session.get(Textbook, textbook_id) is None:
                session.add(Textbook(id=textbook_id, title="EF4 Beginner SB"))
                session.flush()
            unit = TextbookUnit(
                textbook_id=textbook_id,
                unit_ref=unit_ref,
                status="Ready",
                gate_reason=None,
                gate_metrics={},
            )
            session.add(unit)
            session.flush()
            if with_chunks:
                chunk = Chunk(
                    unit_id=unit.id,
                    textbook_id=textbook_id,
                    unit_ref=unit_ref,
                    ordinal=0,
                    content="Hello from Ready SB.",
                )
                session.add(chunk)
                session.flush()
                session.add(
                    Embedding(
                        chunk_id=chunk.id,
                        embedding=[0.1] * EMBEDDING_DIMS,
                        model_name=EMBEDDING_MODEL_NAME,
                        dims=EMBEDDING_DIMS,
                    )
                )
            session.commit()
    finally:
        engine.dispose()


@pytest.mark.integration_db
def test_tutor_cefr_missing_gate(migrated_url: str) -> None:
    _seed_profile(migrated_url, {})

    async def _run() -> None:
        engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                outcome = await handle_tutor(session)
        finally:
            await engine.dispose()
        assert outcome.message == CEFR_MISSING
        assert outcome.ctas == CEFR_GATE_CTAS
        assert outcome.session_patch == {}
        assert outcome.emit_token_delta is False

    asyncio.run(_run())


@pytest.mark.integration_db
def test_tutor_no_ready_sb(migrated_url: str) -> None:
    _seed_profile(migrated_url, {"overall": "A1"})

    async def _run() -> None:
        engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                outcome = await handle_tutor(session)
        finally:
            await engine.dispose()
        assert outcome.message == NO_READY
        assert outcome.ctas == AGENT_CTAS
        assert outcome.session_patch == {}

    asyncio.run(_run())


@pytest.mark.integration_db
def test_tutor_empty_rag(migrated_url: str) -> None:
    unit_ref = f"{EF4_BEG_SB_ID}/1A"
    _seed_profile(migrated_url, {"overall": "A2"})
    _seed_ready_unit(migrated_url, unit_ref=unit_ref, with_chunks=False)

    async def _run() -> None:
        engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                outcome = await handle_tutor(session)
        finally:
            await engine.dispose()
        assert outcome.message == EMPTY_RAG
        assert outcome.ctas == AGENT_CTAS
        assert outcome.session_patch == {"tutor": {"active_unit_ref": unit_ref}}
        assert outcome.active_agent == "Tutor"
        assert outcome.emit_token_delta is False

    asyncio.run(_run())


@pytest.mark.integration_db
def test_tutor_happy_lex_min_bind_and_grounded_teach(migrated_url: str) -> None:
    early = f"{EF4_BEG_SB_ID}/1A"
    later = f"{EF4_BEG_SB_ID}/2B"
    _seed_profile(migrated_url, {"overall": "B1"})
    _seed_ready_unit(migrated_url, unit_ref=later, with_chunks=True)
    _seed_ready_unit(migrated_url, unit_ref=early, with_chunks=True)

    async def _run() -> None:
        engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                outcome = await handle_tutor(session)
        finally:
            await engine.dispose()
        assert outcome.active_agent == "Tutor"
        assert outcome.session_patch == {"tutor": {"active_unit_ref": early}}
        assert early in outcome.message
        assert "Hello from Ready SB." in outcome.message
        assert outcome.emit_token_delta is True
        assert outcome.ctas == ()

    asyncio.run(_run())


@pytest.mark.integration_db
def test_handle_turn_tutor_cta_persists_patch(migrated_url: str) -> None:
    unit_ref = f"{EF4_BEG_SB_ID}/1A"
    _seed_profile(migrated_url, {"overall": "A1"})
    _seed_ready_unit(migrated_url, unit_ref=unit_ref, with_chunks=True)

    result = asyncio.run(handle_turn("tutor_unit", database_url=migrated_url))
    assert isinstance(result, TurnSuccess)
    assert result.emit_token_delta is True
    assert unit_ref in result.message
    snap = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert snap is not None
    assert snap["active_agent"] == "Tutor"
    assert snap["tutor"] == {"active_unit_ref": unit_ref}


def test_handle_turn_blank_unknown_low() -> None:
    with patch(
        "app.router.turn.write_turn_snapshot",
        new_callable=AsyncMock,
        return_value={},
    ):
        blank = asyncio.run(handle_turn("   "))
        assert isinstance(blank, TurnSuccess)
        assert blank.message == BLANK_INPUT
        assert blank.ctas == AGENT_CTAS

        with patch(
            "app.router.turn.classify_turn",
            new_callable=AsyncMock,
            return_value=ClassifyResult(
                intent=None, band="unknown", used_backup=False
            ),
        ):
            unknown = asyncio.run(handle_turn("???")).message
        assert unknown == UNKNOWN_INTENT

        with patch(
            "app.router.turn.classify_turn",
            new_callable=AsyncMock,
            return_value=ClassifyResult(
                intent="tutor_unit", band="low", used_backup=False
            ),
        ):
            low = asyncio.run(handle_turn("maybe")).message
        assert low == CTA_MESSAGE


def test_vocab_and_review_stubs_via_handle_turn() -> None:
    with patch(
        "app.router.turn.write_turn_snapshot",
        new_callable=AsyncMock,
        return_value={},
    ) as write:
        vocab = asyncio.run(handle_turn("vocab_lookup"))
        review = asyncio.run(handle_turn("review_daily"))
    assert isinstance(vocab, TurnSuccess)
    assert vocab.message == "Vocabulary пока в подготовке."
    assert vocab.ctas == ()
    assert isinstance(review, TurnSuccess)
    assert review.message == "Review пока в подготовке."
    assert write.await_count == 2
    assert write.await_args_list[0].kwargs["session_patch"] == {"vocabulary": {}}
    assert write.await_args_list[0].kwargs["active_agent"] == "Vocabulary"
    assert write.await_args_list[1].kwargs["session_patch"] == {"review": {}}
    assert write.await_args_list[1].kwargs["active_agent"] == "Review"


def test_grounded_teach_uses_only_chunk_content() -> None:
    from app.tutor.teach import grounded_teach_message

    corpus = ReadyUnitCorpus(
        unit_ref=f"{EF4_BEG_SB_ID}/1A",
        status="Ready",
        chunks=[
            ReadyChunk(
                ordinal=0,
                content="chunk-alpha",
                embedding=[0.0] * 4,
                model_name="x",
                dims=4,
            )
        ],
    )
    msg = grounded_teach_message(corpus)
    assert "chunk-alpha" in msg
    assert "invented" not in msg.lower()


def test_handle_tutor_matrix_unit_mocked() -> None:
    """Matrix rows Happy / CEFR / no-ready / empty-rag without integration_db."""
    session = AsyncMock()

    async def _cefr_gate() -> None:
        with (
            patch(
                "app.tutor.handoff.read_overall_cefr",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.tutor.handoff.first_ready_sb_unit_ref",
                new_callable=AsyncMock,
            ) as bind,
        ):
            out = await handle_tutor(session)
        assert out.message == CEFR_MISSING
        assert out.ctas == CEFR_GATE_CTAS
        bind.assert_not_awaited()

    async def _no_ready() -> None:
        with (
            patch(
                "app.tutor.handoff.read_overall_cefr",
                new_callable=AsyncMock,
                return_value="A1",
            ),
            patch(
                "app.tutor.handoff.first_ready_sb_unit_ref",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            out = await handle_tutor(session)
        assert out.message == NO_READY
        assert "ingest" in out.message.lower() or "агента" in out.message
        assert out.ctas == AGENT_CTAS

    unit_ref = f"{EF4_BEG_SB_ID}/1A"

    async def _empty_rag() -> None:
        with (
            patch(
                "app.tutor.handoff.read_overall_cefr",
                new_callable=AsyncMock,
                return_value="A2",
            ),
            patch(
                "app.tutor.handoff.first_ready_sb_unit_ref",
                new_callable=AsyncMock,
                return_value=unit_ref,
            ),
            patch(
                "app.tutor.handoff.get_ready_unit_chunks",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            out = await handle_tutor(session)
        assert out.message == EMPTY_RAG
        assert out.ctas == AGENT_CTAS
        assert out.session_patch == {"tutor": {"active_unit_ref": unit_ref}}
        assert out.emit_token_delta is False

    async def _happy() -> None:
        corpus = ReadyUnitCorpus(
            unit_ref=unit_ref,
            status="Ready",
            chunks=[
                ReadyChunk(
                    ordinal=0,
                    content="Hello from Ready SB.",
                    embedding=[0.0] * 4,
                    model_name="x",
                    dims=4,
                )
            ],
        )
        with (
            patch(
                "app.tutor.handoff.read_overall_cefr",
                new_callable=AsyncMock,
                return_value="B1",
            ),
            patch(
                "app.tutor.handoff.first_ready_sb_unit_ref",
                new_callable=AsyncMock,
                return_value=unit_ref,
            ),
            patch(
                "app.tutor.handoff.get_ready_unit_chunks",
                new_callable=AsyncMock,
                return_value=corpus,
            ),
        ):
            out = await handle_tutor(session)
        assert out.emit_token_delta is True
        assert out.session_patch == {"tutor": {"active_unit_ref": unit_ref}}
        assert unit_ref in out.message
        assert "Hello from Ready SB." in out.message
        assert out.ctas == ()

    asyncio.run(_cefr_gate())
    asyncio.run(_no_ready())
    asyncio.run(_empty_rag())
    asyncio.run(_happy())
