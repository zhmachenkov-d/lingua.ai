"""Tutor handoff matrix: CEFR, refuse paths, unit-change, empty-rag, happy teach."""

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
from app.tutor.bind import classify_unit_ref_pure
from app.tutor.copy import (
    CEFR_MISSING,
    EMPTY_RAG,
    NO_READY,
    NULL_UNIT,
    OFF_UNIT,
    READY_LOSS,
    SESSION_PERSIST_FAIL,
    UNIT_CHANGE_CONFIRM,
    WORKBOOK_ONLY,
)
from app.tutor.handoff import (
    CEFR_GATE_CTAS,
    UNIT_CHANGE_CTAS,
    UNSET,
    handle_tutor,
    is_off_unit_text,
    pick_refuse_key,
)
from hypothesis import given
from hypothesis import strategies as st
from lingua_ids import (
    EF4_BEG_SB_ID,
    EF4_BEG_WB_ID,
    EMBEDDING_DIMS,
    EMBEDDING_MODEL_NAME,
)
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


def _seed_unit(
    url: str,
    *,
    unit_ref: str,
    status: str = "Ready",
    with_chunks: bool = True,
    textbook_id: str = EF4_BEG_SB_ID,
    content: str = "Hello from Ready SB.",
) -> None:
    engine = create_engine(to_sqlalchemy_url(url))
    try:
        with Session(engine) as session:
            if session.get(Textbook, textbook_id) is None:
                session.add(Textbook(id=textbook_id, title=textbook_id))
                session.flush()
            unit = TextbookUnit(
                textbook_id=textbook_id,
                unit_ref=unit_ref,
                status=status,
                gate_reason=None,
                gate_metrics={},
            )
            session.add(unit)
            session.flush()
            if with_chunks and status == "Ready":
                chunk = Chunk(
                    unit_id=unit.id,
                    textbook_id=textbook_id,
                    unit_ref=unit_ref,
                    ordinal=0,
                    content=content,
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


def _seed_ready_unit(
    url: str,
    *,
    unit_ref: str,
    with_chunks: bool,
    textbook_id: str = EF4_BEG_SB_ID,
) -> None:
    _seed_unit(
        url,
        unit_ref=unit_ref,
        with_chunks=with_chunks,
        textbook_id=textbook_id,
        status="Ready",
    )


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
        assert outcome.emit_token_delta is False

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
            with patch(
                "app.tutor.teach.fetch_lemma_entries",
                new_callable=AsyncMock,
                return_value=[],
            ):
                async with factory() as session:
                    outcome = await handle_tutor(session)
        finally:
            await engine.dispose()
        assert outcome.active_agent == "Tutor"
        assert outcome.session_patch == {"tutor": {"active_unit_ref": early}}
        assert early in outcome.message
        assert "Hello from Ready SB." in outcome.message
        assert "[CEFR target: B1–B2]" in outcome.message
        assert outcome.emit_token_delta is True
        assert outcome.ctas == ()

    asyncio.run(_run())


@pytest.mark.integration_db
def test_tutor_workbook_only_refuse(migrated_url: str) -> None:
    wb = f"{EF4_BEG_WB_ID}/1A"
    _seed_profile(migrated_url, {"overall": "A1"})
    _seed_unit(
        migrated_url,
        unit_ref=wb,
        textbook_id=EF4_BEG_WB_ID,
        status="Ready",
        with_chunks=True,
    )

    async def _run() -> None:
        engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                outcome = await handle_tutor(
                    session, request_unit_ref=wb
                )
        finally:
            await engine.dispose()
        assert outcome.message == WORKBOOK_ONLY
        assert outcome.ctas == AGENT_CTAS
        assert outcome.emit_token_delta is False

    asyncio.run(_run())


@pytest.mark.integration_db
def test_tutor_null_unit_on_clear_chrome(migrated_url: str) -> None:
    _seed_profile(migrated_url, {"overall": "A1"})
    _seed_ready_unit(
        migrated_url, unit_ref=f"{EF4_BEG_SB_ID}/1A", with_chunks=True
    )

    async def _run() -> None:
        engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                outcome = await handle_tutor(
                    session,
                    prior_tutor={"active_unit_ref": f"{EF4_BEG_SB_ID}/1A"},
                    request_unit_ref=None,
                )
        finally:
            await engine.dispose()
        assert outcome.message == NULL_UNIT
        assert outcome.emit_token_delta is False
        assert outcome.unit_switch_attempt is True

    asyncio.run(_run())


@pytest.mark.integration_db
def test_tutor_ready_loss_mid_session(migrated_url: str) -> None:
    unit_ref = f"{EF4_BEG_SB_ID}/1A"
    _seed_profile(migrated_url, {"overall": "A1"})
    _seed_unit(
        migrated_url, unit_ref=unit_ref, status="NotReady", with_chunks=False
    )

    async def _run() -> None:
        engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                outcome = await handle_tutor(
                    session,
                    text="hello",
                    prior_tutor={"active_unit_ref": unit_ref},
                )
        finally:
            await engine.dispose()
        assert outcome.message == READY_LOSS
        assert outcome.ctas == AGENT_CTAS
        assert outcome.emit_token_delta is False

    asyncio.run(_run())


@pytest.mark.integration_db
def test_tutor_off_unit_refuse(migrated_url: str) -> None:
    unit_ref = f"{EF4_BEG_SB_ID}/1A"
    _seed_profile(migrated_url, {"overall": "A1"})
    _seed_unit(
        migrated_url,
        unit_ref=unit_ref,
        with_chunks=True,
        content="Hello from Ready SB.",
    )

    async def _run() -> None:
        engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                outcome = await handle_tutor(
                    session,
                    text="quantum chromodynamics glossary only",
                    prior_tutor={"active_unit_ref": unit_ref},
                )
        finally:
            await engine.dispose()
        assert outcome.message == OFF_UNIT
        assert outcome.emit_token_delta is False
        assert outcome.ctas == AGENT_CTAS

    asyncio.run(_run())


@pytest.mark.integration_db
def test_tutor_unit_change_confirm_decline(migrated_url: str) -> None:
    a = f"{EF4_BEG_SB_ID}/1A"
    b = f"{EF4_BEG_SB_ID}/2B"
    _seed_profile(migrated_url, {"overall": "A1"})
    _seed_unit(migrated_url, unit_ref=a, content="Alpha chunk hello")
    _seed_unit(migrated_url, unit_ref=b, content="Beta chunk world")

    async def _run() -> None:
        engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            with patch(
                "app.tutor.teach.fetch_lemma_entries",
                new_callable=AsyncMock,
                return_value=[],
            ):
                async with factory() as session:
                    ask = await handle_tutor(
                        session,
                        prior_tutor={"active_unit_ref": a},
                        request_unit_ref=b,
                    )
                    assert ask.message == UNIT_CHANGE_CONFIRM
                    assert ask.ctas == UNIT_CHANGE_CTAS
                    assert ask.session_patch == {
                        "tutor": {"active_unit_ref": a, "pending_unit_ref": b}
                    }
                    assert ask.emit_token_delta is False

                    declined = await handle_tutor(
                        session,
                        text="decline_unit",
                        prior_tutor={
                            "active_unit_ref": a,
                            "pending_unit_ref": b,
                        },
                    )
                    assert a in declined.message
                    assert "Alpha chunk hello" in declined.message
                    assert declined.session_patch == {
                        "tutor": {"active_unit_ref": a}
                    }
                    assert "pending_unit_ref" not in declined.session_patch["tutor"]

                    confirmed = await handle_tutor(
                        session,
                        text="confirm_unit",
                        prior_tutor={
                            "active_unit_ref": a,
                            "pending_unit_ref": b,
                        },
                    )
                    assert b in confirmed.message
                    assert "Beta chunk world" in confirmed.message
                    assert confirmed.session_patch == {
                        "tutor": {"active_unit_ref": b}
                    }
                    assert confirmed.emit_token_delta is True
        finally:
            await engine.dispose()

    asyncio.run(_run())


@pytest.mark.integration_db
def test_tutor_chrome_non_ready_sb_is_no_ready_not_ready_loss(
    migrated_url: str,
) -> None:
    active = f"{EF4_BEG_SB_ID}/1A"
    other = f"{EF4_BEG_SB_ID}/9Z"
    _seed_profile(migrated_url, {"overall": "A1"})
    _seed_unit(migrated_url, unit_ref=active, content="keep")
    _seed_unit(
        migrated_url, unit_ref=other, status="NotReady", with_chunks=False
    )

    async def _run() -> None:
        engine = create_async_engine(to_sqlalchemy_url(migrated_url))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                outcome = await handle_tutor(
                    session,
                    prior_tutor={"active_unit_ref": active},
                    request_unit_ref=other,
                )
        finally:
            await engine.dispose()
        assert outcome.message == NO_READY
        assert outcome.message != READY_LOSS
        assert outcome.unit_switch_attempt is True

    asyncio.run(_run())


@pytest.mark.integration_db
def test_handle_turn_tutor_cta_persists_patch(migrated_url: str) -> None:
    unit_ref = f"{EF4_BEG_SB_ID}/1A"
    _seed_profile(migrated_url, {"overall": "A1"})
    _seed_ready_unit(migrated_url, unit_ref=unit_ref, with_chunks=True)

    with patch(
        "app.tutor.teach.fetch_lemma_entries",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = asyncio.run(handle_turn("tutor_unit", database_url=migrated_url))
    assert isinstance(result, TurnSuccess)
    assert result.emit_token_delta is True
    assert unit_ref in result.message
    assert "[CEFR target: A1–A2]" in result.message
    snap = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert snap is not None
    assert snap["active_agent"] == "Tutor"
    assert snap["tutor"] == {"active_unit_ref": unit_ref}


@pytest.mark.integration_db
def test_handle_turn_persist_fail_on_unit_switch_uses_session_persist_fail(
    migrated_url: str,
) -> None:
    a = f"{EF4_BEG_SB_ID}/1A"
    b = f"{EF4_BEG_SB_ID}/2B"
    _seed_profile(migrated_url, {"overall": "A1"})
    _seed_unit(migrated_url, unit_ref=a, content="Alpha")
    _seed_unit(migrated_url, unit_ref=b, content="Beta")
    with patch(
        "app.tutor.teach.fetch_lemma_entries",
        new_callable=AsyncMock,
        return_value=[],
    ):
        first = asyncio.run(handle_turn("tutor_unit", database_url=migrated_url))
    assert isinstance(first, TurnSuccess)

    with patch(
        "app.router.turn.write_turn_snapshot",
        new_callable=AsyncMock,
        side_effect=RuntimeError("aput boom"),
    ):
        result = asyncio.run(
            handle_turn(
                "tutor_unit",
                unit_ref=b,
                database_url=migrated_url,
            )
        )
    assert isinstance(result, TurnSuccess)
    assert result.message == SESSION_PERSIST_FAIL
    assert result.emit_token_delta is False
    snap = asyncio.run(get_turn_snapshot(database_url=migrated_url))
    assert snap is not None
    assert snap["tutor"] == {"active_unit_ref": a}


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
    """Matrix: Happy / CEFR / no-ready / empty-rag / refuse (no integration_db)."""
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
            patch(
                "app.tutor.teach.fetch_lemma_entries",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            out = await handle_tutor(session)
        assert out.emit_token_delta is True
        assert out.session_patch == {"tutor": {"active_unit_ref": unit_ref}}
        assert unit_ref in out.message
        assert "Hello from Ready SB." in out.message
        assert "[CEFR target: B1–B2]" in out.message
        assert "Mini-context" not in out.message
        assert out.ctas == ()

    async def _null_unit_chrome() -> None:
        with patch(
            "app.tutor.handoff.read_overall_cefr",
            new_callable=AsyncMock,
            return_value="A1",
        ):
            out = await handle_tutor(
                session,
                prior_tutor={"active_unit_ref": unit_ref},
                request_unit_ref=None,
            )
        assert out.message == NULL_UNIT
        assert out.emit_token_delta is False

    async def _workbook() -> None:
        with (
            patch(
                "app.tutor.handoff.read_overall_cefr",
                new_callable=AsyncMock,
                return_value="A1",
            ),
            patch(
                "app.tutor.handoff.classify_unit_ref",
                new_callable=AsyncMock,
                return_value="workbook",
            ),
        ):
            out = await handle_tutor(
                session, request_unit_ref=f"{EF4_BEG_WB_ID}/1A"
            )
        assert out.message == WORKBOOK_ONLY
        assert out.emit_token_delta is False

    async def _precedence_null_over_off() -> None:
        with patch(
            "app.tutor.handoff.read_overall_cefr",
            new_callable=AsyncMock,
            return_value="A1",
        ):
            out = await handle_tutor(
                session,
                text="totally unrelated jargon",
                prior_tutor={"active_unit_ref": unit_ref},
                request_unit_ref=None,
            )
        assert out.message == NULL_UNIT
        assert out.message != OFF_UNIT

    asyncio.run(_cefr_gate())
    asyncio.run(_no_ready())
    asyncio.run(_empty_rag())
    asyncio.run(_happy())
    asyncio.run(_null_unit_chrome())
    asyncio.run(_workbook())
    asyncio.run(_precedence_null_over_off())


@given(
    flags=st.fixed_dictionaries(
        {
            "null-unit": st.booleans(),
            "no-ready": st.booleans(),
            "workbook-only": st.booleans(),
            "ready-loss": st.booleans(),
            "off-unit": st.booleans(),
        }
    )
)
def test_refuse_precedence_picks_at_most_one(flags: dict[str, bool]) -> None:
    picked = pick_refuse_key(flags)
    if not any(flags.values()):
        assert picked is None
        return
    assert picked is not None
    assert flags[picked] is True
    order = (
        "null-unit",
        "no-ready",
        "workbook-only",
        "ready-loss",
        "off-unit",
    )
    for key in order:
        if key == picked:
            break
        assert flags[key] is False


@given(
    unit_ref=st.one_of(
        st.none(),
        st.just(""),
        st.just("   "),
        st.just(EF4_BEG_WB_ID),
        st.just(f"{EF4_BEG_WB_ID}/1A"),
        st.just(f"{EF4_BEG_SB_ID}/1A"),
        st.text(min_size=1, max_size=24),
    ),
    status=st.sampled_from(["Ready", "NotReady", "Review"]),
    exists=st.booleans(),
)
def test_classify_unit_ref_pure_workbook_and_null_invariants(
    unit_ref: str | None, status: str, exists: bool
) -> None:
    kind = classify_unit_ref_pure(
        unit_ref,
        textbook_id=EF4_BEG_SB_ID if exists else None,
        status=status if exists else None,
        exists=exists,
    )
    if unit_ref is None or not str(unit_ref).strip():
        assert kind == "null"
    elif str(unit_ref).strip() == EF4_BEG_WB_ID or str(unit_ref).strip().startswith(
        f"{EF4_BEG_WB_ID}/"
    ):
        assert kind == "workbook"
    elif not exists:
        assert kind == "unknown"


def test_off_unit_token_overlap_and_on_path() -> None:
    chunks = ["Hello from Ready SB."]
    assert is_off_unit_text("quantum chromodynamics", chunks) is True
    assert is_off_unit_text("hello ready", chunks) is False
    assert is_off_unit_text("tutor_unit", chunks) is False
    assert is_off_unit_text("confirm_unit", chunks) is False
    assert is_off_unit_text("decline_unit", chunks) is False


def test_explicit_chrome_null_never_auto_binds() -> None:
    session = AsyncMock()

    async def _run() -> None:
        with (
            patch(
                "app.tutor.handoff.read_overall_cefr",
                new_callable=AsyncMock,
                return_value="A1",
            ),
            patch(
                "app.tutor.handoff.first_ready_sb_unit_ref",
                new_callable=AsyncMock,
                return_value=f"{EF4_BEG_SB_ID}/1A",
            ) as bind,
        ):
            out = await handle_tutor(session, request_unit_ref=None)
        assert out.message == NULL_UNIT
        bind.assert_not_awaited()

    asyncio.run(_run())


def test_unset_request_still_auto_binds() -> None:
    session = AsyncMock()
    unit_ref = f"{EF4_BEG_SB_ID}/1A"
    corpus = ReadyUnitCorpus(
        unit_ref=unit_ref,
        status="Ready",
        chunks=[
            ReadyChunk(
                ordinal=0,
                content="Hello",
                embedding=[0.0] * 4,
                model_name="x",
                dims=4,
            )
        ],
    )

    async def _run() -> None:
        with (
            patch(
                "app.tutor.handoff.read_overall_cefr",
                new_callable=AsyncMock,
                return_value="A1",
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
            patch(
                "app.tutor.teach.fetch_lemma_entries",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            out = await handle_tutor(session, request_unit_ref=UNSET)
        assert out.emit_token_delta is True
        assert unit_ref in out.message
        assert "[CEFR target: A1–A2]" in out.message

    asyncio.run(_run())


def test_mid_session_cefr_clear_reblocks_tutor() -> None:
    """Gate re-checked every Ready Tutor start after mid-session overall clear."""
    session = AsyncMock()

    async def _run() -> None:
        with (
            patch(
                "app.tutor.handoff.read_overall_cefr",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.tutor.handoff.get_ready_unit_chunks",
                new_callable=AsyncMock,
            ) as chunks,
        ):
            out = await handle_tutor(
                session,
                text="tutor_unit",
                prior_tutor={"active_unit_ref": f"{EF4_BEG_SB_ID}/1A"},
            )
        assert out.message == CEFR_MISSING
        assert out.ctas == CEFR_GATE_CTAS
        assert out.session_patch == {}
        assert out.emit_token_delta is False
        chunks.assert_not_awaited()

    asyncio.run(_run())


def test_teach_with_cg_respects_cefr_band() -> None:
    """CEFR×CG order: mini-context present and labeled with same overall/+1 ceiling."""
    from app.mixins.context_generator import LexiconEntry

    session = AsyncMock()
    unit_ref = f"{EF4_BEG_SB_ID}/1A"
    corpus = ReadyUnitCorpus(
        unit_ref=unit_ref,
        status="Ready",
        chunks=[
            ReadyChunk(
                ordinal=0,
                content="Hello practice.",
                embedding=[0.0] * 4,
                model_name="x",
                dims=4,
            )
        ],
    )

    async def _run() -> None:
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
                return_value=corpus,
            ),
            patch(
                "app.tutor.teach.fetch_lemma_entries",
                new_callable=AsyncMock,
                return_value=[
                    LexiconEntry(lemma="hello", definition="used as a greeting")
                ],
            ),
        ):
            out = await handle_tutor(session)
        assert out.emit_token_delta is True
        assert "[CEFR target: A2–B1]" in out.message
        assert "≤B1" in out.message
        assert "hello — used as a greeting" in out.message
        assert out.message.index("[CEFR target:") < out.message.index("Mini-context")

    asyncio.run(_run())
