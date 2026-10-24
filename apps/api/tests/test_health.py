from unittest.mock import AsyncMock, patch

from app.main import app
from fastapi.testclient import TestClient


def test_health_returns_ok() -> None:
    with patch("app.main.bootstrap", new_callable=AsyncMock) as mock_boot:
        with TestClient(app) as client:
            response = client.get("/health")
        mock_boot.assert_awaited()
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
