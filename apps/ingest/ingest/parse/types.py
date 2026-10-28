from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ParsePath = Literal["marker", "pymupdf_fallback", "failed"]


@dataclass(frozen=True)
class ParseResult:
    """Outcome of a single PDF parse attempt (primary or fallback)."""

    text: str
    path: ParsePath
    page_count: int
    error: str | None = None


@dataclass(frozen=True)
class ParseMetrics:
    mean_chars_per_page: float
    printable_ratio: float
    char_count: int


def compute_metrics(text: str, page_count: int) -> ParseMetrics:
    char_count = len(text)
    mean = char_count / page_count if page_count > 0 else 0.0
    if char_count == 0:
        printable = 0.0
    else:
        printable_chars = sum(
            1 for ch in text if ch.isprintable() or ch in "\n\r\t"
        )
        printable = printable_chars / char_count
    return ParseMetrics(
        mean_chars_per_page=mean,
        printable_ratio=printable,
        char_count=char_count,
    )
