from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.parse.result import ParseResult


class ParseAdapter(Protocol):
    """Seam for PDF text extraction (primary OCR or text-layer fallback)."""

    @property
    def adapter_id(self) -> str:
        """Stable id on stdout JSON (``ocrmypdf_tesseract``, ``marker``, ...)."""
        ...

    def parse(self, pdf_path: Path) -> ParseResult:
        """Extract text from ``pdf_path``. Must not mint Ready units."""
        ...
