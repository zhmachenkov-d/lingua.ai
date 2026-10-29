"""Shared corpus ORM for api and ingest (never imports apps.api)."""

from lingua_corpus.base import Base, created_at_col, updated_at_col, uuid_pk
from lingua_corpus.models import (
    EMBEDDING_DIMS,
    UNIT_STATUSES,
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
    "created_at_col",
    "updated_at_col",
    "uuid_pk",
]
