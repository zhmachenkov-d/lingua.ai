from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.persist.config import get_database_url, to_sqlalchemy_url
from app.persist.models import Chunk, Embedding, Textbook, TextbookUnit

logger = logging.getLogger(__name__)

REQUIRED_TABLES = frozenset({"textbook", "textbook_unit", "chunk", "embedding"})

EF4_BEG_SB_TITLE = "English File 4th edition Beginner Students' Book"


class CorpusSchemaMissing(RuntimeError):
    """Raised when 0003 corpus tables are absent — refuse Ready mint."""


@dataclass(frozen=True, slots=True)
class SmokeRow:
    unit_ref: str
    status: str
    dims: int | None
    model_name: str | None


def session_factory(url: str | None = None) -> tuple[Engine, sessionmaker[Session]]:
    db_url = url if url is not None else get_database_url()
    engine = create_engine(to_sqlalchemy_url(db_url))
    return engine, sessionmaker(engine, expire_on_commit=False)


def ensure_corpus_schema(session: Session) -> None:
    """Refuse writes when story 2.2 / 0003 tables are missing."""
    bind = session.get_bind()
    insp = inspect(bind)
    present = set(insp.get_table_names())
    missing = sorted(REQUIRED_TABLES - present)
    if missing:
        raise CorpusSchemaMissing(
            "corpus schema missing (expected Alembic 0003 tables); "
            f"absent: {', '.join(missing)}. "
            "Bring up api once or run `alembic upgrade head` before ingest tracer."
        )


def upsert_textbook(
    session: Session,
    *,
    textbook_id: str,
    title: str = EF4_BEG_SB_TITLE,
) -> Textbook:
    ensure_corpus_schema(session)
    row = session.get(Textbook, textbook_id)
    if row is None:
        row = Textbook(id=textbook_id, title=title)
        session.add(row)
        session.flush()
        return row
    if row.title != title:
        row.title = title
        session.flush()
    return row


def _get_or_create_unit(
    session: Session,
    *,
    textbook_id: str,
    unit_ref: str,
) -> TextbookUnit:
    unit = session.scalar(
        select(TextbookUnit).where(TextbookUnit.unit_ref == unit_ref)
    )
    if unit is None:
        unit = TextbookUnit(
            textbook_id=textbook_id,
            unit_ref=unit_ref,
            status="NotReady",
            gate_reason=None,
            gate_metrics={},
        )
        session.add(unit)
        session.flush()
    return unit


def _clear_unit_chunks(session: Session, unit: TextbookUnit) -> None:
    chunk_ids = list(
        session.scalars(select(Chunk.id).where(Chunk.unit_id == unit.id)).all()
    )
    if chunk_ids:
        session.execute(delete(Embedding).where(Embedding.chunk_id.in_(chunk_ids)))
        session.execute(delete(Chunk).where(Chunk.id.in_(chunk_ids)))
        session.flush()


def upsert_not_ready_unit(
    session: Session,
    *,
    textbook_id: str,
    unit_ref: str,
    gate_reason: str,
    gate_metrics: dict[str, Any],
) -> TextbookUnit:
    upsert_textbook(session, textbook_id=textbook_id)
    unit = _get_or_create_unit(
        session, textbook_id=textbook_id, unit_ref=unit_ref
    )
    unit.status = "NotReady"
    unit.gate_reason = gate_reason
    unit.gate_metrics = gate_metrics
    _clear_unit_chunks(session, unit)
    session.flush()
    return unit


def upsert_ready_unit(
    session: Session,
    *,
    textbook_id: str,
    unit_ref: str,
    gate_metrics: dict[str, Any],
    chunk_texts: list[str],
    embeddings: list[list[float]],
    model_name: str,
    dims: int,
) -> TextbookUnit:
    if len(chunk_texts) != len(embeddings):
        raise ValueError(
            f"chunk/embedding length mismatch: {len(chunk_texts)} vs {len(embeddings)}"
        )
    if not chunk_texts:
        raise ValueError("Ready unit requires at least one non-empty chunk")

    upsert_textbook(session, textbook_id=textbook_id)
    unit = _get_or_create_unit(
        session, textbook_id=textbook_id, unit_ref=unit_ref
    )
    unit.status = "Ready"
    unit.gate_reason = None
    unit.gate_metrics = gate_metrics
    _clear_unit_chunks(session, unit)

    for ordinal, (content, vector) in enumerate(
        zip(chunk_texts, embeddings, strict=True)
    ):
        chunk = Chunk(
            unit_id=unit.id,
            textbook_id=textbook_id,
            unit_ref=unit_ref,
            ordinal=ordinal,
            content=content,
        )
        session.add(chunk)
        session.flush()
        session.add(
            Embedding(
                chunk_id=chunk.id,
                embedding=vector,
                model_name=model_name,
                dims=dims,
            )
        )
    session.flush()
    return unit


def smoke_select_unit(session: Session, unit_ref: str) -> SmokeRow | None:
    """Minimal same-process smoke: unit_ref + embedding dims/model_name."""
    ensure_corpus_schema(session)
    row = session.execute(
        text(
            """
            SELECT tu.unit_ref, tu.status, e.dims, e.model_name
            FROM textbook_unit tu
            LEFT JOIN chunk c ON c.unit_id = tu.id
            LEFT JOIN embedding e ON e.chunk_id = c.id
            WHERE tu.unit_ref = :unit_ref
            ORDER BY c.ordinal ASC NULLS LAST
            LIMIT 1
            """
        ),
        {"unit_ref": unit_ref},
    ).first()
    if row is None:
        return None
    return SmokeRow(
        unit_ref=row[0],
        status=row[1],
        dims=row[2],
        model_name=row[3],
    )
