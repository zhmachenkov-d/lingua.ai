from __future__ import annotations

from pathlib import Path

import pytest
from app.parse.pipeline import parse_pdf
from app.parse.result import ParseResult, compute_yield_metrics


class FakeAdapter:
    def __init__(self, adapter_id: str, result: ParseResult) -> None:
        self._adapter_id = adapter_id
        self.result = result
        self.calls: list[Path] = []

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    def parse(self, pdf_path: Path) -> ParseResult:
        self.calls.append(pdf_path)
        return self.result


def test_marker_happy_path(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    primary = FakeAdapter(
        "marker",
        ParseResult(
            text="Hello page one",
            page_count=1,
            mean_chars_per_page=14.0,
            printable_ratio=1.0,
            wall_time_ms=12,
            adapter_id="marker",
            status="ok",
        ),
    )
    fallback = FakeAdapter(
        "pymupdf_text",
        ParseResult(
            text="fallback",
            page_count=1,
            mean_chars_per_page=8.0,
            printable_ratio=1.0,
            wall_time_ms=3,
            adapter_id="pymupdf_text",
            status="ok",
        ),
    )

    result = parse_pdf(pdf, primary=primary, fallback=fallback)

    assert result.status == "ok"
    assert result.adapter_id == "marker"
    assert result.text == "Hello page one"
    assert primary.calls == [pdf]
    assert fallback.calls == []
    mean, printable = compute_yield_metrics(result.text, result.page_count)
    assert mean == pytest.approx(len("Hello page one"))
    assert printable == pytest.approx(1.0)


def test_marker_fail_then_pymupdf_fallback(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    primary = FakeAdapter(
        "marker",
        ParseResult(
            text="",
            page_count=0,
            mean_chars_per_page=None,
            printable_ratio=None,
            wall_time_ms=50,
            adapter_id="marker",
            status="parse_failed",
            error="Marker boom",
        ),
    )
    fallback = FakeAdapter(
        "pymupdf_text",
        ParseResult(
            text="text layer",
            page_count=2,
            mean_chars_per_page=5.0,
            printable_ratio=1.0,
            wall_time_ms=4,
            adapter_id="pymupdf_text",
            status="ok",
        ),
    )

    result = parse_pdf(pdf, primary=primary, fallback=fallback)

    assert result.status == "fallback"
    assert result.adapter_id == "pymupdf_text"
    assert result.text == "text layer"
    assert primary.calls == [pdf]
    assert fallback.calls == [pdf]


def test_empty_marker_text_stays_ok_no_fallback(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    primary = FakeAdapter(
        "marker",
        ParseResult(
            text="",
            page_count=3,
            mean_chars_per_page=0.0,
            printable_ratio=0.0,
            wall_time_ms=9,
            adapter_id="marker",
            status="ok",
        ),
    )
    fallback = FakeAdapter(
        "pymupdf_text",
        ParseResult(
            text="from layer",
            page_count=3,
            mean_chars_per_page=3.0,
            printable_ratio=1.0,
            wall_time_ms=2,
            adapter_id="pymupdf_text",
            status="ok",
        ),
    )

    result = parse_pdf(pdf, primary=primary, fallback=fallback)

    assert result.status == "ok"
    assert result.adapter_id == "marker"
    assert fallback.calls == []


def test_both_paths_fail(tmp_path: Path) -> None:
    pdf = tmp_path / "corrupt.pdf"
    pdf.write_bytes(b"not-a-pdf")
    primary = FakeAdapter(
        "marker",
        ParseResult(
            text="",
            page_count=0,
            mean_chars_per_page=None,
            printable_ratio=None,
            wall_time_ms=1,
            adapter_id="marker",
            status="parse_failed",
            error="Marker boom",
        ),
    )
    fallback = FakeAdapter(
        "pymupdf_text",
        ParseResult(
            text="",
            page_count=0,
            mean_chars_per_page=None,
            printable_ratio=None,
            wall_time_ms=1,
            adapter_id="pymupdf_text",
            status="parse_failed",
            error="no text layer",
        ),
    )

    result = parse_pdf(pdf, primary=primary, fallback=fallback)

    assert result.status == "parse_failed"
    assert result.error is not None
    assert "Marker boom" in result.error
    assert "no text layer" in result.error


def test_missing_pdf_status(tmp_path: Path) -> None:
    missing = tmp_path / "absent.pdf"
    primary = FakeAdapter(
        "marker",
        ParseResult(
            text="x",
            page_count=1,
            mean_chars_per_page=1.0,
            printable_ratio=1.0,
            wall_time_ms=1,
            adapter_id="marker",
            status="ok",
        ),
    )
    fallback = FakeAdapter(
        "pymupdf_text",
        ParseResult(
            text="y",
            page_count=1,
            mean_chars_per_page=1.0,
            printable_ratio=1.0,
            wall_time_ms=1,
            adapter_id="pymupdf_text",
            status="ok",
        ),
    )

    result = parse_pdf(missing, primary=primary, fallback=fallback)

    assert result.status == "missing_pdf"
    assert result.error is not None
    assert "Missing PDF" in result.error
    assert str(missing) in result.error
    assert primary.calls == []
    assert fallback.calls == []
