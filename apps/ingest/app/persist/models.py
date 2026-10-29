"""Corpus ORM — re-export shared lingua_corpus definitions. Never import apps.api."""

from lingua_corpus import (
    EMBEDDING_DIMS,
    UNIT_STATUSES,
    Base,
    Chunk,
    Embedding,
    Textbook,
    TextbookUnit,
)

__all__ = [
    "EMBEDDING_DIMS",
    "UNIT_STATUSES",
    "Base",
    "Chunk",
    "Embedding",
    "Textbook",
    "TextbookUnit",
]
