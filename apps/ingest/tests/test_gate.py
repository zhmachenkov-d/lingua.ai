from __future__ import annotations

from pathlib import Path

import pytest
from app.gate import evaluate_hard_gate, is_fixture_source


def test_hard_gate_pass_above_thresholds() -> None:
    text = ("Hello world. " * 40 + "\n") * 5  # plenty of printable chars
    result = evaluate_hard_gate(text, page_count=2)
    assert result.passed is True
    assert result.gate_reason is None
    assert result.gate_metrics["mean_chars_per_page"] >= 200
    assert result.gate_metrics["printable_ratio"] >= 0.90


def test_hard_gate_mean_chars_fail() -> None:
    text = "short"
    result = evaluate_hard_gate(text, page_count=2)
    assert result.passed is False
    assert result.gate_reason == "mean_chars_per_page"
    assert "mean_chars_per_page" in result.gate_metrics


def test_hard_gate_printable_ratio_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATE_MEAN_CHARS_PER_PAGE", "1")
    # Mostly non-printable control chars (excluding \n\r\t which count as printable).
    text = ("\x00" * 100) + "a"
    result = evaluate_hard_gate(text, page_count=1)
    assert result.passed is False
    assert result.gate_reason == "printable_ratio"


def test_hard_gate_structure_zero() -> None:
    result = evaluate_hard_gate("   \n  ", page_count=2)
    assert result.passed is False
    assert result.gate_reason == "structure_zero"


def test_hard_gate_parse_failed() -> None:
    text = ("x" * 500) * 2
    result = evaluate_hard_gate(text, page_count=2, parse_failed=True)
    assert result.passed is False
    assert result.gate_reason == "parse_failed"


def test_fixture_path_and_env_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_pdf = tmp_path / "fixtures" / "book.pdf"
    fixture_pdf.parent.mkdir()
    fixture_pdf.write_bytes(b"%PDF")
    assert is_fixture_source(fixture_pdf) is True

    text = ("Hello world. " * 40 + "\n") * 5
    result = evaluate_hard_gate(text, page_count=2, pdf_path=fixture_pdf)
    assert result.passed is False
    assert result.gate_reason == "fixture_refuse"

    real = tmp_path / "textbooks" / "book.pdf"
    real.parent.mkdir()
    real.write_bytes(b"%PDF")
    monkeypatch.setenv("INGEST_SOURCE_KIND", "fixture")
    assert is_fixture_source(real) is True
    gated = evaluate_hard_gate(text, page_count=2, pdf_path=real)
    assert gated.gate_reason == "fixture_refuse"
