"""Cursor SDK agent create/resume/stream."""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    AGENT_START_MAX_ATTEMPTS,
    DEFAULT_AGENT_MAX_TOKENS,
    DEFAULT_AGENT_TIMEOUT_S,
    DEFAULT_MODEL_ID,
    SHUTDOWN_ERROR,
    FactoryHalt,
    log,
)
from .report import TokenUsage, format_token_cost

_ANSI = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "white": "\033[97m",
    "cyan": "\033[36m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "red": "\033[31m",
    "blue": "\033[34m",
}

_KIND_LABEL = {
    "assistant": "asst",
    "thinking": "think",
    "tool_running": "tool",
    "tool_completed": "tool",
    "tool_error": "tool",
    "status": "status",
    "task": "task",
}


@dataclass
class AgentRunResult:
    status: str
    usage: TokenUsage | None
    agent_id: str | None
    run_id: str | None
    error: str | None = None


def resolve_agent_model(model: str) -> Any:
    from cursor_sdk import ModelParameterValue, ModelSelection

    # Accept legacy/alias "auto-smart" as the Auto + balanced selection.
    if model in {DEFAULT_MODEL_ID, "auto-smart"}:
        return ModelSelection(
            id="auto",
            params=[ModelParameterValue(id="optimize_for", value="balanced")],
        )
    return model


def _agent_color_enabled() -> bool:
    return sys.stderr.isatty() and not os.environ.get("NO_COLOR")


def _paint(style: str, text: str) -> str:
    if not _agent_color_enabled():
        return text
    code = _ANSI.get(style, "")
    if not code:
        return text
    return f"{code}{text}{_ANSI['reset']}"


