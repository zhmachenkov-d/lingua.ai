"""Thin Router turn: classify→handoff; patch merge; sole ``aput`` (AD-3, AD-6)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from langgraph.checkpoint.base.id import uuid6
from openai import AsyncOpenAI
from psycopg import AsyncConnection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.checkpointer import open_checkpointer
from app.db.config import get_database_url, to_sqlalchemy_url
from app.db.constants import MVP_LEARNER_ID
from app.llm.adapter import (
    BACKUP_NOTICE,
    LlmMisconfigured,
    LlmUnavailable,
    classify_turn,
)
from app.mixins.context_generator import LexiconUnavailable
from app.review import handle_review_stub
from app.router.session_mirror import upsert_session_mirror
from app.schemas.ws import ErrorCode
from app.tutor import handle_tutor
from app.tutor.copy import SESSION_PERSIST_FAIL
from app.tutor.handoff import UNSET
from app.vocabulary import handle_vocabulary_stub

logger = logging.getLogger(__name__)

# EXPERIENCE RU — blank / unknown; low/tie reuse calm CTA prompt (no extra key).
BLANK_INPUT: Final = "Напиши сообщение или выбери агента."
UNKNOWN_INTENT: Final = "Не поняла запрос. Выбери агента."
CTA_MESSAGE: Final = (
    "Выберите, чем заняться: Tutor (урок), Vocabulary (слова) или Review (повторение)."
)

# Three-agent Router row (blank / unknown / low / tie / empty-rag / no-ready).
AGENT_CTAS: Final = ("tutor", "vocabulary", "review")
# Locked set for api↔web contract (includes gate-only ``cefr`` + unit-change).
KNOWN_CTA_IDS: Final = (
    "tutor",
    "vocabulary",
    "review",
    "cefr",
    "confirm_unit",
    "decline_unit",
)
# Backward-compatible alias used by existing tests / contract readers.
CTAS: Final = AGENT_CTAS

# Other-agent CTA / intent tokens — leave Tutor session for those paths.
_OTHER_AGENT_TOKENS: Final = frozenset(
    {"vocabulary", "vocab_lookup", "review", "review_daily"}
)

ERROR_MESSAGES: Final[dict[ErrorCode, str]] = {
    "llm_misconfigured": (
        "Языковая модель не настроена. Проверьте ключ DEEPSEEK_API_KEY."
    ),
    # EXPERIENCE ``llm-down`` copy; wire code stays llm_unavailable.
    "llm_unavailable": "Сервис временно недоступен. Попробуй позже.",
    "invalid_turn_request": "Некорректный запрос хода.",
    "checkpointer_write_failed": "Не удалось сохранить состояние сессии.",
    "ws_already_open": (
        "Чат уже открыт в другой вкладке. Закройте его и попробуйте снова."
    ),
    # EXPERIENCE ``dict-fail`` — required lexicon fetch (not silent CG skip).
    "lexicon_unavailable": "Словарь временно недоступен. Попробуй позже.",
}

THREAD_ID: Final = str(MVP_LEARNER_ID)
CHECKPOINTER_WRITE_TIMEOUT_SECONDS: Final = 30.0
SNAPSHOT_WRITE_LOCK_KEY: Final = 7_265_300_117_002

_BASE_CHANNELS: Final = ("last_user_text", "active_agent", "turn_at")
_BASE_CHANNEL_KEYS: Final = frozenset(_BASE_CHANNELS)


async def _after_snapshot_aget() -> None:
    """Awaitable seam after ``aget`` (tests may delay here to force a race)."""
    return None


@dataclass(frozen=True, slots=True)
class TurnSuccess:
    message: str
    ctas: tuple[str, ...]
    clarify: None
    backup_notice: str | None
    turn_id: str | None
    last_user_text: str
    emit_token_delta: bool = False


@dataclass(frozen=True, slots=True)
class TurnError:
    code: ErrorCode
    message: str
    turn_id: str | None


def _merge_channel_values(
    *,
    prior_values: Mapping[str, Any] | None,
    last_user_text: str,
    turn_at: str,
    active_agent: str | None,
    session_patch: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep prior namespaced keys; overlay base fields + current session_patch."""
    merged: dict[str, Any] = {}
    if prior_values:
        for key, value in prior_values.items():
            if key not in _BASE_CHANNEL_KEYS:
                merged[key] = value
    merged["last_user_text"] = last_user_text
    merged["active_agent"] = active_agent
    merged["turn_at"] = turn_at
    # Replace per top-level domain key (patch wins; absent keys stay from prior).
    for key, value in session_patch.items():
        merged[key] = value
    return merged


