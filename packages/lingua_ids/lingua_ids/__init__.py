"""Single source of truth for MVP textbook_id string constants (AD-11)."""

EF4_BEG_SB_ID = "ef4-beg-sb"
EF4_BEG_WB_ID = "ef4-beg-wb"

MVP_TEXTBOOK_IDS: frozenset[str] = frozenset({EF4_BEG_SB_ID, EF4_BEG_WB_ID})

__all__ = [
    "EF4_BEG_SB_ID",
    "EF4_BEG_WB_ID",
    "MVP_TEXTBOOK_IDS",
]
