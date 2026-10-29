from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.gate.image_area import image_area_ratio as compute_image_area_ratio
from app.parse.result import compute_yield_metrics

DEFAULT_MEAN_CHARS = 200.0
DEFAULT_PRINTABLE_RATIO = 0.90
DEFAULT_IMAGE_AREA_RATIO = 0.70
DEFAULT_SOFT_CHARS = 50.0

Disposition = Literal["Ready", "NotReady", "Review"]

_FIXTURE_MARKERS = ("fixture", "synthetic", "fixtures")


@dataclass(frozen=True, slots=True)
class GateResult:
    """Gate outcome for one unit span (hard + soft Review)."""

    passed: bool
    disposition: Disposition
    gate_reason: str | None
    gate_metrics: dict[str, Any]


def _threshold_mean_chars() -> float:
    raw = os.environ.get("GATE_MEAN_CHARS_PER_PAGE", "").strip()
    if raw:
        return float(raw)
    return DEFAULT_MEAN_CHARS


def _threshold_printable() -> float:
    raw = os.environ.get("GATE_PRINTABLE_RATIO", "").strip()
    if raw:
        return float(raw)
    return DEFAULT_PRINTABLE_RATIO


def _threshold_image_area() -> float:
    raw = os.environ.get("GATE_IMAGE_AREA_RATIO", "").strip()
    if raw:
        return float(raw)
    return DEFAULT_IMAGE_AREA_RATIO


def _threshold_soft_chars() -> float:
    raw = os.environ.get("GATE_SOFT_CHARS_PER_PAGE", "").strip()
    if raw:
        return float(raw)
    return DEFAULT_SOFT_CHARS


def is_fixture_source(path: Path | str | None) -> bool:
    """True when the PDF path looks like a fixture/synthetic corpus source."""
    if path is None:
        return False
    kind = os.environ.get("INGEST_SOURCE_KIND", "").strip().lower()
    if kind in {"fixture", "synthetic", "test"}:
        return True
    parts = Path(path).resolve().parts
    lowered = {p.lower() for p in parts}
    return any(marker in lowered for marker in _FIXTURE_MARKERS)


def _resolve_image_area_ratio(
    *,
    image_area_ratio: float | None,
    unit_pdf_path: Path | str | None,
    page_start: int | None,
    page_end: int | None,
) -> float:
    if image_area_ratio is not None:
        return float(image_area_ratio)
    if (
        unit_pdf_path is not None
        and page_start is not None
        and page_end is not None
    ):
        return compute_image_area_ratio(unit_pdf_path, page_start, page_end)
    return 0.0


def evaluate_hard_gate(
    text: str,
    *,
    page_count: int,
    pdf_path: Path | str | None = None,
    unit_pdf_path: Path | str | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    image_area_ratio: float | None = None,
    parse_failed: bool = False,
) -> GateResult:
    """Evaluate hard NotReady then soft Review; Ready only when all clear.

    Order: fixture → parse_failed → structure_zero → printable → soft Review
    pair → mean_chars → Ready. Soft overrides mean_chars NotReady only when
    both soft conditions match.
    """
    mean, printable = compute_yield_metrics(text, page_count)
    img_ratio = _resolve_image_area_ratio(
        image_area_ratio=image_area_ratio,
        unit_pdf_path=unit_pdf_path if unit_pdf_path is not None else pdf_path,
        page_start=page_start,
        page_end=page_end,
    )
    mean_thresh = _threshold_mean_chars()
    printable_thresh = _threshold_printable()
    image_thresh = _threshold_image_area()
    soft_chars_thresh = _threshold_soft_chars()

    metrics: dict[str, Any] = {
        "mean_chars_per_page": mean,
        "printable_ratio": printable,
        "image_area_ratio": img_ratio,
        "page_count": page_count,
        "char_count": len(text),
        "mean_chars_threshold": mean_thresh,
        "printable_ratio_threshold": printable_thresh,
        "image_area_ratio_threshold": image_thresh,
        "soft_chars_per_page_threshold": soft_chars_thresh,
    }

    if is_fixture_source(pdf_path):
        metrics["fixture_refuse"] = True
        return GateResult(
            passed=False,
            disposition="NotReady",
            gate_reason="fixture_refuse",
            gate_metrics=metrics,
        )

    if parse_failed:
        metrics["parse_failed"] = True
        return GateResult(
            passed=False,
            disposition="NotReady",
            gate_reason="parse_failed",
            gate_metrics=metrics,
        )

    stripped = text.strip()
    if not stripped or page_count <= 0:
        metrics["structure_zero"] = True
        return GateResult(
            passed=False,
            disposition="NotReady",
            gate_reason="structure_zero",
            gate_metrics=metrics,
        )

    if printable < printable_thresh:
        return GateResult(
            passed=False,
            disposition="NotReady",
            gate_reason="printable_ratio",
            gate_metrics=metrics,
        )

    soft_pair = img_ratio > image_thresh and mean < soft_chars_thresh
    if soft_pair:
        return GateResult(
            passed=False,
            disposition="Review",
            gate_reason="image_area_soft",
            gate_metrics=metrics,
        )

    if mean < mean_thresh:
        return GateResult(
            passed=False,
            disposition="NotReady",
            gate_reason="mean_chars_per_page",
            gate_metrics=metrics,
        )

    return GateResult(
        passed=True,
        disposition="Ready",
        gate_reason=None,
        gate_metrics=metrics,
    )
