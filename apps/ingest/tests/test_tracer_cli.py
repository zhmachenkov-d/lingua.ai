from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from app.cli import (
    SB_PDF_NAME,
    WB_PDF_NAME,
    _searchable_pdf_for_units,
    ingest_mode,
    ready_sweep,
    run_tracer_job,
)
from app.parse.result import ParseResult
from app.persist import CorpusSchemaMissing, DatabaseConfigError
from app.persist.store import SmokeRow
from app.units.span import UnitSpan
from lingua_ids import EMBEDDING_DIMS, EMBEDDING_MODEL_NAME

SB_ID = "ef4-beg-sb"
WB_ID = "ef4-beg-wb"


class FakeAdapter:
    def __init__(self, result: ParseResult) -> None:
        self._result = result
        self.last_searchable_pdf: Path | None = None
        self.parse_calls: list[Path] = []

    @property
    def adapter_id(self) -> str:
        return self._result.adapter_id or "fake"

    def parse(self, pdf_path: Path) -> ParseResult:
        self.parse_calls.append(pdf_path)
        return self._result


class FakeEmbedder:
    model_name = EMBEDDING_MODEL_NAME
    dims = EMBEDDING_DIMS

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.01 * (i + 1)] * EMBEDDING_DIMS for i, _ in enumerate(texts)]


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


def _session_local() -> MagicMock:
    session_cm = MagicMock(
        __enter__=MagicMock(return_value=MagicMock()),
        __exit__=MagicMock(return_value=False),
    )
    return MagicMock(return_value=session_cm)


def _list_units_side(
    sb_spans: tuple[UnitSpan, ...],
    wb_spans: tuple[UnitSpan, ...],
) -> Any:
    def _list(textbook_id: str) -> tuple[UnitSpan, ...]:
        if textbook_id == SB_ID:
            return sb_spans
        if textbook_id == WB_ID:
            return wb_spans
        raise KeyError(textbook_id)

    return _list


@pytest.fixture
def sb_dir(tmp_path: Path) -> Path:
    """Stub textbooks dir with both SB and WB PDFs (tracer requires both)."""
    textbooks = tmp_path / "textbooks"
    textbooks.mkdir()
    (
        textbooks / "English_File_4th_edition_Beginner_Students_book.pdf"
    ).write_bytes(b"%PDF-fake")
    (textbooks / WB_PDF_NAME).write_bytes(b"%PDF-fake")
    return textbooks


