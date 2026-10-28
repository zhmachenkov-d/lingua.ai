from __future__ import annotations

import logging
import time
from pathlib import Path

from app.parse.result import ParseResult, compute_yield_metrics

logger = logging.getLogger(__name__)

ADAPTER_ID = "pymupdf_text"


class PyMuPDFTextAdapter:
    """Explicit non-primary fallback: PyMuPDF text-layer extract."""

    @property
    def adapter_id(self) -> str:
        return ADAPTER_ID

    def parse(self, pdf_path: Path) -> ParseResult:
        started = time.perf_counter()
        try:
            import pymupdf
        except ImportError as exc:
            wall_ms = int((time.perf_counter() - started) * 1000)
            return ParseResult(
                text="",
                page_count=0,
                mean_chars_per_page=None,
                printable_ratio=None,
                wall_time_ms=wall_ms,
                adapter_id=ADAPTER_ID,
                status="parse_failed",
                error=f"PyMuPDF unavailable: {exc}",
            )

        try:
            doc = pymupdf.open(pdf_path)
        except Exception as exc:
            wall_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("PyMuPDF failed to open %s", pdf_path)
            return ParseResult(
                text="",
                page_count=0,
                mean_chars_per_page=None,
                printable_ratio=None,
                wall_time_ms=wall_ms,
                adapter_id=ADAPTER_ID,
                status="parse_failed",
                error=f"PyMuPDF open failed: {exc}",
            )

        try:
            parts: list[str] = []
            for page in doc:
                parts.append(page.get_text("text") or "")
            text = "\n".join(parts)
            page_count = int(doc.page_count)
        except Exception as exc:
            wall_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("PyMuPDF extract failed for %s", pdf_path)
            return ParseResult(
                text="",
                page_count=0,
                mean_chars_per_page=None,
                printable_ratio=None,
                wall_time_ms=wall_ms,
                adapter_id=ADAPTER_ID,
                status="parse_failed",
                error=f"PyMuPDF extract failed: {exc}",
            )
        finally:
            doc.close()

        mean, printable = compute_yield_metrics(text, page_count)
        wall_ms = int((time.perf_counter() - started) * 1000)
        # Empty layer is still a completed fallback attempt with metrics;
        # pipeline marks parse_failed only when Marker also failed.
        return ParseResult(
            text=text,
            page_count=page_count,
            mean_chars_per_page=mean,
            printable_ratio=printable,
            wall_time_ms=wall_ms,
            adapter_id=ADAPTER_ID,
            status="ok",
            error=None if text.strip() else "PyMuPDF text layer empty",
        )
