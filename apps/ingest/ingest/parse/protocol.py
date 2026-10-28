from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ingest.parse.types import ParseResult


class ParseAdapter(Protocol):
    """Seam for PDF text extraction (primary Marker or fallback)."""

    def parse(self, pdf_path: Path) -> ParseResult:
        """Extract text from ``pdf_path``. Must not mint Ready units."""
        ...
