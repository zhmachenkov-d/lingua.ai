from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.cli import ingest_mode, run_tracer_job
from app.parse.result import ParseResult
from app.persist import CorpusSchemaMissing, DatabaseConfigError
from app.persist.store import SmokeRow
from app.units.span import UnitSpan


class FakeAdapter:
    def __init__(self, result: ParseResult) -> None:
        self._result = result
        self.last_searchable_pdf: Path | None = None

    @property
    def adapter_id(self) -> str:
        return self._result.adapter_id or "fake"

    def parse(self, pdf_path: Path) -> ParseResult:
        del pdf_path
        return self._result


class FakeEmbedder:
    model_name = "BAAI/bge-m3"
    dims = 1024

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.01 * (i + 1)] * 1024 for i, _ in enumerate(texts)]


def _ok_parse() -> ParseResult:
    return ParseResult(
        text="ok",
        page_count=10,
        mean_chars_per_page=500.0,
        printable_ratio=1.0,
        wall_time_ms=1,
        adapter_id="ocrmypdf_tesseract",
        status="ok",
    )


def _rich_text(pages: int = 2) -> str:
    return ("Cappuccino please. " * 30 + "\n\n") * pages


@pytest.fixture
def sb_dir(tmp_path: Path) -> Path:
    textbooks = tmp_path / "textbooks"
    textbooks.mkdir()
    (
        textbooks / "English_File_4th_edition_Beginner_Students_book.pdf"
    ).write_bytes(b"%PDF-fake")
    return textbooks


def test_ingest_mode_default_tracer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INGEST_MODE", raising=False)
    assert ingest_mode() == "tracer"


def test_missing_sb_pdf_fail_fast(tmp_path: Path) -> None:
    textbooks = tmp_path / "textbooks"
    textbooks.mkdir()
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run_tracer_job(
        textbooks=textbooks,
        primary=FakeAdapter(_ok_parse()),
        fallback=FakeAdapter(_ok_parse()),
        embedder=FakeEmbedder(),
        stdout=stdout,
        stderr=stderr,
        database_url="postgresql://u:p@localhost/db",
    )
    assert code == 1
    assert stdout.getvalue().strip() == ""
    assert "missing required PDF" in stderr.getvalue()
    assert "Students_book.pdf" in stderr.getvalue()


def test_schema_missing_refuses_ready(sb_dir: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    session = MagicMock()
    SessionLocal = MagicMock(return_value=MagicMock(
        __enter__=MagicMock(return_value=session),
        __exit__=MagicMock(return_value=False),
    ))
    engine = MagicMock()

    with (
        patch("app.cli.session_factory", return_value=(engine, SessionLocal)),
        patch(
            "app.cli.ensure_corpus_schema",
            side_effect=CorpusSchemaMissing("corpus schema missing (0003)"),
        ),
    ):
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            stdout=stdout,
            stderr=stderr,
            database_url="postgresql://u:p@localhost/db",
        )
    assert code == 1
    assert "0003" in stderr.getvalue() or "corpus schema missing" in stderr.getvalue()
    assert stdout.getvalue().strip() == ""


def test_database_config_error(sb_dir: Path) -> None:
    stderr = io.StringIO()
    with patch(
        "app.cli.session_factory",
        side_effect=DatabaseConfigError("no db"),
    ):
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            stdout=io.StringIO(),
            stderr=stderr,
        )
    assert code == 1
    assert "database config error" in stderr.getvalue()


def test_happy_path_first_ready_and_smoke(sb_dir: Path) -> None:
    spans = (
        UnitSpan("ef4-beg-sb", "1A", "t", 5, 6),
        UnitSpan("ef4-beg-sb", "1B", "t", 7, 8),
    )

    def extract(pdf: Path, span: UnitSpan) -> str:
        del pdf
        return _rich_text(span.page_count)

    session = MagicMock()
    session_cm = MagicMock(
        __enter__=MagicMock(return_value=session),
        __exit__=MagicMock(return_value=False),
    )
    SessionLocal = MagicMock(return_value=session_cm)
    engine = MagicMock()
    ready_calls: list[str] = []

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_calls.append(kwargs["unit_ref"])
        return MagicMock()

    with (
        patch("app.cli.session_factory", return_value=(engine, SessionLocal)),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", return_value=spans),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch(
            "app.cli.smoke_select_unit",
            return_value=SmokeRow(
                unit_ref="ef4-beg-sb/1A",
                status="Ready",
                dims=1024,
                model_name="BAAI/bge-m3",
            ),
        ),
    ):
        stdout = io.StringIO()
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=extract,
            stdout=stdout,
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )

    assert code == 0
    assert ready_calls == ["ef4-beg-sb/1A"]
    not_ready.assert_not_called()
    payload = json.loads(stdout.getvalue().strip())
    assert payload["unit_ref"] == "ef4-beg-sb/1A"
    assert payload["status"] == "Ready"
    assert payload["smoke"]["dims"] == 1024
    assert payload["smoke"]["model_name"] == "BAAI/bge-m3"
    assert "gate_metrics" in payload


