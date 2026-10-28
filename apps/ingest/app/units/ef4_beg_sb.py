"""Static unit map for English File 4th Beginner Student's Book.

Page indices are **zero-based PDF pages**. Printed page N in the TOC maps to
PDF index N-1 on the owner scan (cover = printed 1 = index 0). Spans were
derived from the book contents listing and spot-checked against ocrmypdf text
(2026-10-28). Ends are exclusive-of-next-start (inclusive ``page_end``).
"""

from __future__ import annotations

from app.units.span import UnitSpan

TEXTBOOK_ID = "ef4-beg-sb"

# (code, title, page_start_0based) — ordered by start page.
_STARTS: tuple[tuple[str, str, int], ...] = (
    ("1A", "A cappuccino, please", 5),
    ("1B", "World music", 7),
    ("PE1", "Practical English Episode 1", 9),
    ("2A", "Are you on holiday?", 11),
    ("2B", "That's my bus!", 13),
    ("RC1-2", "Revise and Check 1&2", 15),
    ("3A", "Where are my keys?", 17),
    ("3B", "Souvenirs", 19),
    ("PE2", "Practical English Episode 2", 21),
    ("4A", "Meet the family", 23),
    ("4B", "The perfect car", 25),
    ("RC3-4", "Revise and Check 3&4", 27),
    ("5A", "A big breakfast?", 29),
    ("5B", "A very long flight", 31),
    ("PE3", "Practical English Episode 3", 33),
    ("6A", "A school reunion", 35),
    ("6B", "Good morning, goodnight", 37),
    ("RC5-6", "Revise and Check 5&6", 39),
    ("7A", "Have a nice weekend!", 41),
    ("7B", "Lights, camera, action!", 43),
    ("PE4", "Practical English Episode 4", 45),
    ("8A", "Can I park here?", 47),
    ("8B", "I love cooking", 49),
    ("RC7-8", "Revise and Check 7&8", 51),
    ("9A", "Everything's fine!", 53),
    ("9B", "Working undercover", 55),
    ("PE5", "Practical English Episode 5", 57),
    ("10A", "A room with a view", 59),
    ("10B", "Where were you?", 61),
    ("RC9-10", "Revise and Check 9&10", 63),
    ("11A", "A new life in the USA", 65),
    ("11B", "How was your day?", 67),
    ("PE6", "Practical English Episode 6", 69),
    ("12A", "Strangers on a train", 71),
    ("12B", "Revise the past", 73),
    ("RC11-12", "Revise and Check 11&12", 75),
    ("COM", "Communication", 77),
    ("WR", "Writing", 85),
    ("LIS", "Listening", 87),
    ("GB", "Grammar Bank", 91),
    ("VB", "Vocabulary Bank", 115),
    ("WPL", "Words and phrases to learn", 130),
    ("RIV", "Regular and irregular verbs", 132),
    ("SB", "Sound Bank", 133),
)

# Last PDF page index for this corpus (135 pages → 0..134).
_LAST_PAGE = 134


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
