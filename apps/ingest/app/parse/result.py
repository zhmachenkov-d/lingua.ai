from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

ParseStatus = Literal["ok", "fallback", "parse_failed", "missing_pdf"]

METRIC_JSON_KEYS: Final[tuple[str, ...]] = (
    "pdf",
    "adapter_id",
    "status",
    "peak_rss_bytes",
    "wall_time_ms",
    "mean_chars_per_page",
    "printable_ratio",
    "page_count",
)


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Outcome of a PDF parse attempt (primary, fallback, or failure)."""

    text: str
    page_count: int
    mean_chars_per_page: float | None
    printable_ratio: float | None
    wall_time_ms: int | None
    adapter_id: str | None
    status: ParseStatus
    error: str | None = None


def compute_yield_metrics(
    text: str, page_count: int
) -> tuple[float, float]:
    """Return (mean_chars_per_page, printable_ratio)."""
    char_count = len(text)
    mean = char_count / page_count if page_count > 0 else 0.0
    if char_count == 0:
        printable = 0.0
    else:
        printable_chars = sum(
            1 for ch in text if ch.isprintable() or ch in "\n\r\t"
        )
        printable = printable_chars / char_count
    return mean, printable
