"""Build CEFR-constrained EN mini-context from lexicon defs (no invented glosses)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from app.mixins.cefr.band import CefrBand

_WORD_RE: Final = re.compile(r"[A-Za-z][A-Za-z'-]{1,}", re.UNICODE)
_STOP: Final = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "from",
        "with",
        "by",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "this",
        "that",
        "it",
        "as",
        "we",
        "you",
        "they",
        "he",
        "she",
        "i",
        "my",
        "our",
        "your",
        "their",
        "unit",
        "ready",
        "book",
        "sb",
    }
)
_MAX_CANDIDATES: Final = 5
_MAX_DEF_CHARS: Final = 120


@dataclass(frozen=True, slots=True)
class LexiconEntry:
    """One lemma with non-empty Free Dictionary definition text only."""

    lemma: str
    definition: str


def candidate_lemmas_from_text(text: str, *, limit: int = _MAX_CANDIDATES) -> list[str]:
    """Unit-derived candidate lemmas for lexicon fetch (story 4 owns offer UX)."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _WORD_RE.finditer(text):
        lemma = match.group(0).casefold()
        if lemma in _STOP or lemma in seen:
            continue
        seen.add(lemma)
        out.append(lemma)
        if len(out) >= limit:
            break
    return out


def build_mini_context(
    material: list[LexiconEntry] | None,
    band: CefrBand,
) -> str | None:
    """Return CEFR-labeled EN mini-context, or None when material empty/null/absent.

    Uses API definitions only — never invents glosses. Band ceiling annotates
    the paragraph so CEFR constrains CG (no unconstrained bypass).
    """
    if not material:
        return None
    lines: list[str] = []
    for entry in material:
        gloss = entry.definition.strip()
        if not gloss:
            continue
        if len(gloss) > _MAX_DEF_CHARS:
            gloss = gloss[: _MAX_DEF_CHARS - 1].rstrip() + "…"
        lines.append(f"{entry.lemma} — {gloss}")
    if not lines:
        return None
    ceiling = band.ceiling
    body = "\n".join(lines)
    return (
        f"Mini-context (≤{ceiling} EN, grounded in dictionary defs):\n{body}"
    )
