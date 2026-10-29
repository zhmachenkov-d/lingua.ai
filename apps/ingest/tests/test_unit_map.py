from __future__ import annotations

from pathlib import Path

import pytest
from app.units import (
    EF4_BEG_SB_ID,
    EF4_BEG_WB_ID,
    extract_unit_text,
    get_unit,
    list_units,
)
from app.units.span import UnitSpan


def test_ef4_beg_sb_1a_span_and_refs() -> None:
    units = list_units(EF4_BEG_SB_ID)
    assert units[0].code == "1A"
    assert units[0].page_start == 5
    assert units[0].page_end == 6
    assert units[0].unit_ref == "ef4-beg-sb/1A"

    one_a = get_unit("ef4-beg-sb/1A")
    assert one_a.title == "A cappuccino, please"
    assert one_a.page_count == 2

    # Contiguous, non-overlapping lesson spans through Sound Bank.
    assert units[-1].code == "SB"
    assert units[-1].page_end == 134
    for prev, cur in zip(units, units[1:], strict=False):
        assert cur.page_start == prev.page_end + 1


def test_ef4_beg_wb_spans_registry_and_bounds() -> None:
    units = list_units(EF4_BEG_WB_ID)
    assert units[0].code == "1A"
    assert units[0].page_start == 4
    assert units[0].page_end == 5
    assert units[0].unit_ref == "ef4-beg-wb/1A"
    assert units[0].textbook_id == EF4_BEG_WB_ID

    one_a = get_unit("ef4-beg-wb/1A")
    assert one_a.title == "A cappuccino, please"
    assert one_a.page_count == 2

    # Distinct from Students' Book even when codes match.
    assert get_unit("ef4-beg-sb/1A").unit_ref != one_a.unit_ref

    assert units[-1].code == "AK"
    assert units[-1].page_end == 74  # 75-page corpus → indices 0..74
    for prev, cur in zip(units, units[1:], strict=False):
        assert cur.page_start == prev.page_end + 1
    assert all(u.page_end < 75 for u in units)
    assert all(u.page_start >= 0 for u in units)


def test_unknown_unit_ref() -> None:
    with pytest.raises(KeyError, match="Unknown unit_ref"):
        get_unit("ef4-beg-sb/99Z")
    with pytest.raises(KeyError, match="Unknown textbook_id"):
        list_units("no-such-book")


def test_extract_unit_text_page_slice(tmp_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    for i in range(8):
        page = doc.new_page()
        page.insert_text((72, 72), f"PAGE-{i}")
    pdf = tmp_path / "tiny.pdf"
    doc.save(pdf)
    doc.close()

    span = UnitSpan(
        textbook_id="ef4-beg-sb",
        code="1A",
        title="test",
        page_start=5,
        page_end=6,
    )
    text = extract_unit_text(pdf, span)
    assert "PAGE-5" in text
    assert "PAGE-6" in text
    assert "PAGE-4" not in text
    assert "PAGE-7" not in text
