"""Static unit map for English File 4th Beginner Workbook.

Page indices are **zero-based PDF pages**. On the owner WB scan the TOC
printed page N maps to PDF index N (front matter 0–3; lesson 1A starts at
index 4). Spans were derived from the book contents listing and spot-checked
against ocrmypdf text (2026-10-29). Ends are exclusive-of-next-start
(inclusive ``page_end``). Corpus is 75 pages → indices 0..74.
"""

from __future__ import annotations

from lingua_ids import EF4_BEG_WB_ID

from app.units.span import UnitSpan

TEXTBOOK_ID = EF4_BEG_WB_ID

# (code, title, page_start_0based) — ordered by start page.
_STARTS: tuple[tuple[str, str, int], ...] = (
    ("1A", "A cappuccino, please", 4),
    ("1B", "World music", 6),
    ("PE1", "Practical English Episode 1", 8),
    ("2A", "Are you on holiday?", 10),
    ("2B", "That's my bus!", 12),
    ("3A", "Where are my keys?", 14),
    ("3B", "Souvenirs", 16),
    ("PE2", "Practical English Episode 2", 18),
    ("4A", "Meet the family", 20),
    ("4B", "The perfect car", 22),
    ("5A", "A big breakfast?", 24),
    ("5B", "A very long flight", 26),
    ("PE3", "Practical English Episode 3", 28),
    ("6A", "A school reunion", 30),
    ("6B", "Good morning, goodnight", 32),
    ("7A", "Have a nice weekend!", 34),
    ("7B", "Lights, camera, action!", 36),
    ("PE4", "Practical English Episode 4", 38),
    ("8A", "Can I park here?", 40),
    ("8B", "I love cooking", 42),
    ("9A", "Everything's fine!", 44),
    ("9B", "Working undercover", 46),
    ("PE5", "Practical English Episode 5", 48),
    ("10A", "A room with a view", 50),
    ("10B", "Where were you?", 52),
    ("11A", "A new life in the USA", 54),
    ("11B", "How was your day?", 56),
    ("PE6", "Practical English Episode 6", 58),
    ("12A", "Strangers on a train", 60),
    ("12B", "Revise the past", 62),
    ("AK", "Answer Key", 64),
)

# Last PDF page index for this corpus (75 pages → 0..74).
_LAST_PAGE = 74


def _build_units() -> tuple[UnitSpan, ...]:
    units: list[UnitSpan] = []
    for i, (code, title, start) in enumerate(_STARTS):
        if i + 1 < len(_STARTS):
            end = _STARTS[i + 1][2] - 1
        else:
            end = _LAST_PAGE
        if end < start:
            raise ValueError(f"Invalid span for {code}: {start}-{end}")
        units.append(
            UnitSpan(
                textbook_id=TEXTBOOK_ID,
                code=code,
                title=title,
                page_start=start,
                page_end=end,
            )
        )
    return tuple(units)


UNITS: tuple[UnitSpan, ...] = _build_units()
