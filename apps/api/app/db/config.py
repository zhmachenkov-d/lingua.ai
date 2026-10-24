import os


class DatabaseConfigError(RuntimeError):
    pass


def get_database_url() -> str:
    """Compose-style `postgresql://` URL (psycopg3 / AsyncPostgresSaver)."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseConfigError(
            "DATABASE_URL is not set; the api cannot bootstrap without Postgres"
        )
    return url


def to_sqlalchemy_url(url: str) -> str:
    """Derive the SQLAlchemy psycopg3 URL from the single Compose URL."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url
