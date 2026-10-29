from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from app.chunk import split_paragraphs
from app.embed import BgeM3Embedder, Embedder
from app.gate import evaluate_hard_gate
from app.parse.pipeline import parse_pdf
from app.parse.protocol import ParseAdapter
from app.parse.result import METRIC_JSON_KEYS, ParseResult
from app.parse.rss import PeakRssTracker
from app.persist import (
    CorpusSchemaMissing,
    DatabaseConfigError,
    ensure_corpus_schema,
    has_ready_unit,
    list_ready_unit_refs,
    session_factory,
    smoke_select_unit,
    upsert_not_ready_unit,
    upsert_ready_unit,
    upsert_review_unit,
)
from app.units import EF4_BEG_SB_ID, EF4_BEG_WB_ID, extract_unit_text, list_units
from app.units.span import UnitSpan

logger = logging.getLogger(__name__)

DEFAULT_PDF_NAMES: tuple[str, ...] = (
    "English_File_4th_edition_Beginner_Students_book.pdf",
    "English_File_4th_edition_Beginner_Workbook.pdf",
)

SB_PDF_NAME = DEFAULT_PDF_NAMES[0]
WB_PDF_NAME = DEFAULT_PDF_NAMES[1]

ExtractFn = Callable[[Path, UnitSpan], str]


def textbooks_dir() -> Path:
    return Path(os.environ.get("TEXTBOOKS_DIR", "/textbooks"))


def ingest_mode() -> str:
    raw = os.environ.get("INGEST_MODE", "tracer").strip().lower() or "tracer"
    if raw not in {"tracer", "metrics"}:
        raise ValueError(f"Unknown INGEST_MODE={raw!r}; expected tracer or metrics")
    return raw


def ready_sweep() -> str:
    """Ready sweep policy for tracer: stop after first, or walk full SB map.

    Ignored when ``INGEST_MODE=metrics``. Default ``first`` preserves demo behavior.
    """
    raw = os.environ.get("INGEST_READY_SWEEP", "first").strip().lower() or "first"
    if raw not in {"first", "full"}:
        raise ValueError(
            f"Unknown INGEST_READY_SWEEP={raw!r}; expected first or full"
        )
    return raw


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


def _ensure_ocr_cache_dir() -> Path | None:
    """Prefer OCR_CACHE_DIR so searchable PDF survives for unit slicing."""
    env = os.environ.get("OCR_CACHE_DIR", "").strip()
    if env:
        path = Path(env)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return None


def _searchable_pdf_for_units(
    primary: ParseAdapter,
    source_pdf: Path,
    *,
    job_cache: Path | None,
) -> Path:
    """Resolve searchable PDF for unit extract — never reuse another book's OCR.

    Prefer the stem-keyed job_cache candidate. Accept ``last_searchable_pdf``
    only when its name is ``{source_pdf.stem}_ocr.pdf``; otherwise fall back
    to ``source_pdf`` so a failed WB parse cannot inherit the SB OCR pointer.
    """
    expected_name = f"{source_pdf.stem}_ocr.pdf"
    if job_cache is not None:
        candidate = job_cache / expected_name
        if candidate.is_file():
            return candidate
    cached = getattr(primary, "last_searchable_pdf", None)
    if (
        isinstance(cached, Path)
        and cached.is_file()
        and cached.name == expected_name
    ):
        return cached
    return source_pdf


