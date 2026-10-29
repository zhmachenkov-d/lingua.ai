from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.parse.ocrmypdf_tesseract import OcrmypdfAdapter


def test_ocrmypdf_reuses_cache_without_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    src = tmp_path / "book.pdf"
    src.write_bytes(b"%PDF")
    cached = cache / "book_ocr.pdf"
    cached.write_bytes(b"%PDF-ocr")

    calls: list[tuple] = []

    def fake_run(*args: object, **kwargs: object) -> MagicMock:
        calls.append((args, kwargs))
        raise AssertionError("ocrmypdf should not run when cache hits")

    monkeypatch.setattr("app.parse.ocrmypdf_tesseract.subprocess.run", fake_run)

    page = MagicMock()
    page.get_text.return_value = "Hello from OCR"
    doc = MagicMock()
    doc.__iter__.return_value = iter([page])
    doc.page_count = 1
    fake_pymupdf = MagicMock()
    fake_pymupdf.open.return_value = doc
    monkeypatch.setitem(__import__("sys").modules, "pymupdf", fake_pymupdf)

    result = OcrmypdfAdapter(cache_dir=cache, reuse_cache=True).parse(src)

    assert calls == []
    assert result.status == "ok"
    assert result.adapter_id == "ocrmypdf_tesseract"
    assert result.text == "Hello from OCR"
    assert result.page_count == 1
    assert result.mean_chars_per_page == 14.0


def test_ocrmypdf_runs_then_extracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    src = tmp_path / "book.pdf"
    src.write_bytes(b"%PDF")

    def fake_run(cmd: list[str], **_kwargs: object) -> MagicMock:
        out = Path(cmd[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-ocr")
        completed = MagicMock()
        completed.returncode = 0
        completed.stderr = ""
        completed.stdout = ""
        return completed

    monkeypatch.setattr("app.parse.ocrmypdf_tesseract.subprocess.run", fake_run)

    page = MagicMock()
    page.get_text.return_value = "abc"
    doc = MagicMock()
    doc.__iter__.return_value = iter([page, page])
    doc.page_count = 2
    fake_pymupdf = MagicMock()
    fake_pymupdf.open.return_value = doc
    monkeypatch.setitem(__import__("sys").modules, "pymupdf", fake_pymupdf)

    adapter = OcrmypdfAdapter(cache_dir=cache, reuse_cache=False, jobs=2)
    result = adapter.parse(src)

    assert result.status == "ok"
    assert result.page_count == 2
    assert (cache / "book_ocr.pdf").is_file()
    assert adapter.last_searchable_pdf == cache / "book_ocr.pdf"


def test_ocrmypdf_missing_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "book.pdf"
    src.write_bytes(b"%PDF")

    def boom(*_a: object, **_k: object) -> None:
        raise FileNotFoundError("ocrmypdf")

    monkeypatch.setattr("app.parse.ocrmypdf_tesseract.subprocess.run", boom)

    result = OcrmypdfAdapter(cache_dir=tmp_path / "c").parse(src)

    assert result.status == "parse_failed"
    assert result.error is not None
    assert "ocrmypdf" in result.error.lower()


def test_ocrmypdf_clears_last_searchable_on_parse_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "workbook.pdf"
    src.write_bytes(b"%PDF")
    prior = tmp_path / "students_book_ocr.pdf"
    prior.write_bytes(b"%PDF-sb")

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("ocrmypdf boom")

    monkeypatch.setattr("app.parse.ocrmypdf_tesseract.subprocess.run", boom)

    adapter = OcrmypdfAdapter(cache_dir=tmp_path / "c")
    adapter.last_searchable_pdf = prior
    result = adapter.parse(src)

    assert result.status == "parse_failed"
    assert adapter.last_searchable_pdf is None
