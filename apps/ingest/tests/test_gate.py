from __future__ import annotations

from pathlib import Path

import pytest
from app.gate import evaluate_hard_gate, image_area_ratio, is_fixture_source


def _rich_text(pages: int = 2) -> str:
    return ("Hello world. " * 40 + "\n") * pages


def test_hard_gate_pass_above_thresholds() -> None:
    text = _rich_text(5)
    result = evaluate_hard_gate(text, page_count=2, image_area_ratio=0.1)
    assert result.passed is True
    assert result.disposition == "Ready"
    assert result.gate_reason is None
    assert result.gate_metrics["mean_chars_per_page"] >= 200
    assert result.gate_metrics["printable_ratio"] >= 0.90
    assert "image_area_ratio" in result.gate_metrics
    assert "image_area_ratio_threshold" in result.gate_metrics
    assert "soft_chars_per_page_threshold" in result.gate_metrics
    assert "mean_chars_threshold" in result.gate_metrics
    assert "printable_ratio_threshold" in result.gate_metrics


def test_hard_gate_mean_chars_fail() -> None:
    text = "short"
    result = evaluate_hard_gate(text, page_count=2, image_area_ratio=0.1)
    assert result.passed is False
    assert result.disposition == "NotReady"
    assert result.gate_reason == "mean_chars_per_page"
    assert "mean_chars_per_page" in result.gate_metrics


def test_hard_gate_printable_ratio_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATE_MEAN_CHARS_PER_PAGE", "1")
    # Mostly non-printable control chars (excluding \n\r\t which count as printable).
    text = ("\x00" * 100) + "a"
    result = evaluate_hard_gate(text, page_count=1, image_area_ratio=0.1)
    assert result.passed is False
    assert result.disposition == "NotReady"
    assert result.gate_reason == "printable_ratio"


def test_hard_gate_structure_zero() -> None:
    result = evaluate_hard_gate("   \n  ", page_count=2, image_area_ratio=0.9)
    assert result.passed is False
    assert result.disposition == "NotReady"
    assert result.gate_reason == "structure_zero"


def test_hard_gate_parse_failed() -> None:
    text = ("x" * 500) * 2
    result = evaluate_hard_gate(
        text, page_count=2, parse_failed=True, image_area_ratio=0.9
    )
    assert result.passed is False
    assert result.disposition == "NotReady"
    assert result.gate_reason == "parse_failed"


def test_fixture_path_and_env_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_pdf = tmp_path / "fixtures" / "book.pdf"
    fixture_pdf.parent.mkdir()
    fixture_pdf.write_bytes(b"%PDF")
    assert is_fixture_source(fixture_pdf) is True

    text = _rich_text(5)
    result = evaluate_hard_gate(
        text, page_count=2, pdf_path=fixture_pdf, image_area_ratio=0.9
    )
    assert result.passed is False
    assert result.disposition == "NotReady"
    assert result.gate_reason == "fixture_refuse"

    real = tmp_path / "textbooks" / "book.pdf"
    real.parent.mkdir()
    real.write_bytes(b"%PDF")
    monkeypatch.setenv("INGEST_SOURCE_KIND", "fixture")
    assert is_fixture_source(real) is True
    gated = evaluate_hard_gate(
        text, page_count=2, pdf_path=real, image_area_ratio=0.9
    )
    assert gated.gate_reason == "fixture_refuse"
    assert gated.disposition == "NotReady"


def test_soft_review_pair_overrides_mean_chars() -> None:
    # mean_chars << hard (200) and << soft (50); high image ratio → Review.
    text = "hi"  # 2 chars / 2 pages = 1.0 mean
    result = evaluate_hard_gate(text, page_count=2, image_area_ratio=0.85)
    assert result.passed is False
    assert result.disposition == "Review"
    assert result.gate_reason == "image_area_soft"
    assert result.gate_metrics["image_area_ratio"] == 0.85
    assert result.gate_metrics["mean_chars_per_page"] < 50
    assert result.gate_metrics["image_area_ratio_threshold"] == 0.70
    assert result.gate_metrics["soft_chars_per_page_threshold"] == 50.0


def test_mean_chars_only_when_soft_pair_false() -> None:
    # Low chars but image ratio below soft threshold → hard mean_chars NotReady.
    text = "hi"
    result = evaluate_hard_gate(text, page_count=2, image_area_ratio=0.2)
    assert result.disposition == "NotReady"
    assert result.gate_reason == "mean_chars_per_page"


def test_soft_tunable_to_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    # Raise soft thresholds so soft pair is false; raise hard mean so text passes.
    monkeypatch.setenv("GATE_SOFT_CHARS_PER_PAGE", "1")
    monkeypatch.setenv("GATE_IMAGE_AREA_RATIO", "0.99")
    monkeypatch.setenv("GATE_MEAN_CHARS_PER_PAGE", "1")
    text = "hello world printable"
    result = evaluate_hard_gate(text, page_count=1, image_area_ratio=0.85)
    assert result.disposition == "Ready"
    assert result.passed is True
    assert result.gate_metrics["image_area_ratio"] == 0.85
    assert result.gate_metrics["soft_chars_per_page_threshold"] == 1.0
    assert result.gate_metrics["image_area_ratio_threshold"] == 0.99


def test_hard_tunable_to_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATE_MEAN_CHARS_PER_PAGE", "10000")
    monkeypatch.setenv("GATE_IMAGE_AREA_RATIO", "0.99")  # soft pair false
    text = _rich_text(2)
    result = evaluate_hard_gate(text, page_count=2, image_area_ratio=0.1)
    assert result.disposition == "NotReady"
    assert result.gate_reason == "mean_chars_per_page"


def test_printable_hard_beats_soft_pair() -> None:
    # Soft would match (high image, low chars) but printable fails first.
    text = ("\x00" * 100) + "a"
    result = evaluate_hard_gate(text, page_count=1, image_area_ratio=0.9)
    assert result.disposition == "NotReady"
    assert result.gate_reason == "printable_ratio"


def test_structure_beats_soft_pair() -> None:
    result = evaluate_hard_gate("", page_count=2, image_area_ratio=0.9)
    assert result.disposition == "NotReady"
    assert result.gate_reason == "structure_zero"


def test_image_area_ratio_mean_of_clipped_raster(tmp_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    # Page 0: full-page raster via insert_image from a pixmap.
    page0 = doc.new_page(width=200, height=200)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200))
    pix.set_rect(pix.irect, (255, 0, 0))
    page0.insert_image(page0.rect, pixmap=pix)

    # Page 1: no images.
    doc.new_page(width=200, height=200)

    pdf = tmp_path / "img.pdf"
    doc.save(pdf)
    doc.close()

    ratio_both = image_area_ratio(pdf, 0, 1)
    # Mean of ~1.0 and 0.0 ≈ 0.5
    assert 0.4 <= ratio_both <= 0.6

    ratio_img_only = image_area_ratio(pdf, 0, 0)
    assert ratio_img_only > 0.9

    ratio_empty = image_area_ratio(pdf, 1, 1)
    assert ratio_empty == 0.0

    # Out-of-range pages still count toward the span mean as 0.0.
    ratio_oor = image_area_ratio(pdf, 0, 2)
    assert 0.25 <= ratio_oor <= 0.45  # ~1.0, 0.0, 0.0 → ~0.33
