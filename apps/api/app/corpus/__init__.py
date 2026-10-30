"""Read-only corpus query helpers for Tutor RAG consumers.

Public surface
--------------
``get_ready_unit_chunks(session, unit_ref)`` — async library call (no HTTP).

Returns ordinal-ordered Ready chunks with stamped embedding vectors when the
unit exists, ``status == "Ready"``, and the chunk⋈embedding join is non-empty.
Returns ``None`` for unknown, non-Ready, or Ready-with-empty-join ``unit_ref``
(not Tutor-usable). Read-only: never writes corpus tables and never re-embeds.
"""

from app.corpus.query import (
    ReadyChunk,
    ReadyUnitCorpus,
    UnitRow,
    get_ready_unit_chunks,
    get_unit_row,
)

__all__ = [
    "ReadyChunk",
    "ReadyUnitCorpus",
    "UnitRow",
    "get_ready_unit_chunks",
    "get_unit_row",
]