@pytest.fixture(autouse=True)
def _stub_image_area_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake textbooks PDFs are not real PyMuPDF docs; inject soft signal."""
    monkeypatch.setattr(
        "app.gate.hard.compute_image_area_ratio",
        lambda *args, **kwargs: 0.0,
    )


def test_ingest_mode_default_tracer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INGEST_MODE", raising=False)
    assert ingest_mode() == "tracer"


def test_ready_sweep_default_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INGEST_READY_SWEEP", raising=False)
    assert ready_sweep() == "first"


def test_ready_sweep_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INGEST_READY_SWEEP", "full")
    assert ready_sweep() == "full"


def test_ready_sweep_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INGEST_READY_SWEEP", "all")
    with pytest.raises(ValueError, match="INGEST_READY_SWEEP"):
        ready_sweep()


def test_missing_sb_pdf_fail_fast(tmp_path: Path) -> None:
    textbooks = tmp_path / "textbooks"
    textbooks.mkdir()
    (textbooks / WB_PDF_NAME).write_bytes(b"%PDF-fake")
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


def test_missing_wb_pdf_fail_fast(tmp_path: Path) -> None:
    textbooks = tmp_path / "textbooks"
    textbooks.mkdir()
    (
        textbooks / "English_File_4th_edition_Beginner_Students_book.pdf"
    ).write_bytes(b"%PDF-fake")
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
    assert "Workbook.pdf" in stderr.getvalue()


def test_searchable_pdf_rejects_cross_book_last_pointer(tmp_path: Path) -> None:
    """WB must not inherit SB OCR via a stale last_searchable_pdf pointer."""
    cache = tmp_path / "ocr-cache"
    cache.mkdir()
    sb_src = tmp_path / SB_PDF_NAME
    wb_src = tmp_path / WB_PDF_NAME
    sb_src.write_bytes(b"%PDF-sb")
    wb_src.write_bytes(b"%PDF-wb")
    sb_ocr = cache / f"{sb_src.stem}_ocr.pdf"
    sb_ocr.write_bytes(b"%PDF-sb-ocr")
    # No WB OCR cache artifact — simulates failed WB primary after SB success.

    class StalePointerAdapter:
        adapter_id = "fake"
        last_searchable_pdf = sb_ocr

        def parse(self, pdf_path: Path) -> ParseResult:
            del pdf_path
            return _ok_parse()

    primary = StalePointerAdapter()
    # Prefer stem-keyed cache when present.
    assert _searchable_pdf_for_units(primary, sb_src, job_cache=cache) == sb_ocr
    # Stale SB pointer must not win for WB; fall back to WB source.
    assert _searchable_pdf_for_units(primary, wb_src, job_cache=cache) == wb_src


def test_tracer_wb_extract_ignores_stale_sb_searchable(
    sb_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After SB OCR, failed WB parse must not extract/gate against SB OCR PDF."""
    cache = tmp_path / "lingua-tracer-ocr"
    cache.mkdir()
    monkeypatch.setenv("OCR_CACHE_DIR", str(cache))

    sb_path = sb_dir / SB_PDF_NAME
    wb_path = sb_dir / WB_PDF_NAME
    sb_ocr = cache / f"{sb_path.stem}_ocr.pdf"
    sb_ocr.write_bytes(b"%PDF-sb-ocr")

    failed = ParseResult(
        text="",
        page_count=0,
        mean_chars_per_page=None,
        printable_ratio=None,
        wall_time_ms=1,
        adapter_id="ocrmypdf_tesseract",
        status="parse_failed",
        error="wb ocr boom",
    )
    extract_pdfs: list[Path] = []

    class StickyPrimary:
        """SB ok leaves last_searchable on SB OCR; WB fail leaves it uncleared."""

        adapter_id = "ocrmypdf_tesseract"
        last_searchable_pdf: Path | None = None

        def parse(self, pdf_path: Path) -> ParseResult:
            if pdf_path.name == SB_PDF_NAME:
                self.last_searchable_pdf = sb_ocr
                return _ok_parse()
            # Simulate pre-fix OcrmypdfAdapter: fail without clearing pointer.
            return failed

    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    ready_books: set[str] = set()

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return textbook_id in ready_books

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        if textbook_id in ready_books:
            return [f"{textbook_id}/1A"]
        return []

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_books.add(kwargs["textbook_id"])
        return MagicMock()

    def extract(pdf: Path, span: UnitSpan) -> str:
        extract_pdfs.append(pdf)
        if span.textbook_id == SB_ID:
            return _rich_text(span.page_count)
        return "x"

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch("app.cli.upsert_not_ready_unit"),
        patch(
            "app.cli.smoke_select_unit",
            side_effect=lambda s, ref: SmokeRow(
                unit_ref=ref, status="Ready", dims=EMBEDDING_DIMS, model_name=EMBEDDING_MODEL_NAME
            ),
        ),
    ):
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=StickyPrimary(),  # type: ignore[arg-type]
            fallback=FakeAdapter(failed),
            embedder=FakeEmbedder(),
            extract_fn=extract,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )

    assert code == 1
    assert any(p == sb_ocr for p in extract_pdfs)
    wb_extracts = [
        p for p in extract_pdfs if p != sb_ocr
    ]
    assert wb_extracts
    assert all(p == wb_path for p in wb_extracts)
    assert sb_ocr not in wb_extracts


def test_schema_missing_refuses_ready(sb_dir: Path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    session = MagicMock()
    SessionLocal = MagicMock(
        return_value=MagicMock(
            __enter__=MagicMock(return_value=session),
            __exit__=MagicMock(return_value=False),
        )
    )
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


def test_happy_path_sb_and_wb_ready_and_smoke(sb_dir: Path) -> None:
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    ready_books: set[str] = set()
    ready_calls: list[str] = []

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return textbook_id in ready_books

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        if textbook_id in ready_books:
            return [f"{textbook_id}/1A"]
        return []

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_calls.append(kwargs["unit_ref"])
        ready_books.add(kwargs["textbook_id"])
        return MagicMock()

    def smoke(session: Any, unit_ref: str) -> SmokeRow:
        del session
        return SmokeRow(
            unit_ref=unit_ref,
            status="Ready",
            dims=EMBEDDING_DIMS,
            model_name=EMBEDDING_MODEL_NAME,
        )

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch("app.cli.smoke_select_unit", side_effect=smoke),
    ):
        stdout = io.StringIO()
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: _rich_text(span.page_count),
            stdout=stdout,
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )

    assert code == 0
    assert ready_calls == [f"{SB_ID}/1A", f"{WB_ID}/1A"]
    not_ready.assert_not_called()
    lines = [json.loads(line) for line in stdout.getvalue().strip().splitlines()]
    assert lines[0]["unit_ref"] == f"{SB_ID}/1A"
    assert lines[1]["unit_ref"] == f"{WB_ID}/1A"
    summary = lines[-1]
    assert summary["tutor_ready_dod"] == [f"{SB_ID}/1A"]
    assert summary["wb_ready"] == [f"{WB_ID}/1A"]
    assert f"{WB_ID}/1A" not in summary["tutor_ready_dod"]


