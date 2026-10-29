"""Api Alembic / LTM registry — re-export shared Base from lingua_corpus."""

from lingua_corpus import Base, created_at_col, updated_at_col, uuid_pk

__all__ = ["Base", "created_at_col", "updated_at_col", "uuid_pk"]
