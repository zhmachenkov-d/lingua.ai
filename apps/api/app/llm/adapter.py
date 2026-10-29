"""DeepSeek OpenAI-compatible adapter: flash primary, v4-pro escalation (AD-8).

Classifies intent + EXPERIENCE confidence band. CTA intent tokens short-circuit
to high confidence without an LLM call. Never falls back to free-form chat.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Final, Literal

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

PRIMARY_MODEL: Final = "deepseek-flash"
ESCALATION_MODEL: Final = "deepseek-v4-pro"
BASE_URL: Final = "https://api.deepseek.com"
REQUEST_TIMEOUT_SECONDS: Final = 30.0
MAX_TOKENS: Final = 256

# Fixed RU notice when escalation succeeds (FR-1). Never embed in message.
BACKUP_NOTICE: Final = "Сейчас отвечает запасная модель."

IntentName = Literal["tutor_unit", "vocab_lookup", "review_daily"]
ConfidenceBand = Literal["high", "low", "unknown", "tie"]

# CTA chip ids and architecture intent tokens → high-confidence handoff intents.
_CTA_INTENT_MAP: Final[dict[str, IntentName]] = {
    "tutor": "tutor_unit",
    "tutor_unit": "tutor_unit",
    "vocabulary": "vocab_lookup",
    "vocab_lookup": "vocab_lookup",
    "review": "review_daily",
    "review_daily": "review_daily",
}

_VALID_INTENTS: Final[frozenset[str]] = frozenset(
    {"tutor_unit", "vocab_lookup", "review_daily"}
)
_VALID_BANDS: Final[frozenset[str]] = frozenset({"high", "low", "unknown", "tie"})

_CLASSIFY_SYSTEM: Final = (
    "You classify learner messages for an English-learning tutor app. "
    "Reply with JSON only, no markdown: "
    '{"intent":"tutor_unit"|"vocab_lookup"|"review_daily"|null,'
    '"band":"high"|"low"|"unknown"|"tie"}. '
    "band=high only when exactly one agent intent is clear. "
    "band=tie when two intents are equally likely (intent null). "
    "band=low when the agent is unclear. "
    "band=unknown when the message is not about lesson/vocab/review. "
    "Never chat."
)

_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}")


class LlmMisconfigured(Exception):
    """Missing/empty DEEPSEEK_API_KEY, or provider rejected the key (401/403)."""

    code: Final = "llm_misconfigured"


class LlmUnavailable(Exception):
    """Primary and escalation both failed, or gateway unreachable."""

    code: Final = "llm_unavailable"


@dataclass(frozen=True, slots=True)
class ClassifyResult:
    """Intent + EXPERIENCE band. Handoff only when band is high and intent set."""

    intent: IntentName | None
    band: ConfidenceBand
    used_backup: bool

    @property
    def handoff(self) -> IntentName | None:
        if self.band == "high" and self.intent is not None:
            return self.intent
        return None


def _api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "").strip()


def _client(*, api_key: str, http_client: object | None = None) -> AsyncOpenAI:
    if http_client is not None:
        return AsyncOpenAI(
            api_key=api_key,
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
            http_client=http_client,  # type: ignore[arg-type]
        )
    return AsyncOpenAI(
        api_key=api_key,
        base_url=BASE_URL,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _cta_short_circuit(text: str) -> ClassifyResult | None:
    """Exact CTA / intent token → high confidence without LLM."""
    key = text.strip().lower()
    intent = _CTA_INTENT_MAP.get(key)
    if intent is None:
        return None
    return ClassifyResult(intent=intent, band="high", used_backup=False)


def _parse_classify_content(content: str) -> tuple[IntentName | None, ConfidenceBand]:
    """Parse model JSON into intent+band; invalid → unknown."""
    raw = content.strip()
    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        return None, "unknown"
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None, "unknown"
    if not isinstance(data, dict):
        return None, "unknown"

    band_raw = data.get("band")
    band: ConfidenceBand
    if isinstance(band_raw, str) and band_raw in _VALID_BANDS:
        band = band_raw  # type: ignore[assignment]
    else:
        return None, "unknown"

    intent_raw = data.get("intent")
    intent: IntentName | None
    if intent_raw is None or intent_raw == "null":
        intent = None
    elif isinstance(intent_raw, str) and intent_raw in _VALID_INTENTS:
        intent = intent_raw  # type: ignore[assignment]
    else:
        return None, "unknown"

    if band == "high" and intent is None:
        return None, "unknown"
    if band in ("tie", "unknown"):
        intent = None
    return intent, band


async def _complete_once(
    client: AsyncOpenAI,
    *,
    model: str,
    text: str,
) -> str:
    """One bounded chat completion. Raises on timeout/incomplete/transport errors."""
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _CLASSIFY_SYSTEM},
            {"role": "user", "content": text},
        ],
        max_tokens=MAX_TOKENS,
        temperature=0,
    )
    choices = response.choices
    if not choices:
        raise LlmUnavailable("incomplete LLM response: no choices")
    content = choices[0].message.content
    if content is None or (isinstance(content, str) and content.strip() == ""):
        raise LlmUnavailable("incomplete LLM response: empty content")
    finish = choices[0].finish_reason
    if finish not in (None, "stop", "length"):
        raise LlmUnavailable(f"incomplete LLM response: finish_reason={finish!r}")
    return content if isinstance(content, str) else str(content)


async def _try_model(client: AsyncOpenAI, *, model: str, text: str) -> str | None:
    """Return completion text on success; None on recoverable failure."""
    try:
        return await _complete_once(client, model=model, text=text)
    except LlmUnavailable:
        return None
    except APIStatusError as exc:
        if exc.status_code in (401, 403):
            raise LlmMisconfigured(
                f"provider rejected API key: HTTP {exc.status_code}"
            ) from exc
        return None
    except (APITimeoutError, APIConnectionError, TimeoutError, OSError):
        return None


async def classify_turn(
    text: str,
    *,
    http_client: object | None = None,
    client: AsyncOpenAI | None = None,
) -> ClassifyResult:
    """Classify intent + band. CTA tokens short-circuit; else primary then escalate.

    Raises:
        LlmMisconfigured: empty/unset DEEPSEEK_API_KEY, or provider 401/403.
        LlmUnavailable: both models fail / unreachable / incomplete.
    """
    cta = _cta_short_circuit(text)
    if cta is not None:
        return cta

    owns_client = False
    if client is None:
        key = _api_key()
        if not key:
            raise LlmMisconfigured("DEEPSEEK_API_KEY is missing or empty")
        client = _client(api_key=key, http_client=http_client)
        owns_client = True

    try:
        content = await _try_model(client, model=PRIMARY_MODEL, text=text)
        used_backup = False
        if content is None:
            content = await _try_model(client, model=ESCALATION_MODEL, text=text)
            used_backup = True
        if content is None:
            raise LlmUnavailable("primary and escalation models unavailable")
        intent, band = _parse_classify_content(content)
        return ClassifyResult(intent=intent, band=band, used_backup=used_backup)
    finally:
        if owns_client:
            await client.close()
