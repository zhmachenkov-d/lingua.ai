"""DeepSeek OpenAI-compatible adapter: flash primary, v4-pro escalation (AD-8).

Never falls back to free-form chat. Missing key / dual failure are typed errors.
Adapter completion text is never product chat — callers use templates only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

PRIMARY_MODEL: Final = "deepseek-flash"
ESCALATION_MODEL: Final = "deepseek-v4-pro"
BASE_URL: Final = "https://api.deepseek.com"
REQUEST_TIMEOUT_SECONDS: Final = 30.0
MAX_TOKENS: Final = 256

# Fixed RU notice when escalation succeeds (FR-1). Never embed in message.
BACKUP_NOTICE: Final = "Сейчас отвечает запасная модель."

_CLASSIFY_SYSTEM: Final = (
    "You are a stub intent classifier for an English-learning tutor. "
    "Reply with a single token: none. Do not chat."
)


class LlmMisconfigured(Exception):
    """Missing or empty DEEPSEEK_API_KEY."""

    code: Final = "llm_misconfigured"


class LlmUnavailable(Exception):
    """Primary and escalation both failed, or gateway unreachable."""

    code: Final = "llm_unavailable"


@dataclass(frozen=True, slots=True)
class ClassifyResult:
    """Skeleton classify outcome. handoff is always None until domain nodes exist."""

    handoff: None
    used_backup: bool


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


async def _complete_once(
    client: AsyncOpenAI,
    *,
    model: str,
    text: str,
) -> None:
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


async def _try_model(client: AsyncOpenAI, *, model: str, text: str) -> bool:
    """Return True on success; False on recoverable primary/escalation failure."""
    try:
        await _complete_once(client, model=model, text=text)
        return True
    except LlmUnavailable:
        return False
    except (APITimeoutError, APIConnectionError, APIStatusError, TimeoutError, OSError):
        return False


async def classify_turn(
    text: str,
    *,
    http_client: object | None = None,
    client: AsyncOpenAI | None = None,
) -> ClassifyResult:
    """Call primary then escalation. Always returns handoff=None on success.

    Raises:
        LlmMisconfigured: empty/unset DEEPSEEK_API_KEY.
        LlmUnavailable: both models fail / unreachable / incomplete.
    """
    owns_client = False
    if client is None:
        key = _api_key()
        if not key:
            raise LlmMisconfigured("DEEPSEEK_API_KEY is missing or empty")
        client = _client(api_key=key, http_client=http_client)
        owns_client = True

    try:
        if await _try_model(client, model=PRIMARY_MODEL, text=text):
            return ClassifyResult(handoff=None, used_backup=False)
        if await _try_model(client, model=ESCALATION_MODEL, text=text):
            return ClassifyResult(handoff=None, used_backup=True)
        raise LlmUnavailable("primary and escalation models unavailable")
    finally:
        if owns_client:
            await client.close()
