from __future__ import annotations

from app.chunk import split_paragraphs


def test_split_paragraphs_basic() -> None:
    text = "First paragraph.\n\nSecond paragraph.\n\n\nThird."
    chunks = split_paragraphs(text)
    assert chunks == ["First paragraph.", "Second paragraph.", "Third."]


def test_split_paragraphs_size_cap() -> None:
    text = "word " * 100
    chunks = split_paragraphs(text, max_chars=40)
    assert len(chunks) > 1
    assert all(len(c) <= 40 for c in chunks)
    assert "word" in "".join(chunks)


def test_split_single_block_without_blank_lines() -> None:
    text = "One continuous block without blank lines."
    assert split_paragraphs(text) == [text]


def test_split_drops_ultra_short_paragraphs() -> None:
    text = "ab\n\nNormal lesson paragraph here.\n\nxy\n\nAnother kept paragraph."
    chunks = split_paragraphs(text, min_chars=4)
    assert chunks == ["Normal lesson paragraph here.", "Another kept paragraph."]
    assert all(len(c) >= 4 for c in chunks)


def test_split_default_min_drops_three_char_scraps() -> None:
    text = "abc\n\nNormal lesson paragraph here.\n\nab"
    chunks = split_paragraphs(text)
    assert chunks == ["Normal lesson paragraph here."]
    assert all(len(c) >= 4 for c in chunks)


def test_split_all_short_returns_empty() -> None:
    text = "ab\n\nxy\n\nz"
    assert split_paragraphs(text, min_chars=4) == []
