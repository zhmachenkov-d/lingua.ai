from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from app.parse.result import ParseResult, compute_yield_metrics

logger = logging.getLogger(__name__)

ADAPTER_ID = "ocrmypdf_tesseract"


def _default_jobs() -> int:
    raw = os.environ.get("OCRMYPDF_JOBS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return 4


class OcrmypdfAdapter:
    """Primary CPU OCR path: ocrmypdf (Tesseract) → searchable PDF → text layer.

    Image-only owner PDFs have an empty native text layer; this adapter forces
    OCR then extracts with PyMuPDF. Optional ``OCR_CACHE_DIR`` stores reusable
    ``{stem}_ocr.pdf`` artifacts between runs.
    """

    def __init__(
        self,
        *,
        language: str = "eng",
        jobs: int | None = None,
        cache_dir: Path | None = None,
        reuse_cache: bool = True,
    ) -> None:
        self._language = language
        self._jobs = jobs if jobs is not None else _default_jobs()
        env_cache = os.environ.get("OCR_CACHE_DIR", "").strip()
        self._cache_dir = cache_dir or (Path(env_cache) if env_cache else None)
        self._reuse_cache = reuse_cache
        self.last_searchable_pdf: Path | None = None

    @property
    def adapter_id(self) -> str:
        return ADAPTER_ID

    def _cached_path(self, pdf_path: Path) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / f"{pdf_path.stem}_ocr.pdf"

    def _run_ocrmypdf(self, pdf_path: Path, out_path: Path) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ocrmypdf",
            "-l",
            self._language,
            "--force-ocr",
            "--optimize",
            "0",
            "--output-type",
            "pdf",
            "--jobs",
            str(self._jobs),
            str(pdf_path),
            str(out_path),
        ]
        logger.info("OcrmypdfAdapter running: %s", " ".join(cmd))
        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "ocrmypdf binary not found; install ocrmypdf + tesseract-ocr"
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                f"ocrmypdf failed (exit {completed.returncode}): {detail[:800]}"
            )

    def parse(self, pdf_path: Path) -> ParseResult:
        started = time.perf_counter()
        try:
            cached = self._cached_path(pdf_path)
            if (
                cached is not None
                and self._reuse_cache
                and cached.is_file()
                and cached.stat().st_size > 0
            ):
                searchable = cached
                logger.info("OcrmypdfAdapter reuse cache %s", searchable)
                self.last_searchable_pdf = searchable
                return self._extract(searchable, started=started)

            if cached is not None:
                self._run_ocrmypdf(pdf_path, cached)
                self.last_searchable_pdf = cached
                return self._extract(cached, started=started)

            with tempfile.TemporaryDirectory(prefix="lingua-ocr-") as tmp:
                searchable = Path(tmp) / f"{pdf_path.stem}_ocr.pdf"
                self._run_ocrmypdf(pdf_path, searchable)
                self.last_searchable_pdf = None
                return self._extract(searchable, started=started)
        except Exception as exc:
            wall_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("OcrmypdfAdapter failed for %s", pdf_path)
            return ParseResult(
                text="",
                page_count=0,
                mean_chars_per_page=None,
                printable_ratio=None,
                wall_time_ms=wall_ms,
                adapter_id=ADAPTER_ID,
                status="parse_failed",
                error=f"ocrmypdf failed: {exc}",
            )

    def _extract(self, searchable: Path, *, started: float) -> ParseResult:
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
            doc = pymupdf.open(searchable)
        except Exception as exc:
            wall_ms = int((time.perf_counter() - started) * 1000)
            return ParseResult(
                text="",
                page_count=0,
                mean_chars_per_page=None,
                printable_ratio=None,
                wall_time_ms=wall_ms,
                adapter_id=ADAPTER_ID,
                status="parse_failed",
                error=f"PyMuPDF open failed on OCR PDF: {exc}",
            )

        try:
            parts: list[str] = []
            for page in doc:
                parts.append(page.get_text("text") or "")
            text = "\n".join(parts)
            page_count = int(doc.page_count)
        finally:
            doc.close()

        mean, printable = compute_yield_metrics(text, page_count)
        wall_ms = int((time.perf_counter() - started) * 1000)
        return ParseResult(
            text=text,
            page_count=page_count,
            mean_chars_per_page=mean,
            printable_ratio=printable,
            wall_time_ms=wall_ms,
            adapter_id=ADAPTER_ID,
            status="ok",
            error=None if text.strip() else "ocrmypdf text empty",
        )


def which_ocrmypdf() -> str | None:
    return shutil.which("ocrmypdf")
