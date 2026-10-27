import os
import uuid
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql


def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL", "").strip() or None


def _in_ci() -> bool:
    return bool(os.environ.get("CI", "").strip())


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
    # This conftest hook runs before `_pytest.mark` deselection; when CI selects
    # only unmarked tests, do not require DATABASE_URL for still-present marked items.
    markexpr = (config.option.markexpr or "").strip()
    if markexpr == "not integration_db":
        return
    url = _database_url()
    reason = "integration_db: DATABASE_URL not set (Compose db required) — NOT verified"
    if url:
        error = _reachable(url)
        if error is None:
            return
        reason = f"integration_db: Postgres unreachable ({error}) — NOT verified"
    if _in_ci():
        pytest.exit(f"CI: {reason}", returncode=1)
    for item in marked:
        item.add_marker(pytest.mark.skip(reason=reason))


def pytest_collection_finish(session) -> None:
    """Under CI, fail if a CI markexpr selected zero tests."""
    if not _in_ci():
        return
    markexpr = (session.config.option.markexpr or "").strip()
    # Exact match only — `not integration_db` must not satisfy `integration_db`.
    if markexpr == "integration_db":
        label = "integration_db"
    elif markexpr == "not integration_db":
        label = "non-integration_db"
    else:
        return
    if not session.items:
        pytest.exit(f"CI: zero {label} tests collected", returncode=1)


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
