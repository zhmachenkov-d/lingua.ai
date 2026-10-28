from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.parse.pymupdf_text import PyMuPDFTextAdapter


def test_extract_raise_returns_parse_failed(
    tmp_path: Path, monkeypatch
) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    bad_page = MagicMock()
    bad_page.get_text.side_effect = RuntimeError("get_text boom")
    doc = MagicMock()
    doc.__iter__.return_value = iter([bad_page])
    doc.page_count = 1
    doc.close = MagicMock()

    fake_pymupdf = MagicMock()
    fake_pymupdf.open.return_value = doc
    monkeypatch.setitem(__import__("sys").modules, "pymupdf", fake_pymupdf)

    result = PyMuPDFTextAdapter().parse(pdf)

    assert result.status == "parse_failed"
    assert result.adapter_id == "pymupdf_text"
    assert result.error is not None
    assert "get_text boom" in result.error
    doc.close.assert_called_once()
