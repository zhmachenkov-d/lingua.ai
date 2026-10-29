"""Read-only corpus query helpers for Tutor RAG consumers.

Public surface
--------------
``get_ready_unit_chunks(session, unit_ref)`` — async library call (no HTTP).

Returns ordinal-ordered Ready chunks with stamped embedding vectors when the
unit exists and ``status == "Ready"``. Returns ``None`` for unknown or
non-Ready ``unit_ref`` (not Tutor-usable). Read-only: never writes corpus
tables and never re-embeds.
"""

from app.corpus.query import ReadyChunk, ReadyUnitCorpus, get_ready_unit_chunks

__all__ = [
    "ReadyChunk",
    "ReadyUnitCorpus",
    "get_ready_unit_chunks",
]