def test_skip_sb_when_ready_still_runs_wb(sb_dir: Path) -> None:
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    ready_books: set[str] = {SB_ID}
    ready_calls: list[str] = []
    primary = FakeAdapter(_ok_parse())

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return textbook_id in ready_books

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        if textbook_id == SB_ID:
            return [f"{SB_ID}/1A"]
        if textbook_id in ready_books:
            return [f"{textbook_id}/1A"]
        return []

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_calls.append(kwargs["unit_ref"])
        ready_books.add(kwargs["textbook_id"])
        return MagicMock()

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch(
            "app.cli.smoke_select_unit",
            return_value=SmokeRow(
                unit_ref=f"{WB_ID}/1A",
                status="Ready",
                dims=EMBEDDING_DIMS,
                model_name=EMBEDDING_MODEL_NAME,
            ),
        ),
    ):
        stdout = io.StringIO()
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=primary,
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: _rich_text(span.page_count),
            stdout=stdout,
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )

    assert code == 0
    assert ready_calls == [f"{WB_ID}/1A"]
    not_ready.assert_not_called()
    # SB PDF must not be OCR'd when skipped; only WB.
    assert all(p.name == WB_PDF_NAME for p in primary.parse_calls)
    lines = [json.loads(line) for line in stdout.getvalue().strip().splitlines()]
    assert lines[0]["skipped"] is True
    assert lines[0]["textbook_id"] == SB_ID


def test_wb_fail_leaves_sb_ready_unchanged(sb_dir: Path) -> None:
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    ready_books: set[str] = {SB_ID}
    clear_or_ready: list[str] = []

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return textbook_id in ready_books

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        if textbook_id == SB_ID:
            return [f"{SB_ID}/1A"]
        return []

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        clear_or_ready.append(f"ready:{kwargs['unit_ref']}")
        ready_books.add(kwargs["textbook_id"])
        return MagicMock()

    def capture_nr(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        clear_or_ready.append(f"nr:{kwargs['unit_ref']}")
        return MagicMock()

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch("app.cli.upsert_not_ready_unit", side_effect=capture_nr),
    ):
        stderr = io.StringIO()
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: "x",  # WB hard-fails
            stdout=io.StringIO(),
            stderr=stderr,
            database_url="postgresql://u:p@localhost/db",
        )

    assert code == 1
    assert SB_ID in ready_books
    assert not any(c.startswith(f"ready:{SB_ID}") for c in clear_or_ready)
    assert not any(c.startswith(f"nr:{SB_ID}") for c in clear_or_ready)
    assert any(c.startswith(f"nr:{WB_ID}") for c in clear_or_ready)
    assert f"zero Ready under {WB_ID}" in stderr.getvalue()


def test_tutor_dod_helper_ignores_wb_only_ready(sb_dir: Path) -> None:
    """WB Ready must not appear in SB-filtered Tutor Ready DoD list."""
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    # Pre-seed WB only — SB mint will fail so exit 1, but summary DoD is SB-only.
    ready_books: set[str] = {WB_ID}

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return textbook_id in ready_books

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        if textbook_id in ready_books:
            return [f"{textbook_id}/1A"]
        return []

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_books.add(kwargs["textbook_id"])
        return MagicMock()

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch("app.cli.upsert_not_ready_unit"),
        patch(
            "app.cli.smoke_select_unit",
            return_value=SmokeRow(
                unit_ref=f"{SB_ID}/1A",
                status="Ready",
                dims=EMBEDDING_DIMS,
                model_name=EMBEDDING_MODEL_NAME,
            ),
        ),
    ):
        stdout = io.StringIO()
        # SB extract fails → NotReady; WB already Ready so skip mint still runs WB path
        # and can Ready again — use rich text so both mint Ready for clean DoD assert.
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: _rich_text(span.page_count),
            stdout=stdout,
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )

    assert code == 0
    summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
    assert summary["tutor_ready_dod"] == [f"{SB_ID}/1A"]
    assert f"{WB_ID}/1A" not in summary["tutor_ready_dod"]
    assert summary["wb_ready"] == [f"{WB_ID}/1A"]


