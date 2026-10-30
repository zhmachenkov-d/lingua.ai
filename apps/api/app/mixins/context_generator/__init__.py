"""Context Generator mixin — mini-context from lexicon material (§7.6; AD-7)."""

from app.mixins.context_generator.generate import (
    LexiconEntry,
    build_mini_context,
    candidate_lemmas_from_text,
)
from app.mixins.context_generator.lexicon import (
    LexiconUnavailable,
    fetch_lemma_entries,
)

__all__ = [
    "LexiconEntry",
    "LexiconUnavailable",
    "build_mini_context",
    "candidate_lemmas_from_text",
    "fetch_lemma_entries",
]
