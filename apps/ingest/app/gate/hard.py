from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.parse.result import compute_yield_metrics

DEFAULT_MEAN_CHARS = 200.0
DEFAULT_PRINTABLE_RATIO = 0.90

_FIXTURE_MARKERS = ("fixture", "synthetic", "fixtures")


@dataclass(frozen=True, slots=True)
class GateResult:
    """Hard-gate outcome for one unit span (story 2.3)."""

    passed: bool
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


def evaluate_hard_gate(
    text: str,
    *,
    page_count: int,
    pdf_path: Path | str | None = None,
    parse_failed: bool = False,
) -> GateResult:
    """Hard NotReady when yield thresholds fail, structure is empty, or fixture.

    Soft Review / image-area gate is out of scope (story 2.4).
    """
    mean, printable = compute_yield_metrics(text, page_count)
    metrics: dict[str, Any] = {
        "mean_chars_per_page": mean,
        "printable_ratio": printable,
        "page_count": page_count,
        "char_count": len(text),
        "mean_chars_threshold": _threshold_mean_chars(),
        "printable_ratio_threshold": _threshold_printable(),
    }

    if is_fixture_source(pdf_path):
        metrics["fixture_refuse"] = True
        return GateResult(
            passed=False,
            gate_reason="fixture_refuse",
            gate_metrics=metrics,
        )

    if parse_failed:
        metrics["parse_failed"] = True
        return GateResult(
            passed=False,
            gate_reason="parse_failed",
            gate_metrics=metrics,
        )

    stripped = text.strip()
    if not stripped or page_count <= 0:
        metrics["structure_zero"] = True
        return GateResult(
            passed=False,
            gate_reason="structure_zero",
            gate_metrics=metrics,
        )

    if mean < _threshold_mean_chars():
        return GateResult(
            passed=False,
            gate_reason="mean_chars_per_page",
            gate_metrics=metrics,
        )

    if printable < _threshold_printable():
        return GateResult(
            passed=False,
            gate_reason="printable_ratio",
            gate_metrics=metrics,
        )

    return GateResult(passed=True, gate_reason=None, gate_metrics=metrics)