def test_soft_review_then_ready_never_embeds_review(sb_dir: Path) -> None:
    sb_spans = (
        UnitSpan(SB_ID, "1A", "t", 5, 6),
        UnitSpan(SB_ID, "1B", "t", 7, 8),
    )
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    ready_books: set[str] = set()
    review_refs: list[str] = []
    ready_refs: list[str] = []
    embed_calls: list[int] = []

    class CountingEmbedder(FakeEmbedder):
        def embed(self, texts: list[str]) -> list[list[float]]:
            embed_calls.append(len(texts))
            return super().embed(texts)

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return textbook_id in ready_books

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        if textbook_id in ready_books:
            code = "1B" if textbook_id == SB_ID else "1A"
            return [f"{textbook_id}/{code}"]
        return []

    def capture_review(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        review_refs.append(kwargs["unit_ref"])
        return MagicMock()

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_refs.append(kwargs["unit_ref"])
        ready_books.add(kwargs["textbook_id"])
        return MagicMock()

    def extract(pdf: Path, span: UnitSpan) -> str:
        del pdf
        if span.textbook_id == SB_ID and span.code == "1A":
            return "hi"
        return _rich_text(span.page_count)

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.evaluate_hard_gate") as gate_mock,
        patch("app.cli.upsert_review_unit", side_effect=capture_review),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch(
            "app.cli.smoke_select_unit",
            side_effect=lambda s, ref: SmokeRow(
                unit_ref=ref, status="Ready", dims=EMBEDDING_DIMS, model_name=EMBEDDING_MODEL_NAME
            ),
        ),
    ):
        from app.gate.hard import GateResult

        def gate_side_effect(text: str, **kwargs: Any) -> GateResult:
            del kwargs
            if text.strip() == "hi":
                return GateResult(
                    passed=False,
                    disposition="Review",
                    gate_reason="image_area_soft",
                    gate_metrics={
                        "image_area_ratio": 0.85,
                        "mean_chars_per_page": 1.0,
                    },
                )
            return GateResult(
                passed=True,
                disposition="Ready",
                gate_reason=None,
                gate_metrics={
                    "image_area_ratio": 0.1,
                    "mean_chars_per_page": 500.0,
                    "printable_ratio": 1.0,
                },
            )

        gate_mock.side_effect = gate_side_effect
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=CountingEmbedder(),
            extract_fn=extract,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )

    assert code == 0
    assert review_refs == [f"{SB_ID}/1A"]
    assert ready_refs == [f"{SB_ID}/1B", f"{WB_ID}/1A"]
    not_ready.assert_not_called()
    assert len(embed_calls) == 2


def test_wb_soft_review_continues_to_wb_ready(sb_dir: Path) -> None:
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (
        UnitSpan(WB_ID, "1A", "t", 4, 5),
        UnitSpan(WB_ID, "1B", "t", 6, 7),
    )
    ready_books: set[str] = set()
    review_refs: list[str] = []
    ready_refs: list[str] = []

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return textbook_id in ready_books

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        if textbook_id == SB_ID and SB_ID in ready_books:
            return [f"{SB_ID}/1A"]
        if textbook_id == WB_ID and WB_ID in ready_books:
            return [f"{WB_ID}/1B"]
        return []

    def capture_review(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        review_refs.append(kwargs["unit_ref"])
        return MagicMock()

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_refs.append(kwargs["unit_ref"])
        ready_books.add(kwargs["textbook_id"])
        return MagicMock()

    def extract(pdf: Path, span: UnitSpan) -> str:
        del pdf
        if span.unit_ref == f"{WB_ID}/1A":
            return "hi"
        return _rich_text(span.page_count)

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.evaluate_hard_gate") as gate_mock,
        patch("app.cli.upsert_review_unit", side_effect=capture_review),
        patch("app.cli.upsert_not_ready_unit"),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch(
            "app.cli.smoke_select_unit",
            side_effect=lambda s, ref: SmokeRow(
                unit_ref=ref, status="Ready", dims=EMBEDDING_DIMS, model_name=EMBEDDING_MODEL_NAME
            ),
        ),
    ):
        from app.gate.hard import GateResult

        def gate_side_effect(text: str, **kwargs: Any) -> GateResult:
            del kwargs
            if text.strip() == "hi":
                return GateResult(
                    passed=False,
                    disposition="Review",
                    gate_reason="image_area_soft",
                    gate_metrics={"image_area_ratio": 0.85, "mean_chars_per_page": 1.0},
                )
            return GateResult(
                passed=True,
                disposition="Ready",
                gate_reason=None,
                gate_metrics={
                    "image_area_ratio": 0.1,
                    "mean_chars_per_page": 500.0,
                    "printable_ratio": 1.0,
                },
            )

        gate_mock.side_effect = gate_side_effect
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
    assert review_refs == [f"{WB_ID}/1A"]
    assert ready_refs == [f"{SB_ID}/1A", f"{WB_ID}/1B"]


