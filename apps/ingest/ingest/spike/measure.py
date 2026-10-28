from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ingest.parse.pipeline import parse_pdf
from ingest.parse.protocol import ParseAdapter
from ingest.parse.types import compute_metrics
from ingest.spike.note import PdfSpikeRow, render_spike_note, write_spike_note
from ingest.spike.rss import PeakRssTracker

logger = logging.getLogger(__name__)

DEFAULT_PDF_NAMES = (
    "English_File_4th_edition_Beginner_Students_book.pdf",
    "English_File_4th_edition_Beginner_Workbook.pdf",
)


def _pdf_page_count(pdf_path: Path, fallback: int) -> int:
    """Prefer the PDF's real page count (Marker metadata is sparse)."""
    try:
        import pymupdf

        doc = pymupdf.open(pdf_path)
        try:
            count = int(doc.page_count)
            if count > 0:
                return count
        finally:
            doc.close()
    except Exception:
        logger.debug(
            "Could not read page count via PyMuPDF for %s", pdf_path
        )
    return fallback


@dataclass(frozen=True)
class SpikeJobResult:
    note_path: Path
    measured_count: int
    failed_count: int
    job_peak_rss_mb: float


def textbooks_dir() -> Path:
    return Path(os.environ.get("TEXTBOOKS_DIR", "/textbooks"))


def docs_dir() -> Path:
    return Path(os.environ.get("SPIKE_DOCS_DIR", "/app/docs"))


def run_spike(
    textbooks: Path | None = None,
    out_dir: Path | None = None,
    pdf_names: tuple[str, ...] = DEFAULT_PDF_NAMES,
    primary: ParseAdapter | None = None,
    fallback: ParseAdapter | None = None,
    spike_date: date | None = None,
) -> SpikeJobResult:
    """Measure SB+WB parse yield and peak RSS; write dated spike note. No Ready mint."""
    if textbooks is None:
        textbooks = textbooks_dir()
    if out_dir is None:
        out_dir = docs_dir()
    if spike_date is None:
        spike_date = date.today()
    if primary is None:
        from ingest.parse.marker import MarkerAdapter

        primary = MarkerAdapter(mode="fast")
    if fallback is None:
        from ingest.parse.pymupdf import PyMuPDFTextAdapter

        fallback = PyMuPDFTextAdapter()

    tracker = PeakRssTracker()
    tracker.start()
    rows: list[PdfSpikeRow] = []
    measured = 0
    failed = 0
    install_notes: str | None = None

    try:
        for name in pdf_names:
            pdf_path = textbooks / name
            tracker.begin_section()
            logger.info("Parsing %s", name)
            result = parse_pdf(pdf_path, primary=primary, fallback=fallback)
            per_pdf_peak = tracker.peak_mb

            if result.path == "failed":
                failed += 1
                rows.append(
                    PdfSpikeRow(
                        pdf_name=name,
                        path="failed",
                        peak_rss_mb=per_pdf_peak,
                        mean_chars_per_page=None,
                        printable_ratio=None,
                        error=result.error,
                    )
                )
                if (
                    result.error
                    and "Marker failed" in result.error
                    and install_notes is None
                ):
                    install_notes = (
                        "Marker primary path raised during spike; recorded as "
                        "evidence (not a silent primary switch). First error: "
                        + result.error
                    )
            else:
                page_count = _pdf_page_count(pdf_path, result.page_count)
                metrics = compute_metrics(result.text, page_count)
                measured += 1
                rows.append(
                    PdfSpikeRow(
                        pdf_name=name,
                        path=result.path,
                        peak_rss_mb=per_pdf_peak,
                        mean_chars_per_page=metrics.mean_chars_per_page,
                        printable_ratio=metrics.printable_ratio,
                        error=(
                            None
                            if result.path == "marker"
                            else "fallback — not primary Marker success"
                        ),
                    )
                )
    finally:
        job_peak = tracker.stop()

    note_path = out_dir / f"marker-compose-cpu-spike-{spike_date.isoformat()}.md"
    content = render_spike_note(
        spike_date=spike_date,
        job_peak_rss_mb=job_peak,
        rows=rows,
        install_notes=install_notes,
    )
    try:
        write_spike_note(note_path, content)
    except OSError as exc:
        raise RuntimeError(
            f"Failed to write spike note to {note_path}: {exc}"
        ) from exc

    logger.info(
        "Spike note written to %s (measured=%s failed=%s peak_rss=%.1f MiB)",
        note_path,
        measured,
        failed,
        job_peak,
    )
    return SpikeJobResult(
        note_path=note_path,
        measured_count=measured,
        failed_count=failed,
        job_peak_rss_mb=job_peak,
    )