def _checkpoint_for_snapshot(
    *,
    channel_values: dict[str, Any],
    turn_at: str,
    channel_versions: dict[str, str],
) -> dict[str, Any]:
    return {
        "v": 4,
        # uuid6 is time-ordered; aget tips via ORDER BY checkpoint_id DESC.
        "id": str(uuid6()),
        "ts": turn_at,
        "channel_values": channel_values,
        "channel_versions": channel_versions,
        "versions_seen": {},
        "updated_channels": list(channel_values),
    }


def _next_channel_versions(
    saver: Any,
    prior: Mapping[str, Any] | None,
    channels: tuple[str, ...],
) -> dict[str, str]:
    """Advance versions via saver.get_next_version (Postgres: zero-padded str)."""
    raw = prior.get("channel_versions") if prior else None
    prior_versions = raw if isinstance(raw, dict) else {}
    versions: dict[str, str] = {}
    for key in channels:
        current = prior_versions.get(key)
        # Accept str/int/None; legacy Router used plain "1".
        if type(current) is bool or (
            current is not None and not isinstance(current, (str, int))
        ):
            current = None
        try:
            next_version = saver.get_next_version(current, None)
        except (TypeError, ValueError, NotImplementedError):
            next_version = saver.get_next_version(None, None)
        assert isinstance(next_version, str)
        versions[key] = next_version
    return versions


