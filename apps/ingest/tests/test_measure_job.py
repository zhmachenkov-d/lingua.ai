from __future__ import annotations

from datetime import date
from pathlib import Path

from ingest.parse.types import ParseResult
from ingest.spike.measure import run_spike


class FakeAdapter:
    def __init__(self, mapping: dict[str, ParseResult]) -> None:
        self.mapping = mapping

    def parse(self, pdf_path: Path) -> ParseResult:
        return self.mapping[pdf_path.name]


def test_job_continues_sibling_and_writes_note(tmp_path: Path) -> None:
    textbooks = tmp_path / "textbooks"
    docs = tmp_path / "docs"
    textbooks.mkdir()
    docs.mkdir()
    (textbooks / "a.pdf").write_bytes(b"%PDF")
    (textbooks / "b.pdf").write_bytes(b"%PDF")

    primary = FakeAdapter(
        {
            "a.pdf": ParseResult("aaa", "marker", 1),
            "b.pdf": ParseResult("", "failed", 0, error="Marker boom"),
        }
    )
    fallback = FakeAdapter(
        {
            "a.pdf": ParseResult("x", "marker", 1),
            "b.pdf": ParseResult("", "failed", 0, error="no layer"),
        }
    )

    result = run_spike(
        textbooks=textbooks,
        out_dir=docs,
        pdf_names=("a.pdf", "b.pdf"),
        primary=primary,
        fallback=fallback,
        spike_date=date(2026, 10, 27),
    )

    assert result.measured_count == 1
    assert result.failed_count == 1
    assert result.note_path.is_file()
    body = result.note_path.read_text(encoding="utf-8")
    assert "`marker`" in body
    assert "`failed`" in body
    assert "go / no-go" in body


def test_missing_pdf_row_no_fabricated_metrics(tmp_path: Path) -> None:
    textbooks = tmp_path / "textbooks"
    docs = tmp_path / "docs"
    textbooks.mkdir()
    docs.mkdir()
    (textbooks / "present.pdf").write_bytes(b"%PDF")

    primary = FakeAdapter(
        {"present.pdf": ParseResult("ok", "marker", 1)}
    )
    fallback = FakeAdapter({})

    result = run_spike(
        textbooks=textbooks,
        out_dir=docs,
        pdf_names=("present.pdf", "missing.pdf"),
        primary=primary,
        fallback=fallback,
        spike_date=date(2026, 10, 27),
    )

    body = result.note_path.read_text(encoding="utf-8")
    assert "Missing PDF" in body
    assert result.measured_count == 1
    assert result.failed_count == 1