def test_hard_gate_fail_then_ready(sb_dir: Path) -> None:
    spans = (
        UnitSpan("ef4-beg-sb", "1A", "t", 5, 6),
        UnitSpan("ef4-beg-sb", "1B", "t", 7, 8),
    )

    def extract(pdf: Path, span: UnitSpan) -> str:
        del pdf
        if span.code == "1A":
            return "tiny"
        return _rich_text(span.page_count)

    session = MagicMock()
    session_cm = MagicMock(
        __enter__=MagicMock(return_value=session),
        __exit__=MagicMock(return_value=False),
    )
    not_ready_refs: list[str] = []
    ready_refs: list[str] = []

    def capture_nr(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        not_ready_refs.append(kwargs["unit_ref"])
        return MagicMock()

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_refs.append(kwargs["unit_ref"])
        return MagicMock()

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), MagicMock(return_value=session_cm)),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", return_value=spans),
        patch("app.cli.upsert_not_ready_unit", side_effect=capture_nr),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch(
            "app.cli.smoke_select_unit",
            return_value=SmokeRow(
                unit_ref="ef4-beg-sb/1B",
                status="Ready",
                dims=1024,
                model_name="BAAI/bge-m3",
            ),
        ),
    ):
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=extract,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )

    assert code == 0
    assert not_ready_refs == ["ef4-beg-sb/1A"]
    assert ready_refs == ["ef4-beg-sb/1B"]


def test_all_units_fail_exits_nonzero(sb_dir: Path) -> None:
    spans = (UnitSpan("ef4-beg-sb", "1A", "t", 5, 6),)

    session_cm = MagicMock(
        __enter__=MagicMock(return_value=MagicMock()),
        __exit__=MagicMock(return_value=False),
    )
    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), MagicMock(return_value=session_cm)),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", return_value=spans),
        patch("app.cli.upsert_not_ready_unit"),
        patch("app.cli.upsert_ready_unit") as ready,
    ):
        stderr = io.StringIO()
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: "x",
            stdout=io.StringIO(),
            stderr=stderr,
            database_url="postgresql://u:p@localhost/db",
        )
    assert code == 1
    ready.assert_not_called()
    assert "zero Ready" in stderr.getvalue()


def test_fixture_source_never_ready(sb_dir: Path, tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    pdf = fixtures / "English_File_4th_edition_Beginner_Students_book.pdf"
    pdf.write_bytes(b"%PDF")
    spans = (UnitSpan("ef4-beg-sb", "1A", "t", 5, 6),)
    session_cm = MagicMock(
        __enter__=MagicMock(return_value=MagicMock()),
        __exit__=MagicMock(return_value=False),
    )
    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), MagicMock(return_value=session_cm)),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", return_value=spans),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch("app.cli.upsert_ready_unit") as ready,
    ):
        code = run_tracer_job(
            textbooks=fixtures,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: _rich_text(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )
    assert code == 1
    ready.assert_not_called()
    assert not_ready.called
    assert not_ready.call_args.kwargs["gate_reason"] == "fixture_refuse"


def test_parse_failed_marks_not_ready(sb_dir: Path) -> None:
    failed = ParseResult(
        text="",
        page_count=0,
        mean_chars_per_page=None,
        printable_ratio=None,
        wall_time_ms=1,
        adapter_id="ocrmypdf_tesseract",
        status="parse_failed",
        error="boom",
    )
    spans = (UnitSpan("ef4-beg-sb", "1A", "t", 5, 6),)
    session_cm = MagicMock(
        __enter__=MagicMock(return_value=MagicMock()),
        __exit__=MagicMock(return_value=False),
    )
    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), MagicMock(return_value=session_cm)),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", return_value=spans),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch("app.cli.upsert_ready_unit") as ready,
    ):
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(failed),
            fallback=FakeAdapter(failed),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: _rich_text(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )
    assert code == 1
    ready.assert_not_called()
    assert not_ready.call_args.kwargs["gate_reason"] == "parse_failed"


def test_fallback_parse_never_upserts_ready(sb_dir: Path) -> None:
    primary_fail = ParseResult(
        text="",
        page_count=0,
        mean_chars_per_page=None,
        printable_ratio=None,
        wall_time_ms=1,
        adapter_id="ocrmypdf_tesseract",
        status="parse_failed",
        error="primary failed",
    )
    # Pipeline marks status="fallback" when PyMuPDF succeeds after primary fail.
    text_layer_ok = ParseResult(
        text="layer",
        page_count=10,
        mean_chars_per_page=500.0,
        printable_ratio=1.0,
        wall_time_ms=1,
        adapter_id="pymupdf_text",
        status="ok",
    )
    spans = (UnitSpan("ef4-beg-sb", "1A", "t", 5, 6),)
    session_cm = MagicMock(
        __enter__=MagicMock(return_value=MagicMock()),
        __exit__=MagicMock(return_value=False),
    )
    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), MagicMock(return_value=session_cm)),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", return_value=spans),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch("app.cli.upsert_ready_unit") as ready,
    ):
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(primary_fail),
            fallback=FakeAdapter(text_layer_ok),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: _rich_text(),
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )
    assert code == 1
    ready.assert_not_called()
    assert not_ready.call_args.kwargs["gate_reason"] == "fallback"


def test_extract_exception_is_structure_zero_not_parse_failed(sb_dir: Path) -> None:
    spans = (UnitSpan("ef4-beg-sb", "1A", "t", 5, 6),)
    session_cm = MagicMock(
        __enter__=MagicMock(return_value=MagicMock()),
        __exit__=MagicMock(return_value=False),
    )

    def boom(pdf: Path, span: UnitSpan) -> str:
        del pdf, span
        raise RuntimeError("slice failed")

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), MagicMock(return_value=session_cm)),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", return_value=spans),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch("app.cli.upsert_ready_unit") as ready,
    ):
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=boom,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )
    assert code == 1
    ready.assert_not_called()
    assert not_ready.call_args.kwargs["gate_reason"] == "structure_zero"
