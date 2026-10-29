"""Durable run state and journal under ``.bmad-factory/runs/<id>/``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .constants import (
    POLICY_DIRNAME,
    RUNS_DIRNAME,
    SHUTDOWN_ERROR,
    FactoryHalt,
    log,
)

ENGINE_NAME = "bmad-factory"
ENGINE_VERSION = 1

PAUSE_PLAN_CHECKPOINT = "plan_checkpoint"
PAUSE_DONE_CHECKPOINT = "done_checkpoint"
PAUSE_BLOCKED = "blocked"
PAUSE_ERROR = "error"
PAUSE_DIRTY_TREE = "dirty_tree"
PAUSE_SIGNAL = "signal"
PAUSE_STOPPED = "stopped"
PAUSE_PICK_PLAN_CHECKPOINT = "plan-checkpoint"
PAUSE_PICK_EPIC_BOUNDARY = "epic-boundary"
PAUSE_PICK_ESCALATION = "escalation"
PAUSE_PICK_TICKET_HITL = "ticket-hitl"
PAUSE_PICK_TICKET_REFINE = "ticket-refine"
PAUSE_PICK_TICKET_TREE = "ticket-tree"


@dataclass
class UnitAttemptState:
    ref: str
    kind: str = "ticket"  # ticket | bundle
    phase: str = "pending"
    branch: str | None = None
    baseline_rev: str | None = None
    agent_id: str | None = None
    outcome: str | None = None
    reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunState:
    run_id: str
    engine: str = ENGINE_NAME
    engine_version: int = ENGINE_VERSION
    project_root: str = ""
    status: str = "running"  # running | paused | completed | aborted
    pause_reason: str | None = None
    pause_detail: str | None = None
    pause_ticket: str | None = None
    mode: str = "ticket"  # ticket | epic | bugs | spikes | deferred (| backlog legacy)
    ticket: str | None = None
    epic: str | None = None
    model: str = "auto"
    dry_run: bool = False
    yes: bool = False
    no_push: bool = False
    target_branch: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    current_unit: UnitAttemptState | None = None
    completed_refs: list[str] = field(default_factory=list)
    deferred_refs: list[str] = field(default_factory=list)
    blocked_refs: list[dict[str, str]] = field(default_factory=list)
    seen_refs: list[str] = field(default_factory=list)
    awaiting_confirm: list[str] = field(default_factory=list)
    source: str = "tickets"
    task_phases: dict[str, str] = field(default_factory=dict)
    ticket_story_approvals: list[str] = field(default_factory=list)
    ticket_epic_closures: dict[str, str] = field(default_factory=dict)
    ticket_epic_closure_acked: list[str] = field(default_factory=list)
    committed_epics: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        current = data.get("current_unit")
        unit = None
        if isinstance(current, dict):
            unit = UnitAttemptState(
                ref=str(current.get("ref") or ""),
                kind=str(current.get("kind") or "ticket"),
                phase=str(current.get("phase") or "pending"),
                branch=current.get("branch"),
                baseline_rev=current.get("baseline_rev"),
                agent_id=current.get("agent_id"),
                outcome=current.get("outcome"),
                reason=current.get("reason"),
                extra=dict(current.get("extra") or {}),
            )
        return cls(
            run_id=str(data.get("run_id") or ""),
            engine=str(data.get("engine") or ENGINE_NAME),
            engine_version=int(data.get("engine_version") or ENGINE_VERSION),
            project_root=str(data.get("project_root") or ""),
            status=str(data.get("status") or "running"),
            pause_reason=data.get("pause_reason"),
            pause_detail=data.get("pause_detail"),
            pause_ticket=data.get("pause_ticket"),
            mode=str(data.get("mode") or "ticket"),
            ticket=data.get("ticket"),
            epic=data.get("epic"),
            model=str(data.get("model") or "auto"),
            dry_run=bool(data.get("dry_run")),
            yes=bool(data.get("yes")),
            no_push=bool(data.get("no_push")),
            target_branch=data.get("target_branch"),
            created_at=float(data.get("created_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
            current_unit=unit,
            completed_refs=list(data.get("completed_refs") or []),
            deferred_refs=list(data.get("deferred_refs") or []),
            blocked_refs=list(data.get("blocked_refs") or []),
            seen_refs=list(data.get("seen_refs") or []),
            awaiting_confirm=list(data.get("awaiting_confirm") or []),
            source=str(data.get("source") or "tickets"),
            task_phases={
                str(k): str(v) for k, v in dict(data.get("task_phases") or {}).items()
            },
            ticket_story_approvals=list(data.get("ticket_story_approvals") or []),
            ticket_epic_closures={
                str(k): str(v)
                for k, v in dict(data.get("ticket_epic_closures") or {}).items()
            },
            ticket_epic_closure_acked=list(data.get("ticket_epic_closure_acked") or []),
            committed_epics=list(data.get("committed_epics") or []),
            report=dict(data.get("report") or {}),
            meta=dict(data.get("meta") or {}),
        )


def runs_root(project_root: Path) -> Path:
    return project_root / POLICY_DIRNAME / RUNS_DIRNAME


def run_dir(project_root: Path, run_id: str) -> Path:
    return runs_root(project_root) / run_id


def state_path(project_root: Path, run_id: str) -> Path:
    return run_dir(project_root, run_id) / "state.json"


def journal_path(project_root: Path, run_id: str) -> Path:
    return run_dir(project_root, run_id) / "journal.jsonl"


def new_run_id() -> str:
    stamp = time.strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def create_run(
    project_root: Path,
    *,
    mode: str,
    model: str,
    dry_run: bool = False,
    yes: bool = False,
    no_push: bool = False,
    ticket: str | None = None,
    epic: str | None = None,
    target_branch: str | None = None,
    meta: dict[str, Any] | None = None,
) -> RunState:
    run_id = new_run_id()
    now = time.time()
    state = RunState(
        run_id=run_id,
        project_root=str(project_root.resolve()),
        mode=mode,
        model=model,
        dry_run=dry_run,
        yes=yes,
        no_push=no_push,
        ticket=ticket,
        epic=epic,
        target_branch=target_branch,
        created_at=now,
        updated_at=now,
        meta=dict(meta or {}),
    )
    save_run(project_root, state)
    append_journal(
        project_root,
        run_id,
        {"event": "created", "mode": mode, "model": model},
    )
    return state


def save_run(project_root: Path, state: RunState) -> None:
    state.touch()
    path = state_path(project_root, state.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def load_run(project_root: Path, run_id: str) -> RunState:
    path = state_path(project_root, run_id)
    if not path.is_file():
        raise FactoryHalt(SHUTDOWN_ERROR, f"run not found: {run_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise FactoryHalt(
            SHUTDOWN_ERROR, f"corrupt state.json for {run_id}: {err}"
        ) from err
    if not isinstance(data, dict):
        raise FactoryHalt(SHUTDOWN_ERROR, f"invalid state.json for {run_id}")
    state = RunState.from_dict(data)
    if state.engine != ENGINE_NAME:
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            f"refuse load: foreign engine {state.engine!r} (expected {ENGINE_NAME!r})",
        )
    return state


def append_journal(project_root: Path, run_id: str, event: dict[str, Any]) -> None:
    path = journal_path(project_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": time.time(), **event}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def pause_run(
    project_root: Path,
    state: RunState,
    *,
    reason: str,
    detail: str | None = None,
    ticket: str | None = None,
) -> None:
    state.status = "paused"
    state.pause_reason = reason
    state.pause_detail = detail
    state.pause_ticket = ticket
    save_run(project_root, state)
    append_journal(
        project_root,
        state.run_id,
        {
            "event": "paused",
            "reason": reason,
            "detail": detail,
            "ticket": ticket,
        },
    )
    log.info("run paused id=%s reason=%s detail=%s", state.run_id, reason, detail)


def clear_pause(project_root: Path, state: RunState) -> RunState:
    """Clear pause flags so the loop can continue on re-invoke."""
    state.status = "running"
    state.pause_reason = None
    state.pause_detail = None
    save_run(project_root, state)
    append_journal(project_root, state.run_id, {"event": "reinvoked"})
    return state


def list_runs(project_root: Path) -> list[RunState]:
    root = runs_root(project_root)
    if not root.is_dir():
        return []
    out: list[RunState] = []
    for child in sorted(root.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        sp = child / "state.json"
        if not sp.is_file():
            continue
        try:
            out.append(load_run(project_root, child.name))
        except FactoryHalt:
            continue
    return out


def classify_run(
    project_root: Path,
    state: RunState,
    *,
    now: float | None = None,
    stale_after_s: float = 3600.0,
) -> str:
    """Classify a run as completed|aborted|paused|running|stale.

    Canonical stale = ``status=running`` without a live run lock holder.
    ``stale_after_s`` / age are secondary signals for status payloads only.
    """
    del now, stale_after_s  # age is reported by callers; not required for the label
    status = state.status
    if status in {"completed", "aborted", "paused"}:
        return status
    if status == "running":
        from .run_lock import is_run_alive  # local: run_lock may import constants only

        if is_run_alive(project_root, state.run_id):
            return "running"
        return "stale"
    return status or "unknown"


def run_age_s(state: RunState, *, now: float | None = None) -> float:
    stamp = state.updated_at or state.created_at or 0.0
    return max(0.0, (now if now is not None else time.time()) - stamp)


def is_resumable_state(project_root: Path, state: RunState) -> bool:
    """Paused runs and orphan (stale) running runs may be resumed."""
    classified = classify_run(project_root, state)
    return classified in {"paused", "stale"}


def find_resumable_run(
    project_root: Path,
    *,
    mode: str,
    ticket: str | None = None,
    epic: str | None = None,
) -> RunState | None:
    """Latest paused or stale run matching mode + scope (for halt+re-invoke)."""
    mode_aliases = {mode}
    if mode == "bugs":
        mode_aliases.add("backlog")  # legacy mode name
    for state in list_runs(project_root):
        if not is_resumable_state(project_root, state):
            continue
        if state.mode not in mode_aliases:
            continue
        if mode == "ticket" and (state.ticket or "") != (ticket or ""):
            continue
        if mode == "epic" and (state.epic or "") != (epic or ""):
            continue
        return state
    return None


def format_run_brief(
    state: RunState,
    *,
    classified: str | None = None,
    alive: bool | None = None,
    pid: int | None = None,
) -> str:
    label = classified or state.status
    pause = f" pause={state.pause_reason}" if state.pause_reason else ""
    ticket = f" ticket={state.pause_ticket}" if state.pause_ticket else ""
    done = f" done={','.join(state.completed_refs)}" if state.completed_refs else ""
    live = ""
    if label == "running" and pid is not None or alive is True and pid is not None:
        live = f" pid={pid}"
    return f"{state.run_id}  {label}  mode={state.mode}{live}{pause}{ticket}{done}"
