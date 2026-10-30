"""Unit tests for the DeepSeek adapter (mocked HTTP; no live DeepSeek)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.llm.adapter import (
    BACKUP_NOTICE,
    ESCALATION_MODEL,
    PRIMARY_MODEL,
    ClassifyResult,
    LlmMisconfigured,
    LlmUnavailable,
    classify_turn,
)
from openai import APIConnectionError, APIStatusError, APITimeoutError


def _completion(content: str = '{"intent":null,"band":"unknown"}') -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    return response


def _client_with_create(
    *,
    return_value: Any | None = None,
    side_effect: Any | None = None,
) -> MagicMock:
    client = MagicMock()
    if side_effect is not None:
        client.chat.completions.create = AsyncMock(side_effect=side_effect)
    else:
        client.chat.completions.create = AsyncMock(return_value=return_value)
    return client


def test_missing_key_raises_misconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(LlmMisconfigured):
        asyncio.run(classify_turn("hello"))


def test_empty_key_raises_misconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "   ")
    with pytest.raises(LlmMisconfigured):
        asyncio.run(classify_turn("hello"))


def test_cta_tutor_short_circuits_without_llm() -> None:
    client = _client_with_create(return_value=_completion())
    result = asyncio.run(classify_turn("tutor_unit", client=client))
    assert result == ClassifyResult(
        intent="tutor_unit", band="high", used_backup=False
    )
    assert result.handoff == "tutor_unit"
    client.chat.completions.create.assert_not_awaited()


@pytest.mark.parametrize(
    ("token", "intent"),
    [
        ("tutor", "tutor_unit"),
        ("vocabulary", "vocab_lookup"),
        ("vocab_lookup", "vocab_lookup"),
        ("review", "review_daily"),
        ("review_daily", "review_daily"),
    ],
)
def test_cta_tokens_map_high_confidence(token: str, intent: str) -> None:
    result = asyncio.run(classify_turn(token, client=_client_with_create()))
    assert result.band == "high"
    assert result.intent == intent
    assert result.handoff == intent


def test_primary_success_parses_intent_band() -> None:
    client = _client_with_create(
        return_value=_completion('{"intent":"tutor_unit","band":"high"}')
    )
    result = asyncio.run(classify_turn("хочу урок", client=client))
    assert result == ClassifyResult(
        intent="tutor_unit", band="high", used_backup=False
    )
    client.chat.completions.create.assert_awaited_once()
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == PRIMARY_MODEL


def test_primary_fail_escalation_ok() -> None:
    client = _client_with_create(
        side_effect=[
            APITimeoutError(request=MagicMock()),
            _completion('{"intent":null,"band":"unknown"}'),
        ]
    )
    result = asyncio.run(classify_turn("hello", client=client))
    assert result.used_backup is True
    assert result.handoff is None
    assert result.band == "unknown"
    assert BACKUP_NOTICE.startswith("Сейчас")
    models = [c.kwargs["model"] for c in client.chat.completions.create.await_args_list]
    assert models == [PRIMARY_MODEL, ESCALATION_MODEL]


def test_low_band_has_no_handoff() -> None:
    client = _client_with_create(
        return_value=_completion('{"intent":"tutor_unit","band":"low"}')
    )
    result = asyncio.run(classify_turn("maybe lesson", client=client))
    assert result.band == "low"
    assert result.intent == "tutor_unit"
    assert result.handoff is None


def test_tie_clears_intent() -> None:
    client = _client_with_create(
        return_value=_completion('{"intent":"tutor_unit","band":"tie"}')
    )
    result = asyncio.run(classify_turn("урок или слова", client=client))
    assert result.band == "tie"
    assert result.intent is None
    assert result.handoff is None


def test_both_down_raises_unavailable() -> None:
    client = _client_with_create(
        side_effect=APIConnectionError(request=MagicMock(), message="down")
    )
    with pytest.raises(LlmUnavailable):
        asyncio.run(classify_turn("hello", client=client))
    assert client.chat.completions.create.await_count == 2


def _status_error(status_code: int) -> APIStatusError:
    response = httpx.Response(
        status_code, request=httpx.Request("POST", "https://api.deepseek.com")
    )
    return APIStatusError(f"HTTP {status_code}", response=response, body=None)


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_status_raises_misconfigured(status_code: int) -> None:
    client = _client_with_create(side_effect=_status_error(status_code))
    with pytest.raises(LlmMisconfigured):
        asyncio.run(classify_turn("hello", client=client))
    assert client.chat.completions.create.await_count == 1


def test_non_auth_status_still_unavailable() -> None:
    client = _client_with_create(side_effect=_status_error(500))
    with pytest.raises(LlmUnavailable):
        asyncio.run(classify_turn("hello", client=client))
    assert client.chat.completions.create.await_count == 2


def test_incomplete_response_treated_as_failure() -> None:
    empty = MagicMock()
    empty.choices = []
    client = _client_with_create(side_effect=[empty, empty])
    with pytest.raises(LlmUnavailable):
        asyncio.run(classify_turn("hello", client=client))


def test_classify_uses_env_key_when_building_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    fake = _client_with_create(
        return_value=_completion('{"intent":null,"band":"unknown"}')
    )
    fake.close = AsyncMock()
    with patch("app.llm.adapter._client", return_value=fake) as build:
        asyncio.run(classify_turn("hi"))
    build.assert_called_once()
    assert build.call_args.kwargs["api_key"] == "sk-test"
    fake.close.assert_awaited_once()
