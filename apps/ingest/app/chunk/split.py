from __future__ import annotations

import os
import re

DEFAULT_MAX_CHARS = 1800
DEFAULT_MIN_CHARS = 4

_PARA_SPLIT = re.compile(r"\n\s*\n+")


def _max_chars() -> int:
    raw = os.environ.get("CHUNK_MAX_CHARS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_MAX_CHARS


def _min_chars() -> int:
    raw = os.environ.get("CHUNK_MIN_CHARS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_MIN_CHARS


def split_paragraphs(
    text: str,
    *,
    max_chars: int | None = None,
    min_chars: int | None = None,
) -> list[str]:
    """Boring paragraph split with min-length floor and hard size cap (post hard-gate only)."""
    cap = max_chars if max_chars is not None else _max_chars()
    floor = min_chars if min_chars is not None else _min_chars()
    if cap <= 0:
        raise ValueError(f"max_chars must be positive, got {cap}")
    if floor <= 0:
        raise ValueError(f"min_chars must be positive, got {floor}")

    raw_paras = [p.strip() for p in _PARA_SPLIT.split(text) if p.strip()]
    if not raw_paras and text.strip():
        raw_paras = [text.strip()]

    chunks: list[str] = []
    for para in raw_paras:
        if len(para) <= cap:
            if len(para) >= floor:
                chunks.append(para)
            continue
        start = 0
        while start < len(para):
            end = min(start + cap, len(para))
            if end < len(para):
                # Prefer a whitespace break near the cap.
                break_at = para.rfind(" ", start, end)
                if break_at > start + (cap // 4):
                    end = break_at
            piece = para[start:end].strip()
            if piece and len(piece) >= floor:
                chunks.append(piece)
            start = end if end > start else start + cap
    return chunks
