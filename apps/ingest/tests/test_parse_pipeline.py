from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from ingest.parse.pipeline import parse_pdf
from ingest.parse.types import ParseResult, compute_metrics
from ingest.spike.note import PdfSpikeRow, render_spike_note


class FakeAdapter:
    def __init__(self, result: ParseResult) -> None:
        self.result = result
        self.calls: list[Path] = []

    def parse(self, pdf_path: Path) -> ParseResult:
        self.calls.append(pdf_path)
        return self.result


def test_marker_happy_path(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    primary = FakeAdapter(ParseResult("Hello page one", "marker", 1))
    fallback = FakeAdapter(ParseResult("fallback", "pymupdf_fallback", 1))

    result = parse_pdf(pdf, primary=primary, fallback=fallback)

    assert result.path == "marker"
    assert result.text == "Hello page one"
    assert primary.calls == [pdf]
    assert fallback.calls == []
    metrics = compute_metrics(result.text, result.page_count)
    assert metrics.mean_chars_per_page == pytest.approx(len("Hello page one"))
    assert metrics.printable_ratio == pytest.approx(1.0)


def test_marker_fail_then_pymupdf_fallback(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    primary = FakeAdapter(
        ParseResult("", "failed", 0, error="Marker boom")
    )
    fallback = FakeAdapter(
        ParseResult("text layer", "pymupdf_fallback", 2)
    )

    result = parse_pdf(pdf, primary=primary, fallback=fallback)

    assert result.path == "pymupdf_fallback"
    assert result.text == "text layer"
    assert primary.calls == [pdf]
    assert fallback.calls == [pdf]


def test_marker_empty_text_triggers_fallback(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    primary = FakeAdapter(
        ParseResult("   ", "marker", 1, error="empty")
    )
    fallback = FakeAdapter(
        ParseResult("from layer", "pymupdf_fallback", 1)
    )

    result = parse_pdf(pdf, primary=primary, fallback=fallback)

    assert result.path == "pymupdf_fallback"


def test_both_paths_fail(tmp_path: Path) -> None:
    pdf = tmp_path / "corrupt.pdf"
    pdf.write_bytes(b"not-a-pdf")
    primary = FakeAdapter(
        ParseResult("", "failed", 0, error="Marker boom")
    )
    fallback = FakeAdapter(
        ParseResult("", "failed", 0, error="no text layer")
    )

    result = parse_pdf(pdf, primary=primary, fallback=fallback)

    assert result.path == "failed"
    assert result.error is not None
    assert "Marker boom" in result.error
    assert "no text layer" in result.error


def test_missing_pdf_names_path(tmp_path: Path) -> None:
    missing = tmp_path / "absent.pdf"
    primary = FakeAdapter(ParseResult("x", "marker", 1))
    fallback = FakeAdapter(ParseResult("y", "pymupdf_fallback", 1))

    result = parse_pdf(missing, primary=primary, fallback=fallback)

    assert result.path == "failed"
    assert result.error is not None
    assert "Missing PDF" in result.error
    assert str(missing) in result.error
    assert primary.calls == []
    assert fallback.calls == []


def test_spike_note_includes_openrail_and_blank_gongo() -> None:
    md = render_spike_note(
        spike_date=date(2026, 10, 27),
        job_peak_rss_mb=512.0,
        rows=[
            PdfSpikeRow("a.pdf", "marker", 400.0, 250.0, 0.95),
            PdfSpikeRow(
                "b.pdf",
                "pymupdf_fallback",
                100.0,
                220.0,
                0.92,
                error="fallback — not primary Marker success",
            ),
        ],
    )
    assert "OpenRAIL-M" in md
    assert "MODEL_LICENSE" in md
    assert "`pymupdf_fallback`" in md
    assert "cgroup/process-tree" in md
    assert "- [ ] go / no-go — owner after confirming peak RSS" in md
