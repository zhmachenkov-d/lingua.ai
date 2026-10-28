from __future__ import annotations

from pathlib import Path

from app.units import ef4_beg_sb
from app.units.span import UnitSpan

_REGISTRY: dict[str, tuple[UnitSpan, ...]] = {
    ef4_beg_sb.TEXTBOOK_ID: ef4_beg_sb.UNITS,
}


def list_units(textbook_id: str) -> tuple[UnitSpan, ...]:
    try:
        return _REGISTRY[textbook_id]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown textbook_id={textbook_id!r}; known: {known}") from exc


def get_unit(unit_ref: str) -> UnitSpan:
    if "/" not in unit_ref:
        raise KeyError(f"unit_ref must be textbook_id/code, got {unit_ref!r}")
    textbook_id, code = unit_ref.split("/", 1)
    for span in list_units(textbook_id):
        if span.code == code:
            return span
    raise KeyError(f"Unknown unit_ref={unit_ref!r}")


def extract_unit_text(pdf_path: Path, span: UnitSpan) -> str:
    """Extract text for ``span`` from a (preferably searchable) PDF."""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        if span.page_start < 0 or span.page_end >= doc.page_count:
            raise ValueError(
                f"{span.unit_ref} pages {span.page_start}-{span.page_end} "
                f"out of range for {pdf_path} ({doc.page_count} pages)"
            )
        parts: list[str] = []
        for i in range(span.page_start, span.page_end + 1):
            parts.append(doc[i].get_text("text") or "")
        return "\n".join(parts)
    finally:
        doc.close()
