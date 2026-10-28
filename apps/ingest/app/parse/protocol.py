from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.parse.result import ParseResult


class ParseAdapter(Protocol):
    """Seam for PDF text extraction (primary Marker or fallback)."""

    @property
    def adapter_id(self) -> str:
        """Stable id emitted on stdout JSON (e.g. ``marker``, ``pymupdf_text``)."""
        ...

    def parse(self, pdf_path: Path) -> ParseResult:
        """Extract text from ``pdf_path``. Must not mint Ready units."""
        ...
