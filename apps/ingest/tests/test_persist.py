from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.persist.config import DatabaseConfigError, get_database_url, to_sqlalchemy_url
from app.persist.store import (
    EF4_BEG_SB_TITLE,
    EF4_BEG_WB_TITLE,
    REQUIRED_TABLES,
    CorpusSchemaMissing,
    ensure_corpus_schema,
    has_ready_unit,
    list_ready_unit_refs,
    title_for_textbook,
    upsert_not_ready_unit,
    upsert_ready_unit,
    upsert_review_unit,
    upsert_textbook,
)
from lingua_ids import EMBEDDING_DIMS, EMBEDDING_MODEL_NAME


def test_to_sqlalchemy_url() -> None:
    assert (
        to_sqlalchemy_url("postgresql://u:p@db:5432/lingua")
        == "postgresql+psycopg://u:p@db:5432/lingua"
    )


def test_get_database_url_from_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss")
    monkeypatch.setenv("POSTGRES_DB", "lingua")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    url = get_database_url()
    assert url.startswith("postgresql://")
    assert "p%40ss" in url
    assert "@db:5432/" in url


def test_get_database_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for key in (
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_HOST",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(DatabaseConfigError):
        get_database_url()


def test_ensure_corpus_schema_missing() -> None:
    session = MagicMock()
    bind = MagicMock()
    session.get_bind.return_value = bind
    with patch("app.persist.store.inspect") as insp:
        insp.return_value.get_table_names.return_value = ["textbook"]
        with pytest.raises(CorpusSchemaMissing, match="0003"):
            ensure_corpus_schema(session)


def test_ensure_corpus_schema_ok() -> None:
    session = MagicMock()
    bind = MagicMock()
    session.get_bind.return_value = bind
    with patch("app.persist.store.inspect") as insp:
        insp.return_value.get_table_names.return_value = list(REQUIRED_TABLES)
        ensure_corpus_schema(session)


def test_upsert_not_ready_and_ready_paths() -> None:
    """Exercise store helpers against an in-memory fake session surface."""
    from app.persist.models import Textbook, TextbookUnit

    stored: dict[str, Any] = {"textbook": None, "unit": None, "chunks": []}

    class FakeSession:
        def get(self, model, key):  # noqa: ANN001
            if model is Textbook and stored["textbook"] and stored["textbook"].id == key:
                return stored["textbook"]
            return None

        def add(self, obj) -> None:  # noqa: ANN001
            if isinstance(obj, Textbook):
                stored["textbook"] = obj
            elif isinstance(obj, TextbookUnit):
                stored["unit"] = obj
            else:
                stored["chunks"].append(obj)

        def flush(self) -> None:
            if stored["unit"] is not None and getattr(stored["unit"], "id", None) is None:
                stored["unit"].id = "unit-1"

        def scalar(self, stmt):  # noqa: ANN001
            del stmt
            return stored["unit"]

        def scalars(self, stmt):  # noqa: ANN001
            del stmt
            return MagicMock(all=lambda: [])

        def execute(self, *args, **kwargs):  # noqa: ANN001, ANN003
            del args, kwargs
            return MagicMock()

        def get_bind(self):
            return MagicMock()

    session = FakeSession()
    with (
        patch("app.persist.store.ensure_corpus_schema"),
        patch("app.persist.store.select", return_value=MagicMock()),
        patch("app.persist.store.delete", return_value=MagicMock()),
    ):
        unit = upsert_not_ready_unit(
            session,  # type: ignore[arg-type]
            textbook_id="ef4-beg-sb",
            unit_ref="ef4-beg-sb/1A",
            gate_reason="mean_chars_per_page",
            gate_metrics={"mean_chars_per_page": 10.0},
        )
        assert unit.status == "NotReady"
        assert unit.gate_reason == "mean_chars_per_page"

        ready = upsert_ready_unit(
            session,  # type: ignore[arg-type]
            textbook_id="ef4-beg-sb",
            unit_ref="ef4-beg-sb/1A",
            gate_metrics={"mean_chars_per_page": 500.0},
            chunk_texts=["hello"],
            embeddings=[[0.1] * EMBEDDING_DIMS],
            model_name=EMBEDDING_MODEL_NAME,
            dims=EMBEDDING_DIMS,
        )
        assert ready.status == "Ready"
        assert ready.gate_reason is None
        assert any(type(c).__name__ == "Chunk" for c in stored["chunks"])
        assert any(type(c).__name__ == "Embedding" for c in stored["chunks"])


def test_upsert_review_clears_chunks_and_status() -> None:
    from app.persist.models import Textbook, TextbookUnit

    stored: dict[str, Any] = {"textbook": None, "unit": None, "chunks": []}
    clear_calls = {"n": 0}

    class FakeSession:
        def get(self, model, key):  # noqa: ANN001
            if model is Textbook and stored["textbook"] and stored["textbook"].id == key:
                return stored["textbook"]
            return None

        def add(self, obj) -> None:  # noqa: ANN001
            if isinstance(obj, Textbook):
                stored["textbook"] = obj
            elif isinstance(obj, TextbookUnit):
                stored["unit"] = obj
            else:
                stored["chunks"].append(obj)

        def flush(self) -> None:
            if stored["unit"] is not None and getattr(stored["unit"], "id", None) is None:
                stored["unit"].id = "unit-1"

        def scalar(self, stmt):  # noqa: ANN001
            del stmt
            return stored["unit"]

        def scalars(self, stmt):  # noqa: ANN001
            del stmt
            return MagicMock(all=lambda: [])

        def execute(self, *args, **kwargs):  # noqa: ANN001, ANN003
            del args, kwargs
            clear_calls["n"] += 1
            return MagicMock()

        def get_bind(self):
            return MagicMock()

    session = FakeSession()
    with (
        patch("app.persist.store.ensure_corpus_schema"),
        patch("app.persist.store.select", return_value=MagicMock()),
        patch("app.persist.store.delete", return_value=MagicMock()),
        patch(
            "app.persist.store._clear_unit_chunks",
            side_effect=lambda s, u: clear_calls.__setitem__("n", clear_calls["n"] + 1),
        ),
    ):
        unit = upsert_review_unit(
            session,  # type: ignore[arg-type]
            textbook_id="ef4-beg-sb",
            unit_ref="ef4-beg-sb/1A",
            gate_reason="image_area_soft",
            gate_metrics={
                "image_area_ratio": 0.85,
                "mean_chars_per_page": 10.0,
            },
        )
    assert unit.status == "Review"
    assert unit.gate_reason == "image_area_soft"
    assert unit.gate_metrics["image_area_ratio"] == 0.85
    assert clear_calls["n"] >= 1
    assert not any(type(c).__name__ == "Chunk" for c in stored["chunks"])


def test_upsert_ready_requires_chunks() -> None:
    session = MagicMock()
    with (
        patch("app.persist.store.ensure_corpus_schema"),
        patch("app.persist.store.upsert_textbook"),
        patch("app.persist.store._get_or_create_unit"),
    ):
        with pytest.raises(ValueError, match="at least one"):
            upsert_ready_unit(
                session,
                textbook_id="ef4-beg-sb",
                unit_ref="ef4-beg-sb/1A",
                gate_metrics={},
                chunk_texts=[],
                embeddings=[],
                model_name=EMBEDDING_MODEL_NAME,
                dims=EMBEDDING_DIMS,
            )


def test_title_for_textbook_by_id() -> None:
    assert title_for_textbook("ef4-beg-sb") == EF4_BEG_SB_TITLE
    assert title_for_textbook("ef4-beg-wb") == EF4_BEG_WB_TITLE
    assert title_for_textbook("unknown-book") == "unknown-book"


def test_upsert_textbook_uses_wb_title() -> None:
    from app.persist.models import Textbook

    stored: dict[str, Any] = {"textbook": None}

    class FakeSession:
        def get(self, model, key):  # noqa: ANN001
            if model is Textbook and stored["textbook"] and stored["textbook"].id == key:
                return stored["textbook"]
            return None

        def add(self, obj) -> None:  # noqa: ANN001
            if isinstance(obj, Textbook):
                stored["textbook"] = obj

        def flush(self) -> None:
            return None

        def get_bind(self):
            return MagicMock()

    session = FakeSession()
    with patch("app.persist.store.ensure_corpus_schema"):
        row = upsert_textbook(session, textbook_id="ef4-beg-wb")  # type: ignore[arg-type]
    assert row.id == "ef4-beg-wb"
    assert row.title == EF4_BEG_WB_TITLE


def test_has_ready_and_list_ready_filter_by_textbook() -> None:
    """SB DoD helper must not treat WB-only Ready as Tutor Ready."""
    session = MagicMock()
    with (
        patch("app.persist.store.ensure_corpus_schema"),
        patch("app.persist.store.select", return_value=MagicMock()),
    ):
        session.scalar.return_value = None
        session.scalars.return_value = MagicMock(all=lambda: [])
        assert has_ready_unit(session, "ef4-beg-sb") is False
        assert list_ready_unit_refs(session, "ef4-beg-sb") == []

        session.scalar.return_value = "ef4-beg-wb/1A"
        session.scalars.return_value = MagicMock(all=lambda: ["ef4-beg-wb/1A"])
        assert has_ready_unit(session, "ef4-beg-wb") is True
        assert list_ready_unit_refs(session, "ef4-beg-wb") == ["ef4-beg-wb/1A"]

        # SB-filtered view stays empty when only WB Ready was queried separately.
        session.scalar.return_value = None
        session.scalars.return_value = MagicMock(all=lambda: [])
        assert has_ready_unit(session, "ef4-beg-sb") is False
        assert list_ready_unit_refs(session, "ef4-beg-sb") == []

