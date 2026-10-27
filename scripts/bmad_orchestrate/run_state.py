"""Durable run state and journal under ``.bmad-orchestrate/runs/<id>/``."""

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
    OrchestratorHalt,
    log,
)

ENGINE_NAME = "bmad-orchestrate"
ENGINE_VERSION = 1

PAUSE_PLAN_CHECKPOINT = "plan_checkpoint"
PAUSE_DONE_CHECKPOINT = "done_checkpoint"
PAUSE_BLOCKED = "blocked"
PAUSE_UNREFINED_BUGS = "unrefined_bugs"
PAUSE_EPIC_BOUNDARY = "epic_boundary"
PAUSE_OPERATOR = "operator_confirm"
PAUSE_ERROR = "error"
PAUSE_PLATEAU = "plateau_deferred"


@dataclass
class UnitAttemptState:
    ref: str
    kind: str = "ticket"  # ticket | bundle | retrospective
    phase: str = "pending"
    dev_attempts: int = 0
    review_cycles: int = 0
    followup_reviews: int = 0
    worktree_path: str | None = None
    branch: str | None = None
    baseline_rev: str | None = None
    agent_id: str | None = None
    last_verify: str | None = None
    plateau_deferred: bool = False
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
    mode: str = "all"  # ticket | epic | all | sweep
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
    retros_done: list[str] = field(default_factory=list)
    seen_refs: list[str] = field(default_factory=list)
    awaiting_confirm: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        current = data.get("current_unit")
        unit = None
        if isinstance(current, dict):
            unit = UnitAttemptState(
                ref=str(current.get("ref") or ""),
                kind=str(current.get("kind") or "ticket"),
                phase=str(current.get("phase") or "pending"),
                dev_attempts=int(current.get("dev_attempts") or 0),
                review_cycles=int(current.get("review_cycles") or 0),
                followup_reviews=int(current.get("followup_reviews") or 0),
                worktree_path=current.get("worktree_path"),
                branch=current.get("branch"),
                baseline_rev=current.get("baseline_rev"),
                agent_id=current.get("agent_id"),
                last_verify=current.get("last_verify"),
                plateau_deferred=bool(current.get("plateau_deferred")),
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
            mode=str(data.get("mode") or "all"),
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
            retros_done=list(data.get("retros_done") or []),
            seen_refs=list(data.get("seen_refs") or []),
            awaiting_confirm=list(data.get("awaiting_confirm") or []),
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
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"run not found: {run_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"corrupt state.json for {run_id}: {err}"
        ) from err
    if not isinstance(data, dict):
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"invalid state.json for {run_id}")
    state = RunState.from_dict(data)
    if state.engine != ENGINE_NAME:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            f"refuse resume: foreign engine {state.engine!r} (expected {ENGINE_NAME!r})",
        )
    expected_root = str(project_root.resolve())
    if state.project_root and Path(state.project_root).resolve() != Path(
        expected_root
    ).resolve():
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            f"refuse resume: run project_root {state.project_root!r} != {expected_root!r}",
        )
    return state


def append_journal(
    project_root: Path, run_id: str, event: dict[str, Any]
) -> None:
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


def resume_armed(project_root: Path, state: RunState) -> RunState:
    """Clear pause flags so the loop can continue."""
    if state.status not in {"paused", "running"}:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            f"cannot resume run in status={state.status}",
        )
    state.status = "running"
    state.pause_reason = None
    state.pause_detail = None
    # Keep pause_ticket until unit completes so resolve/confirm know the target.
    save_run(project_root, state)
    append_journal(project_root, state.run_id, {"event": "resumed"})
    return state


def resolve_blocked(
    project_root: Path, state: RunState, *, ticket: str | None = None
) -> RunState:
    """Re-arm a blocked/plateau unit for another attempt."""
    target = ticket or state.pause_ticket
    if state.pause_reason and state.pause_reason not in {
        PAUSE_BLOCKED,
        PAUSE_PLATEAU,
        PAUSE_ERROR,
    }:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            f"resolve only applies to blocked/plateau/error pauses "
            f"(got {state.pause_reason})",
        )
    if target and state.current_unit and state.current_unit.ref != target:
        state.current_unit = UnitAttemptState(ref=target, phase="pending")
    elif state.current_unit:
        state.current_unit.phase = "pending"
        state.current_unit.plateau_deferred = False
        state.current_unit.outcome = None
        state.current_unit.reason = None
        state.current_unit.dev_attempts = 0
        state.current_unit.review_cycles = 0
    elif target:
        state.current_unit = UnitAttemptState(ref=target, phase="pending")
    if target:
        state.blocked_refs = [b for b in state.blocked_refs if b.get("ref") != target]
        state.deferred_refs = [r for r in state.deferred_refs if r != target]
    state.pause_ticket = target
    return resume_armed(project_root, state)


def confirm_parked(
    project_root: Path, state: RunState, *, ticket: str | None = None
) -> RunState:
    """Operator confirms a parked checkpoint / epic-boundary / confirm pause."""
    allowed = {
        PAUSE_PLAN_CHECKPOINT,
        PAUSE_DONE_CHECKPOINT,
        PAUSE_EPIC_BOUNDARY,
        PAUSE_OPERATOR,
        PAUSE_UNREFINED_BUGS,
    }
    if state.pause_reason and state.pause_reason not in allowed:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            f"confirm only applies to checkpoint/operator pauses "
            f"(got {state.pause_reason})",
        )
    target = ticket or state.pause_ticket
    if target and target in state.awaiting_confirm:
        state.awaiting_confirm = [r for r in state.awaiting_confirm if r != target]
    if state.current_unit and (
        target is None or state.current_unit.ref == target
    ):
        # After plan checkpoint confirm → continue build; after done → mark/landing.
        if state.pause_reason == PAUSE_PLAN_CHECKPOINT:
            state.current_unit.phase = "build"
            state.current_unit.extra["plan_checkpoint_cleared"] = True
        elif state.pause_reason == PAUSE_DONE_CHECKPOINT:
            state.current_unit.phase = "landing"
            state.current_unit.extra["done_checkpoint_cleared"] = True
        else:
            state.current_unit.phase = "pending"
    state.pause_ticket = target
    return resume_armed(project_root, state)


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
        except OrchestratorHalt:
            continue
    return out


def format_status(state: RunState) -> str:
    lines = [
        f"run_id: {state.run_id}",
        f"status: {state.status}",
        f"mode: {state.mode}",
        f"model: {state.model}",
    ]
    if state.pause_reason:
        lines.append(f"pause_reason: {state.pause_reason}")
    if state.pause_detail:
        lines.append(f"pause_detail: {state.pause_detail}")
    if state.pause_ticket:
        lines.append(f"pause_ticket: {state.pause_ticket}")
    if state.current_unit:
        u = state.current_unit
        lines.append(
            f"current: {u.ref} phase={u.phase} "
            f"dev={u.dev_attempts} review={u.review_cycles}"
        )
    if state.completed_refs:
        lines.append(f"completed: {', '.join(state.completed_refs)}")
    if state.deferred_refs:
        lines.append(f"plateau_deferred: {', '.join(state.deferred_refs)}")
    if state.blocked_refs:
        refs = ", ".join(b.get("ref", "?") for b in state.blocked_refs)
        lines.append(f"blocked: {refs}")
    return "\n".join(lines) + "\n"
