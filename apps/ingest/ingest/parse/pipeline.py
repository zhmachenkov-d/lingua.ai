from __future__ import annotations

import logging
from pathlib import Path

from ingest.parse.protocol import ParseAdapter
from ingest.parse.types import ParseResult

logger = logging.getLogger(__name__)


def parse_pdf(
    pdf_path: Path,
    *,
    primary: ParseAdapter,
    fallback: ParseAdapter,
) -> ParseResult:
    """Try Marker primary; on failure or empty text use explicit PyMuPDF fallback."""
    if not pdf_path.is_file():
        return ParseResult(
            text="",
            path="failed",
            page_count=0,
            error=f"Missing PDF: {pdf_path}",
        )

    primary_result = primary.parse(pdf_path)
    if primary_result.path == "marker" and primary_result.text.strip():
        return primary_result

    logger.warning(
        "Primary parse unusable for %s (%s); trying PyMuPDF fallback",
        pdf_path,
        primary_result.error or primary_result.path,
    )

    fallback_result = fallback.parse(pdf_path)
    if (
        fallback_result.path == "pymupdf_fallback"
        and fallback_result.text.strip()
    ):
        return fallback_result

    errors = "; ".join(
        e
        for e in (primary_result.error, fallback_result.error)
        if e
    ) or "Both Marker and PyMuPDF paths failed"
    return ParseResult(
        text="",
        path="failed",
        page_count=max(primary_result.page_count, fallback_result.page_count),
        error=errors,
    )
