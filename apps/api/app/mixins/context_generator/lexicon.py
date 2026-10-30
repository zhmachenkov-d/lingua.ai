"""Free Dictionary fetch for Context Generator — empty skip vs fail honesty."""

from __future__ import annotations

from typing import Final
from urllib.parse import quote

import httpx

from app.mixins.context_generator.generate import LexiconEntry

FREE_DICT_BASE: Final = "https://api.dictionaryapi.dev/api/v2/entries/en/"
_TIMEOUT_SECONDS: Final = 10.0


class LexiconUnavailable(Exception):
    """Required lexicon fetch failed (429 / transport) — map to WS ``error``."""

    def __init__(self, message: str = "lexicon unavailable") -> None:
        super().__init__(message)


def _first_definition(payload: object) -> str | None:
    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    if not isinstance(first, dict):
        return None
    meanings = first.get("meanings")
    if not isinstance(meanings, list):
        return None
    for meaning in meanings:
        if not isinstance(meaning, dict):
            continue
        definitions = meaning.get("definitions")
        if not isinstance(definitions, list):
            continue
        for item in definitions:
            if not isinstance(item, dict):
                continue
            raw = item.get("definition")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


async def fetch_lemma_entries(
    lemmas: list[str],
    *,
    client: httpx.AsyncClient | None = None,
) -> list[LexiconEntry]:
    """Fetch Free Dict defs for lemmas.

    Empty/null/absent material → empty list (CG skip, not an error).
    HTTP 429 or transport/timeout → ``LexiconUnavailable`` (WS ``error``).
    Per-lemma 404 / empty JSON → omit that lemma (partial material ok).
    """
    if not lemmas:
        return []

    own_client = client is None
    http = client if client is not None else httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
    entries: list[LexiconEntry] = []
    try:
        for lemma in lemmas:
            word = lemma.strip()
            if not word:
                continue
            url = FREE_DICT_BASE + quote(word.casefold(), safe="")
            try:
                response = await http.get(url)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                raise LexiconUnavailable("lexicon transport error") from exc
            if response.status_code == 429:
                raise LexiconUnavailable("lexicon rate limited")
            if response.status_code == 404:
                continue
            if response.status_code >= 500:
                raise LexiconUnavailable(
                    f"lexicon upstream {response.status_code}"
                )
            if response.status_code != 200:
                # Other client errors → treat as empty for that lemma.
                continue
            try:
                payload = response.json()
            except ValueError:
                continue
            definition = _first_definition(payload)
            if definition:
                entries.append(
                    LexiconEntry(lemma=word.casefold(), definition=definition)
                )
    finally:
        if own_client:
            await http.aclose()
    return entries
