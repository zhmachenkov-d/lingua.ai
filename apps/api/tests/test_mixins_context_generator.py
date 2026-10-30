"""Context Generator mixin — skip / build / lexicon fail triad (§7.6)."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.corpus.query import ReadyChunk, ReadyUnitCorpus
from app.mixins.cefr import resolve_target_band
from app.mixins.context_generator import (
    LexiconEntry,
    LexiconUnavailable,
    build_mini_context,
    candidate_lemmas_from_text,
    fetch_lemma_entries,
)
from app.tutor.teach import compose_teach_message
from hypothesis import given
from hypothesis import strategies as st
from lingua_ids import EF4_BEG_SB_ID


@given(
    material=st.one_of(
        st.none(),
        st.just([]),
        st.lists(
            st.builds(
                LexiconEntry,
                lemma=st.just("x"),
                definition=st.just("   "),
            ),
            max_size=3,
        ),
    )
)
def test_empty_null_absent_material_skips_cg(
    material: list[LexiconEntry] | None,
) -> None:
    band = resolve_target_band("A2")
    assert band is not None
    assert build_mini_context(material, band) is None


def test_build_mini_context_uses_defs_only_under_band() -> None:
    band = resolve_target_band("A2")
    assert band is not None
    text = build_mini_context(
        [LexiconEntry(lemma="hello", definition="used as a greeting")],
        band,
    )
    assert text is not None
    assert "hello — used as a greeting" in text
    assert "≤B1" in text
    assert "invented" not in text.casefold()


def test_candidate_lemmas_skips_stopwords() -> None:
    lemmas = candidate_lemmas_from_text("The hello and world from Ready SB.")
    assert "hello" in lemmas
    assert "world" in lemmas
    assert "the" not in lemmas
    assert "and" not in lemmas
    assert "from" not in lemmas


def test_fetch_lemma_entries_empty_input_skips() -> None:
    assert asyncio.run(fetch_lemma_entries([])) == []


def test_fetch_lemma_entries_404_is_empty_not_error() -> None:
    async def _run() -> None:
        response = httpx.Response(
            404, request=httpx.Request("GET", "https://example.com")
        )
        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        assert await fetch_lemma_entries(["zzzunknown"], client=client) == []

    asyncio.run(_run())


def test_fetch_lemma_entries_429_raises() -> None:
    async def _run() -> None:
        response = httpx.Response(
            429, request=httpx.Request("GET", "https://example.com")
        )
        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        with pytest.raises(LexiconUnavailable):
            await fetch_lemma_entries(["hello"], client=client)

    asyncio.run(_run())


def test_fetch_lemma_entries_transport_raises() -> None:
    async def _run() -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(LexiconUnavailable):
            await fetch_lemma_entries(["hello"], client=client)

    asyncio.run(_run())


def test_fetch_lemma_entries_success_parses_definition() -> None:
    async def _run() -> None:
        payload = [
            {
                "word": "hello",
                "meanings": [
                    {"definitions": [{"definition": "used as a greeting"}]}
                ],
            }
        ]
        response = httpx.Response(
            200,
            json=payload,
            request=httpx.Request("GET", "https://example.com"),
        )
        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        entries = await fetch_lemma_entries(["hello"], client=client)
        assert entries == [
            LexiconEntry(lemma="hello", definition="used as a greeting")
        ]

    asyncio.run(_run())


def test_compose_teach_cefr_then_cg_order() -> None:
    async def _run() -> None:
        corpus = ReadyUnitCorpus(
            unit_ref=f"{EF4_BEG_SB_ID}/1A",
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

        async def _fetcher(_lemmas: list[str]) -> list[LexiconEntry]:
            return [LexiconEntry(lemma="hello", definition="used as a greeting")]

        msg = await compose_teach_message(corpus, "A2", lexicon_fetcher=_fetcher)
        assert "[CEFR target: A2–B1]" in msg
        assert "Hello practice." in msg
        assert "hello — used as a greeting" in msg
        assert "≤B1" in msg
        assert msg.index("[CEFR target:") < msg.index("Hello practice.")
        assert msg.index("Hello practice.") < msg.index("Mini-context")

    asyncio.run(_run())


def test_compose_teach_skips_cg_when_lexicon_empty() -> None:
    async def _run() -> None:
        corpus = ReadyUnitCorpus(
            unit_ref=f"{EF4_BEG_SB_ID}/1A",
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

        async def _empty(_lemmas: list[str]) -> list[LexiconEntry]:
            return []

        msg = await compose_teach_message(corpus, "B1", lexicon_fetcher=_empty)
        assert "[CEFR target: B1–B2]" in msg
        assert "Mini-context" not in msg
        assert "Hello practice." in msg

    asyncio.run(_run())


def test_compose_teach_propagates_lexicon_unavailable() -> None:
    async def _run() -> None:
        corpus = ReadyUnitCorpus(
            unit_ref=f"{EF4_BEG_SB_ID}/1A",
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

        async def _fail(_lemmas: list[str]) -> list[LexiconEntry]:
            raise LexiconUnavailable("429")

        with pytest.raises(LexiconUnavailable):
            await compose_teach_message(corpus, "A1", lexicon_fetcher=_fail)

    asyncio.run(_run())


def test_mixins_have_no_router_ui_session_imports() -> None:
    """AD-7 surface: mixins must not import Router, UI, or Session writers."""
    root = Path(__file__).resolve().parents[1] / "app" / "mixins"
    forbidden_prefixes = (
        "app.router",
        "app.api",
        "app.tutor",
        "langgraph",
    )
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for prefix in forbidden_prefixes:
                        assert not alias.name.startswith(prefix), path
            elif isinstance(node, ast.ImportFrom) and node.module:
                for prefix in forbidden_prefixes:
                    assert not node.module.startswith(prefix), path
                assert node.module != "app.models.session"
                assert "checkpointer" not in (node.module or "")


def test_handle_turn_maps_lexicon_unavailable_to_ws_error() -> None:
    from app.router.turn import ERROR_MESSAGES, TurnError, handle_turn

    async def _run() -> None:
        with (
            patch(
                "app.router.turn.get_turn_snapshot",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.router.turn._is_tutor_session_turn",
                return_value=True,
            ),
            patch(
                "app.router.turn.handle_tutor",
                new_callable=AsyncMock,
                side_effect=LexiconUnavailable("429"),
            ),
            patch(
                "app.router.turn._learner_db_session",
            ) as db_ctx,
        ):
            session = MagicMock()
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=session)
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await handle_turn("tutor_unit")
        assert isinstance(result, TurnError)
        assert result.code == "lexicon_unavailable"
        assert result.message == ERROR_MESSAGES["lexicon_unavailable"]
        assert "Словарь" in result.message

    asyncio.run(_run())
