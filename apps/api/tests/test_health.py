from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from fastapi.testclient import TestClient


def _fake_engine(*, connect_error: BaseException | None = None):
    engine = MagicMock()
    if connect_error is not None:
        engine.connect.side_effect = connect_error
        return engine, None

    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _connect():
        yield conn

    engine.connect = MagicMock(side_effect=_connect)
    return engine, conn


def test_health_returns_ok() -> None:
    with patch("app.main.bootstrap", new_callable=AsyncMock) as mock_boot:
        with TestClient(app) as client:
            response = client.get("/health")
        mock_boot.assert_awaited()
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok_when_db_reachable() -> None:
    engine, conn = _fake_engine()
    with (
        patch("app.main.bootstrap", new_callable=AsyncMock),
        patch("app.db.session.get_engine", return_value=engine),
    ):
        with TestClient(app) as client:
            response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert conn is not None
    conn.execute.assert_awaited()
    assert str(conn.execute.await_args.args[0]) == "SELECT 1"


def test_ready_fails_when_db_unreachable() -> None:
    engine, _ = _fake_engine(connect_error=OSError("simulated db down"))
    with (
        patch("app.main.bootstrap", new_callable=AsyncMock),
        patch("app.db.session.get_engine", return_value=engine),
    ):
        with TestClient(app) as client:
            # Real probe path: /ready → probe_database → get_engine().connect().
            # Liveness stays up; readiness must fail so orchestrators stop routing.
            health = client.get("/health")
            ready = client.get("/ready")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable"}