def _mint_first_ready(
    *,
    SessionLocal: Any,
    pdf_path: Path,
    textbook_id: str,
    primary: ParseAdapter,
    fallback: ParseAdapter,
    embedder: Embedder,
    extract_fn: ExtractFn,
    job_cache: Path,
    stdout: TextIO,
    stop_after_first: bool = True,
) -> str | None:
    """OCR → map units → gate → chunk/embed; optionally stop after first Ready."""
    logger.info(
        "Tracer parsing %s (%s) via %s",
        pdf_path.name,
        textbook_id,
        primary.adapter_id,
    )
    parse_result = parse_pdf(pdf_path, primary=primary, fallback=fallback)
    searchable = _searchable_pdf_for_units(primary, pdf_path, job_cache=job_cache)
    units = list_units(textbook_id)
    ready_ref: str | None = None

    with SessionLocal() as session:
        for span in units:
            try:
                unit_text = extract_fn(searchable, span)
            except Exception as exc:
                logger.warning(
                    "Unit extract failed for %s: %s", span.unit_ref, exc
                )
                unit_text = ""

            gate = evaluate_hard_gate(
                unit_text,
                page_count=span.page_count,
                pdf_path=pdf_path,
                unit_pdf_path=searchable,
                page_start=span.page_start,
                page_end=span.page_end,
            )

            def _keep_existing_ready(reason: str) -> bool:
                """Re-sweep must not demote an already-Ready unit on fail paths."""
                if span.unit_ref in list_ready_unit_refs(session, span.textbook_id):
                    logger.info(
                        "Keeping existing Ready %s (skip demote: %s)",
                        span.unit_ref,
                        reason,
                    )
                    return True
                return False

            # Text-layer / failed parse is never a silent Ready path.
            if parse_result.status != "ok":
                if _keep_existing_ready(parse_result.status):
                    continue
                metrics = dict(gate.gate_metrics)
                metrics["parse_status"] = parse_result.status
                upsert_not_ready_unit(
                    session,
                    textbook_id=span.textbook_id,
                    unit_ref=span.unit_ref,
                    gate_reason=parse_result.status,
                    gate_metrics=metrics,
                )
                session.commit()
                logger.info(
                    "NotReady %s reason=%s",
                    span.unit_ref,
                    parse_result.status,
                )
                continue

            if gate.disposition == "Review":
                if _keep_existing_ready(gate.gate_reason or "image_area_soft"):
                    continue
                upsert_review_unit(
                    session,
                    textbook_id=span.textbook_id,
                    unit_ref=span.unit_ref,
                    gate_reason=gate.gate_reason or "image_area_soft",
                    gate_metrics=gate.gate_metrics,
                )
                session.commit()
                logger.info(
                    "Review %s reason=%s",
                    span.unit_ref,
                    gate.gate_reason,
                )
                continue

            if gate.disposition == "NotReady" or not gate.passed:
                if _keep_existing_ready(gate.gate_reason or "structure_zero"):
                    continue
                upsert_not_ready_unit(
                    session,
                    textbook_id=span.textbook_id,
                    unit_ref=span.unit_ref,
                    gate_reason=gate.gate_reason or "structure_zero",
                    gate_metrics=gate.gate_metrics,
                )
                session.commit()
                logger.info(
                    "NotReady %s reason=%s",
                    span.unit_ref,
                    gate.gate_reason,
                )
                continue

            chunks = split_paragraphs(unit_text)
            non_empty = [c for c in chunks if c.strip()]
            if not non_empty:
                if _keep_existing_ready("structure_zero"):
                    continue
                metrics = dict(gate.gate_metrics)
                metrics["structure_zero"] = True
                metrics["chunk_count"] = 0
                upsert_not_ready_unit(
                    session,
                    textbook_id=span.textbook_id,
                    unit_ref=span.unit_ref,
                    gate_reason="structure_zero",
                    gate_metrics=metrics,
                )
                session.commit()
                continue

            vectors = embedder.embed(non_empty)
            upsert_ready_unit(
                session,
                textbook_id=span.textbook_id,
                unit_ref=span.unit_ref,
                gate_metrics=gate.gate_metrics,
                chunk_texts=non_empty,
                embeddings=vectors,
                model_name=embedder.model_name,
                dims=embedder.dims,
            )
            session.commit()
            ready_ref = span.unit_ref
            smoke = smoke_select_unit(session, ready_ref)
            payload = {
                "mode": "tracer",
                "textbook_id": textbook_id,
                "unit_ref": ready_ref,
                "status": "Ready",
                "gate_metrics": gate.gate_metrics,
                "smoke": None
                if smoke is None
                else {
                    "unit_ref": smoke.unit_ref,
                    "status": smoke.status,
                    "dims": smoke.dims,
                    "model_name": smoke.model_name,
                },
            }
            print(json.dumps(payload, ensure_ascii=False), file=stdout, flush=True)
            if stop_after_first:
                logger.info(
                    "Ready %s — stopping after first Ready unit for %s",
                    ready_ref,
                    textbook_id,
                )
                break
            logger.info("Ready %s — continuing map sweep for %s", ready_ref, textbook_id)

    return ready_ref


