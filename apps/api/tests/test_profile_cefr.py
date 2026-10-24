"""LearnerProfile CEFR write path — integration_db round-trips (story 1.4)."""

from collections.abc import Iterator

import psycopg
import pytest
from app.db.constants import MVP_LEARNER_ID
from app.main import app
from fastapi.testclient import TestClient


def _profile_count(url: str) -> int:
    with psycopg.connect(url) as conn:
        row = conn.execute("SELECT count(*) FROM learner_profile").fetchone()
    assert row is not None
    return int(row[0])


def _cefr_raw(url: str) -> dict | None:
    with psycopg.connect(url) as conn:
        row = conn.execute(
            "SELECT cefr_by_skill FROM learner_profile WHERE id = %s",
            (str(MVP_LEARNER_ID),),
        ).fetchone()
    if row is None:
        return None
    return dict(row[0])


@pytest.fixture
def profile_client(
    fresh_db_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", fresh_db_url)
    with TestClient(app) as client:
        yield client


@pytest.mark.integration_db
def test_get_before_write_returns_empty_map_without_insert(
    profile_client: TestClient, fresh_db_url: str
) -> None:
    response = profile_client.get("/profile/cefr")
    assert response.status_code == 200
    assert response.json() == {}
    assert "overall" not in response.json()
    assert _profile_count(fresh_db_url) == 0


@pytest.mark.integration_db
def test_put_then_get_round_trip_with_vocab(
    profile_client: TestClient, fresh_db_url: str
) -> None:
    body = {
        "overall": "B1",
        "reading": "B1",
        "listening": "A2",
        "speaking": "A2",
        "writing": "B1",
        "vocab": "A2",
    }
    put = profile_client.put("/profile/cefr", json=body)
    assert put.status_code == 204
    assert put.content == b""

    get = profile_client.get("/profile/cefr")
    assert get.status_code == 200
    assert get.json() == body
    assert _cefr_raw(fresh_db_url) == body
    assert _profile_count(fresh_db_url) == 1


@pytest.mark.integration_db
def test_put_overall_only_omits_skills(
    profile_client: TestClient, fresh_db_url: str
) -> None:
    assert (
        profile_client.put("/profile/cefr", json={"overall": "A1"}).status_code == 204
    )
    assert profile_client.get("/profile/cefr").json() == {"overall": "A1"}
    assert _cefr_raw(fresh_db_url) == {"overall": "A1"}


@pytest.mark.integration_db
def test_empty_overall_detectable_via_omit_or_null(
    profile_client: TestClient, fresh_db_url: str
) -> None:
    assert (
        profile_client.put(
            "/profile/cefr", json={"overall": "B2", "reading": "B1"}
        ).status_code
        == 204
    )

    omit = profile_client.put("/profile/cefr", json={"reading": "A2"})
    assert omit.status_code == 204
    cleared = profile_client.get("/profile/cefr").json()
    assert "overall" not in cleared
    assert cleared == {"reading": "A2"}
    assert "overall" not in (_cefr_raw(fresh_db_url) or {})

    null_overall = profile_client.put(
        "/profile/cefr", json={"overall": None, "listening": "B1"}
    )
    assert null_overall.status_code == 204

    again = profile_client.get("/profile/cefr").json()
    assert "overall" not in again
    assert again == {"listening": "B1"}


@pytest.mark.integration_db
def test_invalid_cefr_token_rejects_and_leaves_db_unchanged(
    profile_client: TestClient, fresh_db_url: str
) -> None:
    good = {"overall": "A1"}
    assert profile_client.put("/profile/cefr", json=good).status_code == 204

    bad = profile_client.put("/profile/cefr", json={"overall": "A2+"})
    assert bad.status_code == 422
    assert profile_client.get("/profile/cefr").json() == good
    assert _cefr_raw(fresh_db_url) == good


@pytest.mark.integration_db
def test_unknown_map_key_rejects_and_leaves_db_unchanged(
    profile_client: TestClient, fresh_db_url: str
) -> None:
    good = {"overall": "B1", "vocab": "A2"}
    assert profile_client.put("/profile/cefr", json=good).status_code == 204

    bad = profile_client.put("/profile/cefr", json={"overall": "B1", "grammar": "A1"})
    assert bad.status_code == 422
    assert profile_client.get("/profile/cefr").json() == good
    assert _cefr_raw(fresh_db_url) == good


@pytest.mark.integration_db
def test_dual_put_full_replace_single_row(
    profile_client: TestClient, fresh_db_url: str
) -> None:
    first = {
        "overall": "A1",
        "reading": "A1",
        "listening": "A1",
        "speaking": "A1",
        "writing": "A1",
        "vocab": "A1",
    }
    second = {"overall": "C1", "vocab": "B2"}
    assert profile_client.put("/profile/cefr", json=first).status_code == 204
    assert profile_client.put("/profile/cefr", json=second).status_code == 204
    assert profile_client.get("/profile/cefr").json() == second
    assert _cefr_raw(fresh_db_url) == second
    assert _profile_count(fresh_db_url) == 1


@pytest.mark.integration_db
def test_put_does_not_wipe_other_profile_columns(
    profile_client: TestClient, fresh_db_url: str
) -> None:
    with psycopg.connect(fresh_db_url) as conn:
        conn.execute(
            "INSERT INTO learner_profile (id, cefr_by_skill, goals, constraints) "
            "VALUES (%s, '{}'::jsonb, ARRAY['fluency'], "
            "'{\"max_minutes\": 20}'::jsonb)",
            (str(MVP_LEARNER_ID),),
        )
        conn.commit()

    assert (
        profile_client.put("/profile/cefr", json={"overall": "B1"}).status_code == 204
    )
    with psycopg.connect(fresh_db_url) as conn:
        row = conn.execute(
            "SELECT cefr_by_skill, goals, constraints FROM learner_profile "
            "WHERE id = %s",
            (str(MVP_LEARNER_ID),),
        ).fetchone()
    assert row is not None
    assert dict(row[0]) == {"overall": "B1"}
    assert list(row[1]) == ["fluency"]
    assert dict(row[2]) == {"max_minutes": 20}