def _format_payload(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        return str(value)


def _emit_agent_line(kind: str, text: str) -> None:
    style = {
        "assistant": "white",
        "thinking": "dim",
        "tool_running": "yellow",
        "tool_completed": "green",
        "tool_error": "red",
        "status": "blue",
        "task": "blue",
    }.get(kind, "")
    label = _KIND_LABEL.get(kind, (kind or "?")[:6])
    prefix = _paint("dim", f"agent | {label:<6} |")
    body = _paint(style, text) if style else text
    print(f"{prefix} {body}", file=sys.stderr, flush=True)


def _emit_agent_block(kind: str, text: str) -> None:
    text = text.replace("\r\n", "\n").replace("\r", "\n").rstrip()
    if not text:
        return
    for line in text.split("\n"):
        _emit_agent_line(kind, line)


def _assistant_text(message: Any) -> str:
    content = getattr(getattr(message, "message", None), "content", None) or ()
    parts: list[str] = []
    for block in content:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
            if text:
                parts.append(text)
    return "".join(parts)


def _emit_agent_message(message: Any) -> None:
    msg_type = getattr(message, "type", None)
    if msg_type == "assistant":
        text = _assistant_text(message)
        if text:
            _emit_agent_block("assistant", text)
        return
    if msg_type == "thinking":
        text = getattr(message, "text", "") or ""
        if text:
            _emit_agent_block("thinking", text)
        return
    if msg_type == "tool_call":
        name = getattr(message, "name", "") or "tool"
        status = str(getattr(message, "status", "") or "")
        kind = {
            "running": "tool_running",
            "completed": "tool_completed",
            "error": "tool_error",
        }.get(status, "tool_running")
        header = name
        if status:
            header = f"{header} [{status}]"
        _emit_agent_line(kind, header)
        args_text = _format_payload(getattr(message, "args", None))
        if args_text:
            _emit_agent_block(kind, args_text)
        if status in {"completed", "error"}:
            result_text = _format_payload(getattr(message, "result", None))
            if result_text:
                _emit_agent_block(kind, f"→ {result_text}")
        return
    if msg_type == "status":
        status = getattr(message, "status", "") or ""
        detail = getattr(message, "message", "") or ""
        line = f"{status}"
        if detail:
            line = f"{line} {detail}"
        _emit_agent_line("status", line.strip())
        return
    if msg_type == "task":
        status = getattr(message, "status", "") or ""
        text = getattr(message, "text", "") or ""
        line = f"{status}"
        if text:
            line = f"{line} {text}"
        _emit_agent_line("task", line.strip())


class _AgentTextCoalescer:
    """Buffer consecutive thinking/assistant text deltas into readable blocks."""

    def __init__(self) -> None:
        self._kind: str | None = None
        self._parts: list[str] = []

    def flush(self) -> None:
        if not self._kind or not self._parts:
            self._kind = None
            self._parts = []
            return
        text = "".join(self._parts)
        kind = self._kind
        self._kind = None
        self._parts = []
        if kind == "assistant":
            _emit_agent_block("assistant", text)
        elif kind == "thinking":
            _emit_agent_block("thinking", text)

    def feed(self, message: Any) -> None:
        msg_type = getattr(message, "type", None)
        if msg_type == "assistant":
            text = _assistant_text(message)
            if not text:
                return
            if self._kind not in (None, "assistant"):
                self.flush()
            self._kind = "assistant"
            self._parts.append(text)
            return
        if msg_type == "thinking":
            text = getattr(message, "text", "") or ""
            if not text:
                return
            if self._kind not in (None, "thinking"):
                self.flush()
            self._kind = "thinking"
            self._parts.append(text)
            return
        self.flush()
        _emit_agent_message(message)


def _soft_close_agent(agent: Any, err_type: type[BaseException]) -> None:
    if agent is None:
        return
    try:
        agent.close()
    except err_type as close_err:
        log.warning(
            "agent close failed: %s",
            getattr(close_err, "message", None) or close_err,
        )
    except Exception as close_err:  # noqa: BLE001 — never mask primary halt
        log.warning("agent close failed: %s", close_err)


_active_agent_run: Any | None = None


def _set_active_agent_run(run: Any | None) -> None:
    global _active_agent_run
    _active_agent_run = run


def _soft_cancel_run(run: Any) -> None:
    if run is None:
        return
    try:
        run.cancel()
    except Exception as err:  # noqa: BLE001 — best-effort cancel
        log.warning("agent cancel failed: %s", getattr(err, "message", None) or err)


def cancel_active_agent() -> None:
    """Best-effort cancel of the in-flight Cursor SDK run (signal / --stop path)."""
    _soft_cancel_run(_active_agent_run)


def _retry_delay(err: Any, attempt: int) -> float:
    raw = getattr(err, "retry_after", None)
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    return float(min(2 ** (attempt - 1), 2))


def _token_usage_from_raw(raw_usage: Any) -> TokenUsage | None:
    if raw_usage is None:
        return None
    return TokenUsage(
        input_tokens=int(getattr(raw_usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(raw_usage, "output_tokens", 0) or 0),
        total_tokens=int(getattr(raw_usage, "total_tokens", 0) or 0),
        cache_read_tokens=int(getattr(raw_usage, "cache_read_tokens", 0) or 0),
        cache_write_tokens=int(getattr(raw_usage, "cache_write_tokens", 0) or 0),
    )


@dataclass
class _StreamLimitsOutcome:
    """Result of streaming one agent run under timeout/token caps."""

    status: str
    usage: TokenUsage | None = None
    error: str | None = None


def _stream_run_with_limits(
    run: Any,
    *,
    timeout_s: int,
    max_tokens: int,
) -> _StreamLimitsOutcome:
    """Drain ``run.messages()`` with wall-clock + token caps, then ``wait()``.

    Timeout uses a producer thread so a blocked ``next(message)`` still expires.
    Mid-stream ``usage`` messages enforce the token ceiling early via ``cancel``.
    """
    deadline = time.monotonic() + timeout_s if timeout_s > 0 else None
    latest_usage: TokenUsage | None = None
    msg_q: queue.Queue[tuple[str, Any]] = queue.Queue()

    def _producer() -> None:
        try:
            for message in run.messages():
                msg_q.put(("msg", message))
            msg_q.put(("done", None))
        except Exception as err:  # noqa: BLE001 — forwarded to consumer
            msg_q.put(("err", err))

    thread = threading.Thread(target=_producer, name="bmad-agent-stream", daemon=True)
    coalescer = _AgentTextCoalescer()
    _emit_agent_line("status", "----- begin -----")
    thread.start()

    def _timeout_outcome() -> _StreamLimitsOutcome:
        detail = f"agent call timed out after {timeout_s}s"
        log.error("%s", detail)
        _soft_cancel_run(run)
        coalescer.flush()
        _emit_agent_line(
            "status",
            f"----- end status=cancelled {format_token_cost(latest_usage)} -----",
        )
        return _StreamLimitsOutcome(
            status="cancelled", usage=latest_usage, error=detail
        )

    def _token_limit_outcome(usage: TokenUsage) -> _StreamLimitsOutcome:
        detail = (
            f"agent call exceeded token limit ({usage.total_tokens} > {max_tokens})"
        )
        log.error("%s", detail)
        _soft_cancel_run(run)
        coalescer.flush()
        _emit_agent_line(
            "status",
            f"----- end status=error {format_token_cost(usage)} -----",
        )
        return _StreamLimitsOutcome(status="error", usage=usage, error=detail)

    try:
        while True:
            get_timeout: float | None = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return _timeout_outcome()
                get_timeout = remaining
            try:
                kind, payload = msg_q.get(timeout=get_timeout)
            except queue.Empty:
                return _timeout_outcome()

            if kind == "err":
                raise payload
            if kind == "done":
                break

            message = payload
            if getattr(message, "type", None) == "usage":
                usage = _token_usage_from_raw(getattr(message, "usage", None))
                if usage is not None:
                    latest_usage = usage
                    _emit_agent_line("status", f"usage {format_token_cost(usage)}")
                    if max_tokens > 0 and usage.total_tokens > max_tokens:
                        return _token_limit_outcome(usage)
                continue
            coalescer.feed(message)
    finally:
        coalescer.flush()
        thread.join(timeout=5.0)

    phase_wait_result = run.wait()
    usage = (
        _token_usage_from_raw(
            getattr(phase_wait_result, "usage", None) or getattr(run, "usage", None)
        )
        or latest_usage
    )
    if max_tokens > 0 and usage is not None and usage.total_tokens > max_tokens:
        return _token_limit_outcome(usage)

    status = getattr(phase_wait_result, "status", None) or "unknown"
    _emit_agent_line(
        "status",
        f"----- end status={status} {format_token_cost(usage)} -----",
    )
    err = None
    if status == "error":
        run_id = getattr(run, "run_id", None) or getattr(run, "id", None)
        err = f"agent run failed: {run_id}"
        log.error("agent error run_id=%s %s", run_id, format_token_cost(usage))
    return _StreamLimitsOutcome(status=str(status), usage=usage, error=err)


def agent_call_limits(limits: Any | None = None) -> dict[str, int]:
    """Kwargs for ``run_cursor_agent`` timeout/token caps from ``LimitsPolicy``."""
    if limits is None:
        return {
            "timeout_s": DEFAULT_AGENT_TIMEOUT_S,
            "max_tokens": DEFAULT_AGENT_MAX_TOKENS,
        }
    return {
        "timeout_s": int(getattr(limits, "agent_timeout_s", DEFAULT_AGENT_TIMEOUT_S)),
        "max_tokens": int(
            getattr(limits, "agent_max_tokens", DEFAULT_AGENT_MAX_TOKENS)
        ),
    }


def run_cursor_agent(
    *,
    project_root: Path,
    model: str,
    prompt: str,
    dry_run: bool,
    resume_agent_id: str | None = None,
    cwd: Path | None = None,
    timeout_s: int = DEFAULT_AGENT_TIMEOUT_S,
    max_tokens: int = DEFAULT_AGENT_MAX_TOKENS,
) -> AgentRunResult:
    agent_cwd = cwd or project_root
    if dry_run:
        log.info("[dry-run] agent cwd=%s prompt:\n%s", agent_cwd, prompt)
        return AgentRunResult(status="dry_run", usage=None, agent_id=None, run_id=None)

    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise FactoryHalt(SHUTDOWN_ERROR, "CURSOR_API_KEY is not set")

    from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions

    resolved_model = resolve_agent_model(model)
    local_opts = LocalAgentOptions(cwd=str(agent_cwd), setting_sources=["project"])
    agent_options = AgentOptions(
        model=resolved_model,
        api_key=api_key,
        local=local_opts,
    )
    log.info(
        "agent start model=%s cwd=%s resume_agent_id=%s timeout_s=%s max_tokens=%s",
        model,
        agent_cwd,
        resume_agent_id or "(none)",
        timeout_s,
        max_tokens,
    )
    use_resume = bool(resume_agent_id)

    for attempt in range(1, AGENT_START_MAX_ATTEMPTS + 1):
        agent: Any = None
        phase = "create"
        try:
            if use_resume and resume_agent_id:
                phase = "resume"
                try:
                    agent = Agent.resume(resume_agent_id, agent_options)
                    log.info("agent resume agent_id=%s", resume_agent_id)
                except Exception as resume_err:  # noqa: BLE001 — fall back to create
                    detail = getattr(resume_err, "message", None) or resume_err
                    log.warning(
                        "agent resume failed; falling back to create detail=%s",
                        detail,
                    )
                    use_resume = False
                    agent = None

            if agent is None:
                phase = "create"
                agent = Agent.create(
                    model=resolved_model,
                    api_key=api_key,
                    local=local_opts,
                )
                log.info(
                    "agent created agent_id=%s",
                    getattr(agent, "agent_id", None) or getattr(agent, "agentId", None),
                )

            agent_id = (
                getattr(agent, "agent_id", None)
                or getattr(agent, "agentId", None)
                or resume_agent_id
            )

            phase = "send"
            run = agent.send(prompt)
            _set_active_agent_run(run)
            run_id = getattr(run, "run_id", None) or getattr(run, "id", None)
            log.info("agent sent agent_id=%s run_id=%s", agent_id, run_id)

            phase = "stream"
            try:
                outcome = _stream_run_with_limits(
                    run, timeout_s=timeout_s, max_tokens=max_tokens
                )
            finally:
                _set_active_agent_run(None)
            if outcome.error is None:
                log.info(
                    "agent finished status=%s agent_id=%s run_id=%s %s",
                    outcome.status,
                    agent_id,
                    run_id,
                    format_token_cost(outcome.usage),
                )
            return AgentRunResult(
                status=outcome.status,
                usage=outcome.usage,
                agent_id=str(agent_id) if agent_id else None,
                run_id=str(run_id) if run_id else None,
                error=outcome.error,
            )
        except KeyboardInterrupt:
            _soft_cancel_run(_active_agent_run)
            _set_active_agent_run(None)
            _soft_close_agent(agent, CursorAgentError)
            agent = None
            raise
        except CursorAgentError as err:
            _soft_close_agent(agent, CursorAgentError)
            agent = None
            if (
                phase in {"create", "resume", "send"}
                and err.is_retryable
                and attempt < AGENT_START_MAX_ATTEMPTS
            ):
                delay = _retry_delay(err, attempt)
                log.warning(
                    "agent retry attempt=%s/%s phase=%s after=%ss detail=%s",
                    attempt + 1,
                    AGENT_START_MAX_ATTEMPTS,
                    phase,
                    delay,
                    err.message,
                )
                time.sleep(delay)
                continue
            raise FactoryHalt(
                SHUTDOWN_ERROR,
                f"Cursor agent {phase} failed: {err.message} "
                f"(retryable={err.is_retryable})",
            ) from err
        finally:
            _set_active_agent_run(None)
            _soft_close_agent(agent, CursorAgentError)

    raise FactoryHalt(SHUTDOWN_ERROR, "Cursor agent create/send retries exhausted")


def usage_dict(usage: TokenUsage | None) -> dict[str, int] | None:
    if usage is None:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
    }