@asynccontextmanager
async def _snapshot_write_lock(
    database_url: str | None = None,
) -> AsyncIterator[None]:
    """Hold a Postgres advisory lock for the aget→aput critical section."""
    url = database_url if database_url is not None else get_database_url()
    conn = await AsyncConnection.connect(
        url,
        autocommit=True,
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    try:
        await conn.execute("SELECT pg_advisory_lock(%s)", (SNAPSHOT_WRITE_LOCK_KEY,))
        try:
            yield
        finally:
            await conn.execute(
                "SELECT pg_advisory_unlock(%s)", (SNAPSHOT_WRITE_LOCK_KEY,)
            )
    finally:
        await conn.close()


async def write_turn_snapshot(
    *,
    last_user_text: str,
    active_agent: str | None = None,
    session_patch: Mapping[str, Any] | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Persist Router STM snapshot. Sole ``aput`` path in the app (AD-3)."""
    turn_at = datetime.now(UTC).isoformat()
    patch = dict(session_patch) if session_patch else {}
    config: dict[str, Any] = {
        "configurable": {"thread_id": THREAD_ID, "checkpoint_ns": ""}
    }

    async def _persist() -> dict[str, Any]:
        async with _snapshot_write_lock(database_url):
            async with open_checkpointer(database_url) as saver:
                prior = await saver.aget(config)  # type: ignore[arg-type]
                await _after_snapshot_aget()
                prior_values = None
                if prior is not None:
                    raw_values = prior.get("channel_values")
                    if isinstance(raw_values, dict):
                        prior_values = raw_values
                channel_values = _merge_channel_values(
                    prior_values=prior_values,
                    last_user_text=last_user_text,
                    turn_at=turn_at,
                    active_agent=active_agent,
                    session_patch=patch,
                )
                # Advance versions for every key written (base + preserved + patch).
                namespaced = tuple(
                    sorted(k for k in channel_values if k not in _BASE_CHANNEL_KEYS)
                )
                channels = _BASE_CHANNELS + namespaced
                versions = _next_channel_versions(saver, prior, channels)
                checkpoint = _checkpoint_for_snapshot(
                    channel_values=channel_values,
                    turn_at=turn_at,
                    channel_versions=versions,
                )
                write_config = config
                if prior is not None:
                    write_config = {
                        "configurable": {
                            "thread_id": THREAD_ID,
                            "checkpoint_ns": "",
                            "checkpoint_id": prior["id"],
                        }
                    }
                version_map: dict[str, str | int | float] = dict(versions)
                await saver.aput(
                    write_config,  # type: ignore[arg-type]
                    checkpoint,  # type: ignore[arg-type]
                    {"source": "update", "step": 0, "parents": {}},
                    version_map,
                )
                values = checkpoint["channel_values"]
                assert isinstance(values, dict)
                return values

    values = await asyncio.wait_for(
        _persist(),
        timeout=CHECKPOINTER_WRITE_TIMEOUT_SECONDS,
    )

    # Best-effort non-SoT Session mirror; never fail the turn / snapshot.
    try:
        await asyncio.wait_for(
            upsert_session_mirror(database_url=database_url),
            timeout=CHECKPOINTER_WRITE_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception("session mirror upsert failed after successful snapshot")

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


@asynccontextmanager
async def _learner_db_session(
    database_url: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """Ephemeral async session for domain reads (CEFR / Ready corpus)."""
    url = database_url if database_url is not None else get_database_url()
    engine = create_async_engine(to_sqlalchemy_url(url))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


def _prior_tutor_and_agent(
    snap: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if snap is None:
        return None, None
    raw_agent = snap.get("active_agent")
    agent = raw_agent if isinstance(raw_agent, str) else None
    raw_tutor = snap.get("tutor")
    tutor = dict(raw_tutor) if isinstance(raw_tutor, dict) else None
    return tutor, agent


def _is_tutor_session_turn(stripped: str, prior_agent: str | None) -> bool:
    """Active Tutor continues (incl. free text / unit chrome) unless other-agent CTA."""
    if prior_agent != "Tutor":
        return False
    return stripped.casefold() not in _OTHER_AGENT_TOKENS


async def handle_turn(
    text: str,
    *,
    turn_id: str | None = None,
    unit_ref: Any = UNSET,
    database_url: str | None = None,
    http_client: object | None = None,
    llm_client: AsyncOpenAI | None = None,
) -> TurnSuccess | TurnError:
    """Blank → CTA; classify → domain handoff or three CTAs; persist-then-complete."""
    stripped = text.strip()
    used_backup = False
    active_agent: str | None = None
    session_patch: dict[str, Any] = {}
    emit_token_delta = False
    unit_switch_attempt = False
    message: str
    ctas: tuple[str, ...]

    prior_snap: dict[str, Any] | None = None
    try:
        prior_snap = await get_turn_snapshot(database_url=database_url)
    except Exception:
        logger.exception("prior snapshot read failed; continuing without STM")
    prior_tutor, prior_agent = _prior_tutor_and_agent(prior_snap)

    if not stripped and unit_ref is UNSET:
        message = BLANK_INPUT
        ctas = AGENT_CTAS
    else:
        run_tutor = False
        handoff: str | None = None
        band: str | None = None

        if _is_tutor_session_turn(stripped or "tutor_unit", prior_agent) or (
            unit_ref is not UNSET and prior_agent == "Tutor"
        ):
            run_tutor = True
        elif not stripped and unit_ref is not UNSET:
            # Chrome-only turn with empty text while idle — treat as tutor_unit.
            run_tutor = True
            stripped = "tutor_unit"
        else:
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
                return TurnError(
                    code="llm_unavailable",
                    message=ERROR_MESSAGES["llm_unavailable"],
                    turn_id=turn_id,
                )
            used_backup = result.used_backup
            handoff = result.handoff
            band = result.band
            if handoff == "tutor_unit":
                run_tutor = True

        if run_tutor:
            try:
                async with _learner_db_session(database_url) as session:
                    outcome = await handle_tutor(
                        session,
                        text=stripped or "tutor_unit",
                        prior_tutor=prior_tutor,
                        request_unit_ref=unit_ref,
                    )
            except LexiconUnavailable:
                return TurnError(
                    code="lexicon_unavailable",
                    message=ERROR_MESSAGES["lexicon_unavailable"],
                    turn_id=turn_id,
                )
            except Exception:
                # Tutor/DB path — not an LLM outage; reuse honest non-llm-down code.
                logger.exception("tutor handoff failed")
                return TurnError(
                    code="checkpointer_write_failed",
                    message=ERROR_MESSAGES["checkpointer_write_failed"],
                    turn_id=turn_id,
                )
            message = outcome.message
            ctas = outcome.ctas
            session_patch = dict(outcome.session_patch)
            active_agent = outcome.active_agent
            emit_token_delta = outcome.emit_token_delta
            unit_switch_attempt = outcome.unit_switch_attempt
        elif handoff == "vocab_lookup":
            vocab = handle_vocabulary_stub()
            message = vocab.message
            ctas = ()
            session_patch = dict(vocab.session_patch)
            active_agent = vocab.active_agent
        elif handoff == "review_daily":
            review = handle_review_stub()
            message = review.message
            ctas = ()
            session_patch = dict(review.session_patch)
            active_agent = review.active_agent
        elif band == "unknown":
            message = UNKNOWN_INTENT
            ctas = AGENT_CTAS
        else:
            # low / tie — three CTAs; no extra RU key required
            message = CTA_MESSAGE
            ctas = AGENT_CTAS

    backup_notice = BACKUP_NOTICE if used_backup else None

    try:
        await write_turn_snapshot(
            last_user_text=stripped,
            active_agent=active_agent,
            session_patch=session_patch,
            database_url=database_url,
        )
    except Exception:
        if unit_switch_attempt:
            # EXPERIENCE session-persist-fail: keep prior STM; block switch.
            return TurnSuccess(
                message=SESSION_PERSIST_FAIL,
                ctas=AGENT_CTAS,
                clarify=None,
                backup_notice=backup_notice,
                turn_id=turn_id,
                last_user_text=stripped,
                emit_token_delta=False,
            )
        return TurnError(
            code="checkpointer_write_failed",
            message=ERROR_MESSAGES["checkpointer_write_failed"],
            turn_id=turn_id,
        )

    return TurnSuccess(
        message=message,
        ctas=ctas,
        clarify=None,
        backup_notice=backup_notice,
        turn_id=turn_id,
        last_user_text=stripped,
        emit_token_delta=emit_token_delta,
    )
