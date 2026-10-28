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
