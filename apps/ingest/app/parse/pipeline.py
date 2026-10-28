from __future__ import annotations

import logging
from pathlib import Path

from app.parse.protocol import ParseAdapter
from app.parse.result import ParseResult

logger = logging.getLogger(__name__)


def parse_pdf(
    pdf_path: Path,
    *,
    primary: ParseAdapter,
    fallback: ParseAdapter,
) -> ParseResult:
    """Try primary adapter; on exception/failure use explicit PyMuPDF fallback.

    Empty primary yield stays ``ok`` (metrics only). Fallback is only for
    primary raise / OOM / hard failure — never a silent second Ready path.
    """
    if not pdf_path.is_file():
        return ParseResult(
            text="",
            page_count=0,
            mean_chars_per_page=None,
            printable_ratio=None,
            wall_time_ms=None,
            adapter_id=None,
            status="missing_pdf",
            error=f"Missing PDF: {pdf_path}",
        )

    primary_result = primary.parse(pdf_path)
    if primary_result.status == "ok":
        return primary_result

    logger.warning(
        "Primary parse unusable for %s (%s); trying PyMuPDF fallback",
        pdf_path.name,
        primary_result.error or primary_result.status,
    )

    fallback_result = fallback.parse(pdf_path)
    if fallback_result.status == "ok":
        return ParseResult(
            text=fallback_result.text,
            page_count=fallback_result.page_count,
            mean_chars_per_page=fallback_result.mean_chars_per_page,
            printable_ratio=fallback_result.printable_ratio,
            wall_time_ms=fallback_result.wall_time_ms,
            adapter_id=fallback_result.adapter_id,
            status="fallback",
            error=primary_result.error,
        )

    errors = (
        "; ".join(e for e in (primary_result.error, fallback_result.error) if e)
        or "Both primary and PyMuPDF paths failed"
    )
    return ParseResult(
        text=fallback_result.text,
        page_count=max(primary_result.page_count, fallback_result.page_count),
        mean_chars_per_page=fallback_result.mean_chars_per_page,
        printable_ratio=fallback_result.printable_ratio,
        wall_time_ms=fallback_result.wall_time_ms,
        adapter_id=fallback_result.adapter_id or primary_result.adapter_id,
        status="parse_failed",
        error=errors,
    )
