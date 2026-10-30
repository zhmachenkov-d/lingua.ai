"""CEFR i+1 band policy — overall or +1 max; undefined when overall invalid."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.schemas.cefr import CefrLevel

CEFR_LADDER: Final[tuple[CefrLevel, ...]] = ("A1", "A2", "B1", "B2", "C1", "C2")
_INDEX: Final[dict[CefrLevel, int]] = {level: i for i, level in enumerate(CEFR_LADDER)}


@dataclass(frozen=True, slots=True)
class CefrBand:
    """Limiter target band: ``overall`` with ceiling ``min(overall+1, C2)``."""

    overall: CefrLevel
    ceiling: CefrLevel


def resolve_target_band(overall: CefrLevel | None) -> CefrBand | None:
    """Map valid overall to target/ceiling; None when overall missing/invalid.

    By-skill bands are ignored (MVP overall-only). Never invents a default band.
    """
    if overall is None or overall not in _INDEX:
        return None
    idx = _INDEX[overall]
    ceiling = CEFR_LADDER[min(idx + 1, len(CEFR_LADDER) - 1)]
    return CefrBand(overall=overall, ceiling=ceiling)


def format_band_annotation(band: CefrBand) -> str:
    """Observable teach-surface band line (beyond the empty/invalid gate alone)."""
    if band.overall == band.ceiling:
        return f"[CEFR target: {band.overall}]"
    return f"[CEFR target: {band.overall}–{band.ceiling}]"
