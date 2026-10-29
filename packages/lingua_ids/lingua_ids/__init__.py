"""Single source of truth for MVP textbook_id and embedding pin (AD-11 / AD-12)."""

EF4_BEG_SB_ID = "ef4-beg-sb"
EF4_BEG_WB_ID = "ef4-beg-wb"

MVP_TEXTBOOK_IDS: frozenset[str] = frozenset({EF4_BEG_SB_ID, EF4_BEG_WB_ID})

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DIMS = 1024

__all__ = [
    "EF4_BEG_SB_ID",
    "EF4_BEG_WB_ID",
    "MVP_TEXTBOOK_IDS",
    "EMBEDDING_MODEL_NAME",
    "EMBEDDING_DIMS",
]