def test_threshold_env_flips_disposition_without_code_edits(
    sb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same unit text: soft envs → Review; raised soft + hard → Ready."""
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    soft_text = "ab"  # 2 chars / 2 pages = 1.0

    def run_once() -> tuple[int, MagicMock, MagicMock, MagicMock]:
        ready_books: set[str] = set()
        review = MagicMock(
            side_effect=lambda *a, **k: MagicMock()
        )
        not_ready = MagicMock()
        ready = MagicMock()

        def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
            del args
            ready_books.add(kwargs["textbook_id"])
            ready(kwargs["unit_ref"])
            return MagicMock()

        def has_ready(session: Any, textbook_id: str) -> bool:
            del session
            return textbook_id in ready_books

        def list_refs(session: Any, textbook_id: str) -> list[str]:
            del session
            if textbook_id in ready_books:
                return [f"{textbook_id}/1A"]
            return []

        with (
            patch(
                "app.cli.session_factory",
                return_value=(MagicMock(), _session_local()),
            ),
            patch("app.cli.ensure_corpus_schema"),
            patch(
                "app.cli.list_units",
                side_effect=_list_units_side(sb_spans, wb_spans),
            ),
            patch("app.cli.has_ready_unit", side_effect=has_ready),
            patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
            patch(
                "app.cli.evaluate_hard_gate",
                wraps=__import__(
                    "app.gate", fromlist=["evaluate_hard_gate"]
                ).evaluate_hard_gate,
            ),
            patch("app.gate.hard.compute_image_area_ratio", return_value=0.85),
            patch("app.cli.upsert_review_unit", review),
            patch("app.cli.upsert_not_ready_unit", not_ready),
            patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
            patch(
                "app.cli.smoke_select_unit",
                side_effect=lambda s, ref: SmokeRow(
                    unit_ref=ref,
                    status="Ready",
                    dims=EMBEDDING_DIMS,
                    model_name=EMBEDDING_MODEL_NAME,
                ),
            ),
        ):
            code = run_tracer_job(
                textbooks=sb_dir,
                primary=FakeAdapter(_ok_parse()),
                fallback=FakeAdapter(_ok_parse()),
                embedder=FakeEmbedder(),
                extract_fn=lambda pdf, span: soft_text,
                stdout=io.StringIO(),
                stderr=io.StringIO(),
                database_url="postgresql://u:p@localhost/db",
            )
        return code, review, not_ready, ready

    # Soft pair matches → Review on SB+WB, zero Ready → exit 1
    monkeypatch.delenv("GATE_SOFT_CHARS_PER_PAGE", raising=False)
    monkeypatch.delenv("GATE_IMAGE_AREA_RATIO", raising=False)
    monkeypatch.delenv("GATE_MEAN_CHARS_PER_PAGE", raising=False)
    code, review, not_ready, ready = run_once()
    assert code == 1
    assert review.called
    ready.assert_not_called()

    # Soft disabled (image thresh 0.99) + hard mean lowered → Ready both books
    monkeypatch.setenv("GATE_IMAGE_AREA_RATIO", "0.99")
    monkeypatch.setenv("GATE_SOFT_CHARS_PER_PAGE", "1")
    monkeypatch.setenv("GATE_MEAN_CHARS_PER_PAGE", "1")
    code, review, not_ready, ready = run_once()
    assert code == 0
    assert ready.called
    review.assert_not_called()


def test_default_sweep_stops_after_first_sb_ready(
    sb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default/first sweep mints only the first gate-passing SB unit."""
    monkeypatch.delenv("INGEST_READY_SWEEP", raising=False)
    sb_spans = (
        UnitSpan(SB_ID, "1A", "t", 5, 6),
        UnitSpan(SB_ID, "1B", "t", 7, 8),
    )
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    ready_by_book: dict[str, list[str]] = {}

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return bool(ready_by_book.get(textbook_id))

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        return list(ready_by_book.get(textbook_id, []))

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_by_book.setdefault(kwargs["textbook_id"], []).append(kwargs["unit_ref"])
        return MagicMock()

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch(
            "app.cli.smoke_select_unit",
            side_effect=lambda s, ref: SmokeRow(
                unit_ref=ref,
                status="Ready",
                dims=EMBEDDING_DIMS,
                model_name=EMBEDDING_MODEL_NAME,
            ),
        ),
    ):
        stdout = io.StringIO()
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: _rich_text(span.page_count),
            stdout=stdout,
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )

    assert code == 0
    not_ready.assert_not_called()
    assert ready_by_book[SB_ID] == [f"{SB_ID}/1A"]
    assert ready_by_book[WB_ID] == [f"{WB_ID}/1A"]
    summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
    assert summary["sb_ready"] == [f"{SB_ID}/1A"]


