from __future__ import annotations

import io
from pathlib import Path

import pytest
from app.cli import _default_primary_adapter, run_metrics_job
from app.parse.result import ParseResult


def test_default_primary_is_ocrmypdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PARSE_PRIMARY", raising=False)
    adapter = _default_primary_adapter()
    assert adapter.adapter_id == "ocrmypdf_tesseract"


def test_parse_primary_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSE_PRIMARY", "marker")
    monkeypatch.setenv("MARKER_PAGE_RANGE", "0-1")
    adapter = _default_primary_adapter()
    assert adapter.adapter_id == "marker"


def test_parse_primary_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARSE_PRIMARY", "nope")
    with pytest.raises(ValueError, match="Unknown PARSE_PRIMARY"):
        _default_primary_adapter()


def test_run_metrics_uses_injected_primary(tmp_path: Path) -> None:
    textbooks = tmp_path / "textbooks"
    textbooks.mkdir()
    (textbooks / "a.pdf").write_bytes(b"%PDF")

    class Fake:
        adapter_id = "ocrmypdf_tesseract"

        def parse(self, pdf_path: Path) -> ParseResult:
            return ParseResult(
                text="x",
                page_count=1,
                mean_chars_per_page=1.0,
                printable_ratio=1.0,
                wall_time_ms=1,
                adapter_id=self.adapter_id,
                status="ok",
            )

    class Fallback:
        adapter_id = "pymupdf_text"

        def parse(self, pdf_path: Path) -> ParseResult:
            raise AssertionError("fallback should not run")

    stdout = io.StringIO()
    code = run_metrics_job(
        textbooks=textbooks,
        pdf_names=("a.pdf",),
        primary=Fake(),
        fallback=Fallback(),
        stdout=stdout,
        stderr=io.StringIO(),
    )
    assert code == 0
    assert "ocrmypdf_tesseract" in stdout.getvalue()
