"""Corpus Ready + embedding schema (story 2.2) + shared ORM SoT (bug 33)."""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

import psycopg
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db.bootstrap import bootstrap
from app.db.config import to_sqlalchemy_url
from app.models import Base, Chunk, Embedding, Textbook, TextbookUnit
from app.models.embedding import EMBEDDING_DIMS
from lingua_corpus import Chunk as SharedChunk
from lingua_corpus import Embedding as SharedEmbedding
from lingua_corpus import Textbook as SharedTextbook
from lingua_corpus import TextbookUnit as SharedTextbookUnit
from lingua_ids import EF4_BEG_SB_ID, EF4_BEG_WB_ID, MVP_TEXTBOOK_IDS
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "apps" / "api"
INGEST_ROOT = REPO_ROOT / "apps" / "ingest"

CORPUS_TABLES = {"textbook", "textbook_unit", "chunk", "embedding"}
CORPUS_CLASS_NAMES = ("Textbook", "TextbookUnit", "Chunk", "Embedding")
# Ingest must never import the api application package (apps.api or api's app.*).
_API_APP_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(?:apps\.api\b|app\.(?:models|corpus|db|main)\b)",
    re.M,
)


@pytest.fixture
def migrated_url(fresh_db_url: str) -> str:
    asyncio.run(bootstrap(fresh_db_url, lock_timeout=10))
    return fresh_db_url


def test_shared_textbook_ids() -> None:
    assert EF4_BEG_SB_ID == "ef4-beg-sb"
    assert EF4_BEG_WB_ID == "ef4-beg-wb"
    assert MVP_TEXTBOOK_IDS == frozenset({EF4_BEG_SB_ID, EF4_BEG_WB_ID})


def test_corpus_orm_is_shared_lingua_corpus_definition() -> None:
    """AC4: both apps resolve the four corpus ORM types from lingua_corpus."""
    assert Textbook is SharedTextbook
    assert TextbookUnit is SharedTextbookUnit
    assert Chunk is SharedChunk
    assert Embedding is SharedEmbedding

    persist_models = (INGEST_ROOT / "app" / "persist" / "models.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(persist_models)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in CORPUS_CLASS_NAMES:
            raise AssertionError(
                "ingest persist/models.py must not define a local corpus class "
                f"{node.name!r}; import from lingua_corpus"
            )

    # Persist sources must pull the four tables from the shared package.
    assert re.search(
        r"from\s+lingua_corpus\s+import\b",
        persist_models,
    ), "ingest persist/models.py must import corpus ORM from lingua_corpus"


def test_ingest_does_not_import_api_application_package() -> None:
    """AC4: ingest must not depend on the api application package."""
    ingest_app = INGEST_ROOT / "app"
    for path in ingest_app.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        match = _API_APP_IMPORT_RE.search(text)
        assert match is None, (
            f"ingest must not import api application package: "
            f"{path.relative_to(REPO_ROOT)} ({match.group(0)!r})"
        )


def test_api_has_no_corpus_write_path_and_ingest_has_no_alembic() -> None:
    """AC: api does not write corpus tables; ingest has no migration runner.

    Ingest may *mention* Alembic in operator-facing errors (run api / upgrade
    head first); it must not ship an alembic env or import the alembic package.
    """
    api_app = API_ROOT / "app"
    for path in api_app.rglob("*.py"):
        if "models" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if not any(name in text for name in CORPUS_CLASS_NAMES):
            continue
        assert not re.search(r"session\.(add|add_all|merge|delete)", text, re.I), (
            f"corpus write path in {path.relative_to(REPO_ROOT)}"
        )

    assert not (INGEST_ROOT / "alembic").exists()
    assert not (INGEST_ROOT / "alembic.ini").exists()
    ingest_app = INGEST_ROOT / "app"
    for path in ingest_app.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+alembic\b", text, re.M | re.I), (
            f"ingest must not import alembic: {path.relative_to(REPO_ROOT)}"
        )


@pytest.mark.integration_db
def test_corpus_tables_and_vector_dims(migrated_url: str) -> None:
    with psycopg.connect(migrated_url) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ).fetchall()
        }
        assert CORPUS_TABLES <= tables

        ext = conn.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        assert ext is not None

        row = conn.execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'embedding'
              AND a.attname = 'embedding'
              AND a.attnum > 0
              AND NOT a.attisdropped
            """
        ).fetchone()
        assert row is not None
        assert row[0] == f"vector({EMBEDDING_DIMS})"


@pytest.mark.integration_db
def test_not_ready_gate_metrics_round_trip(migrated_url: str) -> None:
    engine = create_engine(to_sqlalchemy_url(migrated_url))
    metrics = {"mean_chars_per_page": 12.5, "printable_ratio": 0.5}
    try:
        with Session(engine) as session:
            session.add(Textbook(id=EF4_BEG_SB_ID, title="EF4 Beginner SB"))
            session.flush()
            unit = TextbookUnit(
                textbook_id=EF4_BEG_SB_ID,
                unit_ref=f"{EF4_BEG_SB_ID}/1A",
                status="NotReady",
                gate_reason="mean_chars_per_page",
                gate_metrics=metrics,
            )
            session.add(unit)
            session.commit()
            unit_id = unit.id

        with Session(engine) as session:
            loaded = session.scalar(
                select(TextbookUnit).where(TextbookUnit.id == unit_id)
            )
            assert loaded is not None
            assert loaded.status == "NotReady"
            assert loaded.gate_metrics == metrics
            assert loaded.gate_reason == "mean_chars_per_page"
    finally:
        engine.dispose()


@pytest.mark.integration_db
def test_corpus_models_match_migration(migrated_url: str) -> None:
    engine = create_engine(to_sqlalchemy_url(migrated_url))
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "include_object": lambda obj, name, type_, reflected, compare_to: (
                        type_ != "table" or name in Base.metadata.tables
                    ),
                },
            )
            diff = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()
    assert diff == []
