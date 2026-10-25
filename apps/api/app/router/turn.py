"""Thin Router turn: CTA/blank path, sole checkpointer ``aput`` (AD-3, AD-6)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from openai import AsyncOpenAI

from app.db.checkpointer import open_checkpointer
from app.db.constants import MVP_LEARNER_ID
from app.llm.adapter import (
    BACKUP_NOTICE,
    LlmMisconfigured,
    LlmUnavailable,
    classify_turn,
)
from app.schemas.ws import ErrorCode

# Fixed RU template — never copy adapter completion text into message.
CTA_MESSAGE: Final = (
    "Выберите, чем заняться: Tutor (урок), Vocabulary (слова) или Review (повторение)."
)
CTAS: Final = ("tutor", "vocabulary", "review")

ERROR_MESSAGES: Final[dict[ErrorCode, str]] = {
    "llm_misconfigured": (
        "Языковая модель не настроена. Проверьте ключ DEEPSEEK_API_KEY."
    ),
    "llm_unavailable": ("Языковая модель сейчас недоступна. Попробуйте позже."),
    "invalid_turn_request": "Некорректный запрос хода.",
    "checkpointer_write_failed": "Не удалось сохранить состояние сессии.",
}

THREAD_ID: Final = str(MVP_LEARNER_ID)


@dataclass(frozen=True, slots=True)
class TurnSuccess:
    message: str
    ctas: tuple[str, ...]
    clarify: None
    backup_notice: str | None
    turn_id: str | None
    last_user_text: str


@dataclass(frozen=True, slots=True)
class TurnError:
    code: ErrorCode
    message: str
    turn_id: str | None


def _checkpoint_for_snapshot(
    *,
    last_user_text: str,
    turn_at: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    channel_values: dict[str, Any] = {
        "last_user_text": last_user_text,
        "active_agent": None,
        "turn_at": turn_at,
    }
    channel_versions = {key: "1" for key in channel_values}
    checkpoint: dict[str, Any] = {
        "v": 4,
        "id": str(uuid.uuid4()),
        "ts": turn_at,
        "channel_values": channel_values,
        "channel_versions": channel_versions,
        "versions_seen": {},
        "updated_channels": list(channel_values),
    }
    return checkpoint, channel_versions


async def write_turn_snapshot(
    *,
    last_user_text: str,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Persist thin Router STM snapshot. Sole ``aput`` path in the app."""
    turn_at = datetime.now(UTC).isoformat()
    checkpoint, versions = _checkpoint_for_snapshot(
        last_user_text=last_user_text,
        turn_at=turn_at,
    )
    config: dict[str, Any] = {
        "configurable": {"thread_id": THREAD_ID, "checkpoint_ns": ""}
    }
    version_map: dict[str, str | int | float] = dict(versions)
    async with open_checkpointer(database_url) as saver:
        await saver.aput(
            config,  # type: ignore[arg-type]
            checkpoint,  # type: ignore[arg-type]
            {"source": "update", "step": 0, "parents": {}},
            version_map,
        )
    values = checkpoint["channel_values"]
    assert isinstance(values, dict)
    return values


async def get_turn_snapshot(
    *,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Read the MVP learner checkpointer channels (tests / later readers)."""
    config: dict[str, Any] = {
        "configurable": {"thread_id": THREAD_ID, "checkpoint_ns": ""}
    }
    async with open_checkpointer(database_url) as saver:
        got = await saver.aget(config)  # type: ignore[arg-type]
    if got is None:
        return None
    values = got.get("channel_values")
    return dict(values) if isinstance(values, dict) else None


async def handle_turn(
    text: str,
    *,
    turn_id: str | None = None,
    database_url: str | None = None,
    http_client: object | None = None,
    llm_client: AsyncOpenAI | None = None,
) -> TurnSuccess | TurnError:
    """Blank → CTA without LLM; non-blank → classify then CTA; persist-then-complete."""
    stripped = text.strip()
    used_backup = False

    if stripped:
        try:
            result = await classify_turn(
                stripped,
                http_client=http_client,
                client=llm_client,
            )
        except LlmMisconfigured:
            return TurnError(
                code="llm_misconfigured",
                message=ERROR_MESSAGES["llm_misconfigured"],
                turn_id=turn_id,
            )
        except LlmUnavailable:
            return TurnError(
                code="llm_unavailable",
                message=ERROR_MESSAGES["llm_unavailable"],
                turn_id=turn_id,
            )
        except Exception:
            # Unexpected classify/LLM failures — not snapshot errors.
            return TurnError(
                code="llm_unavailable",
                message=ERROR_MESSAGES["llm_unavailable"],
                turn_id=turn_id,
            )
        # Skeleton: no domain handoff targets — always CTA.
        _ = result.handoff
        used_backup = result.used_backup

    backup_notice = BACKUP_NOTICE if used_backup else None

    try:
        await write_turn_snapshot(
            last_user_text=stripped,
            database_url=database_url,
        )
    except Exception:
        return TurnError(
            code="checkpointer_write_failed",
            message=ERROR_MESSAGES["checkpointer_write_failed"],
            turn_id=turn_id,
        )

    return TurnSuccess(
        message=CTA_MESSAGE,
        ctas=CTAS,
        clarify=None,
        backup_notice=backup_notice,
        turn_id=turn_id,
        last_user_text=stripped,
    )