def run_tracer_job(
    *,
    textbooks: Path | None = None,
    sb_pdf_name: str = SB_PDF_NAME,
    wb_pdf_name: str = WB_PDF_NAME,
    primary: ParseAdapter | None = None,
    fallback: ParseAdapter | None = None,
    embedder: Embedder | None = None,
    extract_fn: ExtractFn | None = None,
    database_url: str | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Require SB+WB PDFs; mint SB (or skip if Ready) then WB; both Ready required."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if textbooks is None:
        textbooks = textbooks_dir()
    if fallback is None:
        from app.parse.pymupdf_text import PyMuPDFTextAdapter

        fallback = PyMuPDFTextAdapter()
    if extract_fn is None:
        extract_fn = extract_unit_text
    if embedder is None:
        embedder = BgeM3Embedder()

    _, missing = resolve_required_pdfs(
        textbooks, (sb_pdf_name, wb_pdf_name)
    )
    if missing:
        for path in missing:
            print(f"missing required PDF: {path}", file=err)
        return 1
    sb_path = textbooks / sb_pdf_name
    wb_path = textbooks / wb_pdf_name

    # Keep a searchable OCR PDF for unit slicing (Compose sets OCR_CACHE_DIR).
    cache = _ensure_ocr_cache_dir()
    tmp_ctx = None
    if cache is None:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="lingua-tracer-ocr-")
        cache = Path(tmp_ctx.name)
        os.environ["OCR_CACHE_DIR"] = str(cache)

    if primary is None:
        primary = _default_primary_adapter()

    try:
        try:
            engine, SessionLocal = session_factory(database_url)
        except DatabaseConfigError as exc:
            print(f"database config error: {exc}", file=err)
            return 1

        try:
            with SessionLocal() as session:
                try:
                    ensure_corpus_schema(session)
                except CorpusSchemaMissing as exc:
                    print(str(exc), file=err)
                    return 1

            # Warm-load BGE-M3 outside unit-write sessions (download/load can be slow).
            warm = getattr(embedder, "_load", None)
            if callable(warm):
                warm()

            sweep = ready_sweep()
            # Full SB map sweep never short-circuits on existing Ready.
            skip_sb_when_ready = sweep == "first"
            stop_sb_after_first = sweep == "first"

            skipped_sb = False
            sb_ready_ref: str | None = None
            with SessionLocal() as session:
                if skip_sb_when_ready and has_ready_unit(session, EF4_BEG_SB_ID):
                    skipped_sb = True
                    refs = list_ready_unit_refs(session, EF4_BEG_SB_ID)
                    sb_ready_ref = refs[0] if refs else None
                    logger.info(
                        "Skipping SB mint path; existing Ready under %s (%s)",
                        EF4_BEG_SB_ID,
                        sb_ready_ref,
                    )
                    print(
                        json.dumps(
                            {
                                "mode": "tracer",
                                "textbook_id": EF4_BEG_SB_ID,
                                "skipped": True,
                                "unit_ref": sb_ready_ref,
                                "status": "Ready",
                            },
                            ensure_ascii=False,
                        ),
                        file=out,
                        flush=True,
                    )

            if not skipped_sb:
                _mint_first_ready(
                    SessionLocal=SessionLocal,
                    pdf_path=sb_path,
                    textbook_id=EF4_BEG_SB_ID,
                    primary=primary,
                    fallback=fallback,
                    embedder=embedder,
                    extract_fn=extract_fn,
                    job_cache=cache,
                    stdout=out,
                    stop_after_first=stop_sb_after_first,
                )

            # WB always stop-after-first (full-map sweep is SB-only).
            _mint_first_ready(
                SessionLocal=SessionLocal,
                pdf_path=wb_path,
                textbook_id=EF4_BEG_WB_ID,
                primary=primary,
                fallback=fallback,
                embedder=embedder,
                extract_fn=extract_fn,
                job_cache=cache,
                stdout=out,
                stop_after_first=True,
            )

            with SessionLocal() as session:
                sb_ok = has_ready_unit(session, EF4_BEG_SB_ID)
                wb_ok = has_ready_unit(session, EF4_BEG_WB_ID)
                sb_refs = list_ready_unit_refs(session, EF4_BEG_SB_ID)
                wb_refs = list_ready_unit_refs(session, EF4_BEG_WB_ID)

            summary = {
                "mode": "tracer",
                "skipped_sb": skipped_sb,
                "sb_ready": sb_refs,
                "wb_ready": wb_refs,
                # Tutor Ready DoD: SB-filtered only (WB Ready must not satisfy).
                "tutor_ready_dod": sb_refs,
            }
            print(json.dumps(summary, ensure_ascii=False), file=out, flush=True)

            if not sb_ok or not wb_ok:
                parts: list[str] = []
                if not sb_ok:
                    parts.append(f"zero Ready under {EF4_BEG_SB_ID}")
                if not wb_ok:
                    parts.append(f"zero Ready under {EF4_BEG_WB_ID}")
                print(
                    "tracer finished without required Ready: " + "; ".join(parts),
                    file=err,
                )
                return 1
            return 0
        finally:
            engine.dispose()
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()


def main(argv: list[str] | None = None) -> int:
    del argv  # CLI takes no args; mode/paths come from env.
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    mode = ingest_mode()
    if mode == "metrics":
        return run_metrics_job()
    return run_tracer_job()
