"""Grounded one-turn RU teaching text + CEFR band + optional CG (§7.5 / §7.6)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.corpus.query import ReadyUnitCorpus
from app.mixins.cefr import format_band_annotation, resolve_target_band
from app.mixins.context_generator import (
    LexiconEntry,
    build_mini_context,
    candidate_lemmas_from_text,
    fetch_lemma_entries,
)
from app.schemas.cefr import CefrLevel

LexiconFetcher = Callable[[list[str]], Awaitable[list[LexiconEntry]]]


def grounded_teach_excerpts(corpus: ReadyUnitCorpus) -> str:
    """Build RU teaching body citing Ready unit chunks only (no invented lesson)."""
    excerpts = "\n\n".join(
        f"[{chunk.ordinal}] {chunk.content.strip()}" for chunk in corpus.chunks
    )
    return (
        f"Разберём unit {corpus.unit_ref} по материалу Students' Book "
        f"(Ready).\n\n{excerpts}\n\n"
        "Прочитай фрагменты выше и кратко ответь по-английски, опираясь на unit."
    )


def grounded_teach_message(corpus: ReadyUnitCorpus) -> str:
    """Backward-compatible grounded body without CEFR/CG (tests / callers)."""
    return grounded_teach_excerpts(corpus)


async def compose_teach_message(
    corpus: ReadyUnitCorpus,
    overall: CefrLevel,
    *,
    lexicon_fetcher: LexiconFetcher | None = None,
) -> str:
    """Compose teach turn: band annotation → grounded body → optional CG.

    Apply order: resolve band, append grounded excerpts, then generate/skip
    CEFR-ceiling-labeled CG under that band. Empty lexicon material skips CG;
    fetch failures propagate ``LexiconUnavailable``.
    """
    band = resolve_target_band(overall)
    if band is None:
        raise ValueError("compose_teach_message requires a valid overall CEFR")

    parts: list[str] = [
        format_band_annotation(band),
        grounded_teach_excerpts(corpus),
    ]

    lemmas = candidate_lemmas_from_text(
        " ".join(chunk.content for chunk in corpus.chunks)
    )
    fetcher = lexicon_fetcher if lexicon_fetcher is not None else fetch_lemma_entries
    material = await fetcher(lemmas) if lemmas else []
    cg = build_mini_context(material, band)
    if cg:
        parts.append(cg)

    return "\n\n".join(parts)
