import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from urllib.parse import urlsplit, urlunsplit


def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL", "").strip() or None


def _reachable(url: str) -> str | None:
    try:
        with psycopg.connect(url, connect_timeout=3):
            return None
    except psycopg.Error as exc:
        return str(exc).strip()


def pytest_collection_modifyitems(config, items) -> None:
    marked = [i for i in items if "integration_db" in i.keywords]
    if not marked:
        return
    url = _database_url()
    reason = "integration_db: DATABASE_URL not set (Compose db required) — NOT verified"
    if url:
        error = _reachable(url)
        if error is None:
            return
        reason = f"integration_db: Postgres unreachable ({error}) — NOT verified"
    for item in marked:
        item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture
def fresh_db_url() -> Iterator[str]:
    """A brand-new empty database on the Compose server, dropped afterwards."""
    base = _database_url()
    assert base
    name = f"lingua_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = urlunsplit(urlsplit(base)._replace(path=f"/{name}"))
    try:
        yield url
    finally:
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(name)
                )
            )
