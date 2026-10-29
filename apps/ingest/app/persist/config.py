"""Postgres URL helpers mirrored from ``apps/api/app/db/config.py``.

Ingest must never import ``apps.api`` — keep this copy in sync by column contract.
"""

from __future__ import annotations

import os
from urllib.parse import quote


class DatabaseConfigError(RuntimeError):
    pass


_COMPONENT_KEYS = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
)


def _build_url_from_components() -> str | None:
    values = {key: os.environ.get(key, "").strip() for key in _COMPONENT_KEYS}
    if not any(values.values()):
        return None
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise DatabaseConfigError(
            "incomplete Postgres URL components for DATABASE_URL construction "
            f"(missing {', '.join(missing)}); set an explicit DATABASE_URL or "
            f"all of {', '.join(_COMPONENT_KEYS)} as raw secrets — ingest "
            "percent-encodes user/password/db when building the URL"
        )
    user = quote(values["POSTGRES_USER"], safe="")
    password = quote(values["POSTGRES_PASSWORD"], safe="")
    db = quote(values["POSTGRES_DB"], safe="")
    host = values["POSTGRES_HOST"]
    return f"postgresql://{user}:{password}@{host}:5432/{db}"


def get_database_url() -> str:
    """Compose-style ``postgresql://`` URL (psycopg3).

    Prefer an explicit ``DATABASE_URL``. Otherwise build from
    ``POSTGRES_USER`` / ``POSTGRES_PASSWORD`` / ``POSTGRES_DB`` / ``POSTGRES_HOST``.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    built = _build_url_from_components()
    if built:
        return built
    raise DatabaseConfigError(
        "DATABASE_URL is not set and Postgres URL components are missing; "
        "ingest cannot write Ready without Postgres. Compose should pass "
        f"{', '.join(_COMPONENT_KEYS)} as raw secrets (ingest percent-encodes "
        "user/password/db when building the URL) or set an explicit DATABASE_URL"
    )


def to_sqlalchemy_url(url: str) -> str:
    """Derive the SQLAlchemy psycopg3 URL from the single Compose URL."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url
