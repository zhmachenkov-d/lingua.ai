"""Grounded one-turn RU teaching text from Ready chunks (no invented lesson)."""

from __future__ import annotations

from app.corpus.query import ReadyUnitCorpus


def grounded_teach_message(corpus: ReadyUnitCorpus) -> str:
    """Build one RU teaching turn citing the Ready unit and its chunk text.

    Uses only retrieved chunk content — never invents material beyond the unit.
    """
    excerpts = "\n\n".join(
        f"[{chunk.ordinal}] {chunk.content.strip()}" for chunk in corpus.chunks
    )
    return (
        f"Разберём unit {corpus.unit_ref} по материалу Students' Book "
        f"(Ready).\n\n{excerpts}\n\n"
        "Прочитай фрагменты выше и кратко ответь по-английски, опираясь на unit."
    )
