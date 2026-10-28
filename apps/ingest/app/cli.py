from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, TextIO

from app.parse.pipeline import parse_pdf
from app.parse.protocol import ParseAdapter
from app.parse.result import METRIC_JSON_KEYS, ParseResult
from app.parse.rss import PeakRssTracker

logger = logging.getLogger(__name__)

DEFAULT_PDF_NAMES: tuple[str, ...] = (
    "English_File_4th_edition_Beginner_Students_book.pdf",
    "English_File_4th_edition_Beginner_Workbook.pdf",
)


def textbooks_dir() -> Path:
    return Path(os.environ.get("TEXTBOOKS_DIR", "/textbooks"))


def _default_primary_adapter() -> ParseAdapter:
    """Select primary parse adapter from ``PARSE_PRIMARY`` (default: ocrmypdf)."""
    choice = os.environ.get("PARSE_PRIMARY", "ocrmypdf").strip().lower() or "ocrmypdf"
    if choice in {"ocrmypdf", "ocrmypdf_tesseract", "tesseract"}:
        from app.parse.ocrmypdf_tesseract import OcrmypdfAdapter

        return OcrmypdfAdapter()
    if choice == "marker":
        from app.parse.marker import MarkerAdapter

        # Optional HITL subset, e.g. MARKER_PAGE_RANGE=0-19 (Marker zero-based).
        page_range = os.environ.get("MARKER_PAGE_RANGE", "").strip() or None
        return MarkerAdapter(mode="fast", page_range=page_range)
    raise ValueError(f"Unknown PARSE_PRIMARY={choice!r}; expected ocrmypdf or marker")


def metrics_payload(
    *,
    pdf_name: str,
    result: ParseResult,
    peak_rss_bytes: int | None,
) -> dict[str, Any]:
    return {
        "pdf": pdf_name,
        "adapter_id": result.adapter_id,
        "status": result.status,
        "peak_rss_bytes": peak_rss_bytes,
        "wall_time_ms": result.wall_time_ms,
        "mean_chars_per_page": result.mean_chars_per_page,
        "printable_ratio": result.printable_ratio,
        "page_count": result.page_count if result.page_count > 0 else None,
    }


def assert_metric_keys(payload: dict[str, Any]) -> None:
    missing = [k for k in METRIC_JSON_KEYS if k not in payload]
    if missing:
        raise KeyError(f"stdout metrics missing keys: {missing}")


def resolve_required_pdfs(
    textbooks: Path,
    pdf_names: tuple[str, ...] = DEFAULT_PDF_NAMES,
) -> tuple[list[Path], list[Path]]:
    """Return (present_paths, missing_paths) for required SB/WB filenames."""
    present: list[Path] = []
    missing: list[Path] = []
    for name in pdf_names:
        path = textbooks / name
        if path.is_file():
            present.append(path)
        else:
            missing.append(path)
    return present, missing


def run_metrics_job(
    *,
    textbooks: Path | None = None,
    pdf_names: tuple[str, ...] = DEFAULT_PDF_NAMES,
    primary: ParseAdapter | None = None,
    fallback: ParseAdapter | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse SB+WB; print one JSON object per present PDF. Never writes spike note.

    Returns process exit code: non-zero if any required PDF path is missing.
    """
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if textbooks is None:
        textbooks = textbooks_dir()
    if primary is None:
        primary = _default_primary_adapter()
    if fallback is None:
        from app.parse.pymupdf_text import PyMuPDFTextAdapter

        fallback = PyMuPDFTextAdapter()

    present, missing = resolve_required_pdfs(textbooks, pdf_names)
    if missing:
        for path in missing:
            print(f"missing required PDF: {path}", file=err)
        return 1

    tracker = PeakRssTracker()
    tracker.start()
    try:
        for pdf_path in present:
            tracker.begin_section()
            logger.info("Parsing %s via %s", pdf_path.name, primary.adapter_id)
            result = parse_pdf(pdf_path, primary=primary, fallback=fallback)
            if result.error:
                logger.warning(
                    "Parse status=%s adapter=%s error=%s",
                    result.status,
                    result.adapter_id,
                    result.error,
                )
            else:
                logger.info(
                    "Parse status=%s adapter=%s",
                    result.status,
                    result.adapter_id,
                )
            peak = tracker.peak_bytes
            payload = metrics_payload(
                pdf_name=pdf_path.name,
                result=result,
                peak_rss_bytes=peak,
            )
            assert_metric_keys(payload)
            print(json.dumps(payload, ensure_ascii=False), file=out, flush=True)
    finally:
        tracker.stop()

    return 0


def main(argv: list[str] | None = None) -> int:
    del argv  # CLI takes no args; paths come from TEXTBOOKS_DIR + PRD names.
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    return run_metrics_job()