def test_full_sweep_mints_all_gate_passing_sb_units(
    sb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INGEST_READY_SWEEP=full Ready-mints every gate-passing SB map unit."""
    monkeypatch.setenv("INGEST_READY_SWEEP", "full")
    sb_spans = (
        UnitSpan(SB_ID, "1A", "t", 5, 6),
        UnitSpan(SB_ID, "1B", "t", 7, 8),
        UnitSpan(SB_ID, "1C", "t", 9, 10),
    )
    wb_spans = (
        UnitSpan(WB_ID, "1A", "t", 4, 5),
        UnitSpan(WB_ID, "1B", "t", 6, 7),
    )
    ready_by_book: dict[str, list[str]] = {}
    ready_gate_metrics: list[dict[str, Any]] = []

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return bool(ready_by_book.get(textbook_id))

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        return list(ready_by_book.get(textbook_id, []))

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_by_book.setdefault(kwargs["textbook_id"], []).append(kwargs["unit_ref"])
        ready_gate_metrics.append(dict(kwargs["gate_metrics"]))
        assert kwargs["dims"] == EMBEDDING_DIMS
        assert kwargs["model_name"] == EMBEDDING_MODEL_NAME
        return MagicMock()

    def extract(pdf: Path, span: UnitSpan) -> str:
        del pdf
        # Mid SB unit fails hard gate; others pass. WB both pass but stop-after-first.
        if span.unit_ref == f"{SB_ID}/1B":
            return "tiny"
        return _rich_text(span.page_count)

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch(
            "app.cli.smoke_select_unit",
            side_effect=lambda s, ref: SmokeRow(
                unit_ref=ref,
                status="Ready",
                dims=EMBEDDING_DIMS,
                model_name=EMBEDDING_MODEL_NAME,
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
    assert ready_by_book[SB_ID] == [f"{SB_ID}/1A", f"{SB_ID}/1C"]
    # WB remains stop-after-first even under full SB sweep.
    assert ready_by_book[WB_ID] == [f"{WB_ID}/1A"]
    assert not_ready.call_args.kwargs["unit_ref"] == f"{SB_ID}/1B"
    assert all(m for m in ready_gate_metrics)
    summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
    assert summary["sb_ready"] == [f"{SB_ID}/1A", f"{SB_ID}/1C"]
    assert summary["wb_ready"] == [f"{WB_ID}/1A"]


def test_full_sweep_preserves_prior_ready_on_fail(
    sb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-sweep must not demote an already-Ready unit when that unit fails gate."""
    monkeypatch.setenv("INGEST_READY_SWEEP", "full")
    sb_spans = (
        UnitSpan(SB_ID, "1A", "t", 5, 6),
        UnitSpan(SB_ID, "1B", "t", 7, 8),
    )
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    # Prior Ready for 1A; this run's extract fails 1A hard-gate but 1B passes.
    ready_by_book: dict[str, list[str]] = {SB_ID: [f"{SB_ID}/1A"]}
    ready_calls: list[str] = []
    demote_refs: list[str] = []

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return bool(ready_by_book.get(textbook_id))

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        return list(ready_by_book.get(textbook_id, []))

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_calls.append(kwargs["unit_ref"])
        refs = ready_by_book.setdefault(kwargs["textbook_id"], [])
        if kwargs["unit_ref"] not in refs:
            refs.append(kwargs["unit_ref"])
        return MagicMock()

    def capture_demote(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        demote_refs.append(kwargs["unit_ref"])
        return MagicMock()

    def extract(pdf: Path, span: UnitSpan) -> str:
        del pdf
        if span.unit_ref == f"{SB_ID}/1A":
            return "tiny"  # hard-gate fail
        return _rich_text(span.page_count)

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch("app.cli.upsert_not_ready_unit", side_effect=capture_demote),
        patch("app.cli.upsert_review_unit", side_effect=capture_demote),
        patch(
            "app.cli.smoke_select_unit",
            side_effect=lambda s, ref: SmokeRow(
                unit_ref=ref,
                status="Ready",
                dims=EMBEDDING_DIMS,
                model_name=EMBEDDING_MODEL_NAME,
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
    assert f"{SB_ID}/1A" not in demote_refs
    assert f"{SB_ID}/1A" in ready_by_book[SB_ID]
    assert ready_calls == [f"{SB_ID}/1B", f"{WB_ID}/1A"]
    summary = json.loads(stdout.getvalue().strip().splitlines()[-1])
    assert summary["sb_ready"] == [f"{SB_ID}/1A", f"{SB_ID}/1B"]


def test_full_sweep_does_not_skip_existing_sb_ready(
    sb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sweep=full still runs SB mint when ≥1 SB Ready already exists."""
    monkeypatch.setenv("INGEST_READY_SWEEP", "full")
    sb_spans = (
        UnitSpan(SB_ID, "1A", "t", 5, 6),
        UnitSpan(SB_ID, "1B", "t", 7, 8),
    )
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    ready_by_book: dict[str, list[str]] = {SB_ID: [f"{SB_ID}/1A"]}
    ready_calls: list[str] = []
    primary = FakeAdapter(_ok_parse())

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return bool(ready_by_book.get(textbook_id))

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        return list(ready_by_book.get(textbook_id, []))

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_calls.append(kwargs["unit_ref"])
        refs = ready_by_book.setdefault(kwargs["textbook_id"], [])
        if kwargs["unit_ref"] not in refs:
            refs.append(kwargs["unit_ref"])
        return MagicMock()

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch(
            "app.cli.smoke_select_unit",
            side_effect=lambda s, ref: SmokeRow(
                unit_ref=ref,
                status="Ready",
                dims=EMBEDDING_DIMS,
                model_name=EMBEDDING_MODEL_NAME,
            ),
        ),
    ):
        stdout = io.StringIO()
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=primary,
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: _rich_text(span.page_count),
            stdout=stdout,
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )

    assert code == 0
    not_ready.assert_not_called()
    # Both SB units minted (re-upsert 1A + new 1B); no skipped_sb short-circuit.
    assert ready_calls == [f"{SB_ID}/1A", f"{SB_ID}/1B", f"{WB_ID}/1A"]
    assert any(p.name == SB_PDF_NAME for p in primary.parse_calls)
    lines = [json.loads(line) for line in stdout.getvalue().strip().splitlines()]
    assert not any(line.get("skipped") is True for line in lines)
    summary = lines[-1]
    assert summary["skipped_sb"] is False
    assert summary["sb_ready"] == [f"{SB_ID}/1A", f"{SB_ID}/1B"]


def test_full_sweep_fixture_source_never_ready(
    sb_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fixture refuse still holds under INGEST_READY_SWEEP=full."""
    monkeypatch.setenv("INGEST_READY_SWEEP", "full")
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "English_File_4th_edition_Beginner_Students_book.pdf").write_bytes(
        b"%PDF"
    )
    (fixtures / WB_PDF_NAME).write_bytes(b"%PDF")
    sb_spans = (
        UnitSpan(SB_ID, "1A", "t", 5, 6),
        UnitSpan(SB_ID, "1B", "t", 7, 8),
    )
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session, textbook_id
        return False

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session, textbook_id
        return []

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
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
    assert all(
        c.kwargs["gate_reason"] == "fixture_refuse" for c in not_ready.call_args_list
    )


def test_hard_gate_fail_then_ready(sb_dir: Path) -> None:
    sb_spans = (
        UnitSpan(SB_ID, "1A", "t", 5, 6),
        UnitSpan(SB_ID, "1B", "t", 7, 8),
    )
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)
    ready_books: set[str] = set()
    not_ready_refs: list[str] = []
    ready_refs: list[str] = []

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session
        return textbook_id in ready_books

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session
        if textbook_id == SB_ID and SB_ID in ready_books:
            return [f"{SB_ID}/1B"]
        if textbook_id == WB_ID and WB_ID in ready_books:
            return [f"{WB_ID}/1A"]
        return []

    def capture_nr(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        not_ready_refs.append(kwargs["unit_ref"])
        return MagicMock()

    def capture_ready(*args: Any, **kwargs: Any) -> MagicMock:
        del args
        ready_refs.append(kwargs["unit_ref"])
        ready_books.add(kwargs["textbook_id"])
        return MagicMock()

    def extract(pdf: Path, span: UnitSpan) -> str:
        del pdf
        if span.unit_ref == f"{SB_ID}/1A":
            return "tiny"
        return _rich_text(span.page_count)

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_not_ready_unit", side_effect=capture_nr),
        patch("app.cli.upsert_ready_unit", side_effect=capture_ready),
        patch(
            "app.cli.smoke_select_unit",
            side_effect=lambda s, ref: SmokeRow(
                unit_ref=ref, status="Ready", dims=EMBEDDING_DIMS, model_name=EMBEDDING_MODEL_NAME
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
    assert not_ready_refs == [f"{SB_ID}/1A"]
    assert ready_refs == [f"{SB_ID}/1B", f"{WB_ID}/1A"]


def test_all_units_fail_exits_nonzero(sb_dir: Path) -> None:
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session, textbook_id
        return False

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session, textbook_id
        return []

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
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
    assert f"zero Ready under {SB_ID}" in stderr.getvalue()
    assert f"zero Ready under {WB_ID}" in stderr.getvalue()


def test_fixture_source_never_ready(sb_dir: Path, tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "English_File_4th_edition_Beginner_Students_book.pdf").write_bytes(
        b"%PDF"
    )
    (fixtures / WB_PDF_NAME).write_bytes(b"%PDF")
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session, textbook_id
        return False

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session, textbook_id
        return []

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
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
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session, textbook_id
        return False

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session, textbook_id
        return []

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
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
    text_layer_ok = ParseResult(
        text="layer",
        page_count=10,
        mean_chars_per_page=500.0,
        printable_ratio=1.0,
        wall_time_ms=1,
        adapter_id="pymupdf_text",
        status="ok",
    )
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session, textbook_id
        return False

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session, textbook_id
        return []

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
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
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 6),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 5),)

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session, textbook_id
        return False

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session, textbook_id
        return []

    def boom(pdf: Path, span: UnitSpan) -> str:
        del pdf, span
        raise RuntimeError("slice failed")

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
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


def test_all_short_ocr_noise_chunks_mark_structure_zero_not_ready(
    sb_dir: Path,
) -> None:
    """Hard gate can pass on many short scraps; post-split empty → NotReady."""
    # page_count=1 → need ≥200 chars to clear mean_chars; every para is len 2.
    short_noise = "\n\n".join(["ab"] * 120)
    sb_spans = (UnitSpan(SB_ID, "1A", "t", 5, 5),)
    wb_spans = (UnitSpan(WB_ID, "1A", "t", 4, 4),)

    def has_ready(session: Any, textbook_id: str) -> bool:
        del session, textbook_id
        return False

    def list_refs(session: Any, textbook_id: str) -> list[str]:
        del session, textbook_id
        return []

    with (
        patch(
            "app.cli.session_factory",
            return_value=(MagicMock(), _session_local()),
        ),
        patch("app.cli.ensure_corpus_schema"),
        patch("app.cli.list_units", side_effect=_list_units_side(sb_spans, wb_spans)),
        patch("app.cli.has_ready_unit", side_effect=has_ready),
        patch("app.cli.list_ready_unit_refs", side_effect=list_refs),
        patch("app.cli.upsert_not_ready_unit") as not_ready,
        patch("app.cli.upsert_ready_unit") as ready,
    ):
        code = run_tracer_job(
            textbooks=sb_dir,
            primary=FakeAdapter(_ok_parse()),
            fallback=FakeAdapter(_ok_parse()),
            embedder=FakeEmbedder(),
            extract_fn=lambda pdf, span: short_noise,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
            database_url="postgresql://u:p@localhost/db",
        )
    assert code == 1
    ready.assert_not_called()
    assert not_ready.called
    assert all(
        c.kwargs["gate_reason"] == "structure_zero" for c in not_ready.call_args_list
    )
    assert all(
        c.kwargs["gate_metrics"].get("chunk_count") == 0
        for c in not_ready.call_args_list
    )
