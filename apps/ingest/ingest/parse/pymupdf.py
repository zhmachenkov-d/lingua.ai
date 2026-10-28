from __future__ import annotations

import logging
from pathlib import Path

from ingest.parse.types import ParseResult

logger = logging.getLogger(__name__)


class PyMuPDFTextAdapter:
    """Explicit non-primary fallback: PyMuPDF text-layer extract."""

    def parse(self, pdf_path: Path) -> ParseResult:
        try:
            import pymupdf
        except ImportError as exc:
            return ParseResult(
                text="",
                path="failed",
                page_count=0,
                error=f"PyMuPDF unavailable: {exc}",
            )

        try:
            doc = pymupdf.open(pdf_path)
        except Exception as exc:
            logger.exception("PyMuPDF failed to open %s", pdf_path)
            return ParseResult(
                text="",
                path="failed",
                page_count=0,
                error=f"PyMuPDF open failed: {exc}",
            )

        try:
            parts: list[str] = []
            for page in doc:
                parts.append(page.get_text("text") or "")
            text = "\n".join(parts)
            page_count = doc.page_count
        finally:
            doc.close()

        if not text.strip():
            return ParseResult(
                text="",
                path="failed",
                page_count=page_count,
                error="PyMuPDF text layer empty",
            )
        return ParseResult(
            text=text,
            path="pymupdf_fallback",
            page_count=page_count,
        )
