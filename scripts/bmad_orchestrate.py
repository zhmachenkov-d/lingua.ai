#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "cursor-sdk",
#   "pyyaml",
# ]
# ///
"""BMAD Cursor build orchestrator.

Python owns queueing, checkpoints, deferred append, mark-done, git push/PR, and
reporting. Cursor agents run only for ``bmad-build-auto`` and ``bmad-retrospective``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

TICKETS_SCRIPT = Path("_bmad/method/scripts/tickets.py")
PROTECTED_BRANCHES = frozenset({"main", "master"})
SHUTDOWN_COMPLETED = "completed"
SHUTDOWN_BLOCKED = "blocked"
SHUTDOWN_PLAN_CHECKPOINT = "plan_checkpoint"
SHUTDOWN_DONE_CHECKPOINT = "done_checkpoint"
SHUTDOWN_DIRTY_TREE = "dirty_tree"
SHUTDOWN_ERROR = "error"
SHUTDOWN_TICKET_NOT_RESOLVED = "ticket_not_resolved"


# --------------------------------------------------------------------------- report


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: TokenUsage | None) -> None:
        if other is None:
            return
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens


@dataclass
class UnitReport:
    ref: str
    kind: str  # ticket | retrospective
    plan_status: str | None = None
    outcome: str = "error"
    deferred_count: int = 0
    tokens: dict[str, int] | None = None
    agent_id: str | None = None
    run_id: str | None = None
    pr_url: str | None = None
    reason: str | None = None
    epic: str | None = None


@dataclass
class RunReport:
    units: list[UnitReport] = field(default_factory=list)
    shutdown: str = SHUTDOWN_COMPLETED
    shutdown_detail: str | None = None
    totals: dict[str, Any] = field(default_factory=dict)

    def add(self, unit: UnitReport) -> None:
        self.units.append(unit)

    def finalize_totals(self) -> None:
        usage = TokenUsage()
        marked_done = 0
        deferred = 0
        retros = 0
        prs: set[str] = set()
        tickets = 0
        for u in self.units:
            if u.kind == "ticket":
                tickets += 1
                if u.outcome == "done":
                    marked_done += 1
            elif u.kind == "retrospective":
                retros += 1
            deferred += u.deferred_count
            if u.tokens:
                usage.add(
                    TokenUsage(
                        input_tokens=u.tokens.get("input_tokens", 0),
                        output_tokens=u.tokens.get("output_tokens", 0),
                        total_tokens=u.tokens.get("total_tokens", 0),
                    )
                )
            if u.pr_url:
                prs.add(u.pr_url)
        self.totals = {
            "tickets": tickets,
            "marked_done": marked_done,
            "deferred_items": deferred,
            "retrospectives": retros,
            "prs": len(prs),
            "tokens": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        self.finalize_totals()
        return {
            "shutdown": self.shutdown,
            "shutdown_detail": self.shutdown_detail,
            "units": [asdict(u) for u in self.units],
            "totals": self.totals,
        }

    def print_human(self, stream=sys.stderr) -> None:
        self.finalize_totals()
        detail = f" — {self.shutdown_detail}" if self.shutdown_detail else ""
        print("=== BMAD orchestrate report ===", file=stream)
        print(f"Shutdown: {self.shutdown}{detail}", file=stream)
        tickets = [u for u in self.units if u.kind == "ticket"]
        retros = [u for u in self.units if u.kind == "retrospective"]
        print("Tickets:", file=stream)
        if not tickets:
            print("  (none)", file=stream)
        for u in tickets:
            tok = u.tokens["total_tokens"] if u.tokens else "null"
            extra = ""
            if u.outcome == "blocked" and u.reason:
                extra = f"  reason={u.reason}"
            elif u.pr_url:
                extra = f"  pr={u.pr_url}"
            elif u.reason:
                extra = f"  reason={u.reason}"
            print(
                f"  {u.ref:<40} {u.outcome:<12} tokens={tok}  deferred={u.deferred_count}{extra}",
                file=stream,
            )
        print("Retrospectives:", file=stream)
        if not retros:
            print("  none", file=stream)
        else:
            for u in retros:
                tok = u.tokens["total_tokens"] if u.tokens else "null"
                extra = f"  pr={u.pr_url}" if u.pr_url else ""
                print(f"  {u.ref:<40} {u.outcome:<12} tokens={tok}{extra}", file=stream)
        t = self.totals
        tok = t["tokens"]
        print(
            f"Totals: tickets={t['tickets']}  done={t['marked_done']}  "
            f"tokens={tok['total_tokens']}  (in={tok['input_tokens']} out={tok['output_tokens']})  "
            f"deferred={t['deferred_items']}  retros={t['retrospectives']}  prs={t['prs']}",
            file=stream,
        )


class OrchestratorHalt(Exception):
    """Stop the loop with a shutdown reason (non-zero unless completed)."""

    def __init__(self, shutdown: str, detail: str | None = None):
        self.shutdown = shutdown
        self.detail = detail
        super().__init__(detail or shutdown)


# --------------------------------------------------------------------------- tickets.py


def _tickets_bin(project_root: Path) -> list[str]:
    script = project_root / TICKETS_SCRIPT
    if not script.is_file():
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"missing {script}")
    return ["uv", "run", str(script), "--project-root", str(project_root)]


def tickets_cmd(project_root: Path, *args: str) -> dict[str, Any]:
    cmd = [*_tickets_bin(project_root), *args]
    proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
    raw_out = (proc.stdout or "").strip()
    raw_err = (proc.stderr or "").strip()
    payload: dict[str, Any] | None = None
    for blob in (raw_out, raw_err):
        if not blob:
            continue
        try:
            payload = json.loads(blob)
            break
        except json.JSONDecodeError:
            continue
    if proc.returncode != 0:
        err = None
        if isinstance(payload, dict):
            err = payload.get("error")
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            err or raw_err or raw_out or f"tickets.py exited {proc.returncode}",
        )
    if not isinstance(payload, dict):
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"tickets.py returned non-JSON: {raw_out[:200]}"
        )
    return payload


def tickets_next(project_root: Path, folder: str | None = None) -> dict[str, Any]:
    args = ["next"]
    if folder:
        args.append(folder)
    args.append("--synced")
    return tickets_cmd(project_root, *args)


def tickets_find(
    project_root: Path, ref: str, folder: str | None = None
) -> dict[str, Any]:
    args = ["find"]
    if folder:
        args.extend([folder, ref])
    else:
        args.append(ref)
    return tickets_cmd(project_root, *args)


def tickets_status(project_root: Path, folder: str | None = None) -> dict[str, Any]:
    args = ["status"]
    if folder:
        args.append(folder)
    return tickets_cmd(project_root, *args)


def tickets_mark_done(
    project_root: Path, ref: str, plan_path: Path | None, folder: str | None = None
) -> None:
    """Mark plan status done. Falls back to editing the plan when store refuses mark."""
    args = ["mark"]
    if folder:
        args.extend([folder, ref, "done"])
    else:
        args.extend([ref, "done"])
    cmd = [*_tickets_bin(project_root), *args]
    proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
    if proc.returncode == 0:
        return
    err_blob = (proc.stderr or proc.stdout or "").strip()
    err_msg = err_blob
    try:
        err_msg = json.loads(err_blob).get("error", err_blob)
    except json.JSONDecodeError:
        pass
    # GitHub (and other tracker) stores refuse mark; edit plan frontmatter like build-auto HALT fallback.
    if (
        plan_path
        and plan_path.is_file()
        and "change status through the store" in str(err_msg)
    ):
        set_plan_status(plan_path, "done")
        return
    raise OrchestratorHalt(SHUTDOWN_ERROR, f"mark done failed: {err_msg}")


# --------------------------------------------------------------------------- plan / deferred IO


def read_frontmatter(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip("\n")
    data = yaml.safe_load(block) or {}
    return data if isinstance(data, dict) else {}


def set_plan_status(path: Path, status: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"plan has no frontmatter: {path}")
    end = text.find("\n---", 3)
    if end < 0:
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"plan frontmatter not closed: {path}")
    block = text[3:end].strip("\n")
    data = yaml.safe_load(block) or {}
    if not isinstance(data, dict):
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"plan frontmatter is not a mapping: {path}"
        )
    data["status"] = status
    new_block = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip()
    path.write_text(f"---\n{new_block}\n---{text[end + 4 :]}", encoding="utf-8")


def initiative_dir_for(plan_path: Path, project_root: Path) -> Path:
    """Locate the initiative folder that owns deferred-work.md."""
    root = project_root.resolve()
    for parent in [plan_path.resolve().parent, *plan_path.resolve().parents]:
        if parent == root or root not in parent.parents:
            break
        if (parent / "deferred-work.md").is_file():
            return parent
        if (parent / "tickets").is_dir() and (
            (parent / f"{parent.name}.md").is_file()
            or parent.name.startswith("initiative")
        ):
            return parent
    for parent in plan_path.resolve().parents:
        if parent.name.startswith("initiative") and (parent / "tickets").is_dir():
            return parent
    raise OrchestratorHalt(
        SHUTDOWN_ERROR, f"cannot locate initiative for plan {plan_path}"
    )


def append_deferred(plan_path: Path, project_root: Path, items: list[Any]) -> int:
    if not items:
        return 0
    initiative = initiative_dir_for(plan_path, project_root)
    dest = initiative / "deferred-work.md"
    try:
        rel_plan = str(plan_path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        rel_plan = str(plan_path)
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary", "")).strip() or "(no summary)"
        evidence = str(item.get("evidence", "")).strip() or "(no evidence)"
        chunk = [
            f"- source_plan: `{rel_plan}`",
            f"  summary: {summary}",
            f"  evidence: {evidence}",
        ]
        for key in ("location", "severity"):
            if item.get(key):
                chunk.append(f"  {key}: {item[key]}")
        lines.append("\n".join(chunk))
    if not lines:
        return 0
    existing = (
        dest.read_text(encoding="utf-8") if dest.is_file() else "# Deferred work\n"
    )
    if not existing.endswith("\n"):
        existing += "\n"
    if not existing.endswith("\n\n"):
        existing += "\n"
    dest.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


# --------------------------------------------------------------------------- git / gh


def run_git(
    project_root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args], cwd=project_root, capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            proc.stderr.strip()
            or proc.stdout.strip()
            or f"git {' '.join(args)} failed",
        )
    return proc


def require_clean_tree(project_root: Path) -> None:
    proc = run_git(project_root, "status", "--porcelain")
    if proc.stdout.strip():
        raise OrchestratorHalt(SHUTDOWN_DIRTY_TREE, "working tree is not clean")


def current_branch(project_root: Path) -> str:
    return run_git(project_root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def has_unpushed_or_new_commits(project_root: Path) -> bool:
    """True when HEAD has commits not on origin for this branch (or no upstream)."""
    branch = current_branch(project_root)
    if branch in PROTECTED_BRANCHES:
        return False
    # Always attempt push after successful work; caller decides --no-push.
    return True


def ensure_push_and_pr(
    project_root: Path,
    *,
    epic: str | None,
    refs: list[str],
    no_push: bool,
    dry_run: bool,
) -> str | None:
    if dry_run or no_push:
        return None
    branch = current_branch(project_root)
    if branch in PROTECTED_BRANCHES:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"refusing to push protected branch {branch}"
        )
    push = subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if push.returncode != 0:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            push.stderr.strip() or push.stdout.strip() or "git push failed",
        )

    view = subprocess.run(
        ["gh", "pr", "view", "--json", "url"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if view.returncode == 0:
        try:
            return json.loads(view.stdout).get("url")
        except json.JSONDecodeError:
            return None

    epic_slug = epic or "build"
    title = f"feat({epic_slug}): orchestrated build for {', '.join(refs)}"
    if len(title) > 72:
        title = f"feat({epic_slug}): orchestrated build"
    body = "\n".join(
        [
            "## Summary",
            *(f"- Orchestrated BMAD build for `{r}`" for r in refs),
            "",
            "## Test plan",
            "- [ ] Review agent-produced commits and plan status",
            "- [ ] Confirm CI on this PR",
        ]
    )
    create = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if create.returncode != 0:
        # Race: PR may exist now
        view2 = subprocess.run(
            ["gh", "pr", "view", "--json", "url"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        if view2.returncode == 0:
            try:
                return json.loads(view2.stdout).get("url")
            except json.JSONDecodeError:
                pass
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            create.stderr.strip() or create.stdout.strip() or "gh pr create failed",
        )
    url = (create.stdout or "").strip().splitlines()
    return url[-1] if url else None


# --------------------------------------------------------------------------- Cursor agent


@dataclass
class AgentRunResult:
    status: str
    usage: TokenUsage | None
    agent_id: str | None
    run_id: str | None
    error: str | None = None


def run_cursor_agent(
    *,
    project_root: Path,
    model: str,
    prompt: str,
    dry_run: bool,
) -> AgentRunResult:
    if dry_run:
        print(f"[dry-run] agent prompt:\n{prompt}", file=sys.stderr)
        return AgentRunResult(status="dry_run", usage=None, agent_id=None, run_id=None)

    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise OrchestratorHalt(SHUTDOWN_ERROR, "CURSOR_API_KEY is not set")

    from cursor_sdk import Agent, CursorAgentError, LocalAgentOptions

    try:
        with Agent.create(
            model=model,
            api_key=api_key,
            local=LocalAgentOptions(cwd=str(project_root), setting_sources=["project"]),
        ) as agent:
            agent_id = getattr(agent, "agent_id", None) or getattr(
                agent, "agentId", None
            )
            run = agent.send(prompt)
            run_id = getattr(run, "id", None)
            result = run.wait()
            usage = None
            raw_usage = getattr(result, "usage", None) or getattr(run, "usage", None)
            if raw_usage is not None:
                usage = TokenUsage(
                    input_tokens=int(getattr(raw_usage, "input_tokens", 0) or 0),
                    output_tokens=int(getattr(raw_usage, "output_tokens", 0) or 0),
                    total_tokens=int(getattr(raw_usage, "total_tokens", 0) or 0),
                )
            status = getattr(result, "status", None) or "unknown"
            err = None
            if status == "error":
                err = f"agent run failed: {run_id}"
            return AgentRunResult(
                status=str(status),
                usage=usage,
                agent_id=str(agent_id) if agent_id else None,
                run_id=str(run_id) if run_id else None,
                error=err,
            )
    except CursorAgentError as err:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            f"Cursor agent startup failed: {err.message} (retryable={err.is_retryable})",
        ) from err


def usage_dict(usage: TokenUsage | None) -> dict[str, int] | None:
    if usage is None:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


# --------------------------------------------------------------------------- orchestration


def first_ready(next_payload: dict[str, Any]) -> dict[str, Any] | None:
    ready = next_payload.get("ready_to_start") or []
    if ready:
        return ready[0]
    backlog = next_payload.get("backlog")
    if isinstance(backlog, dict):
        ready = backlog.get("ready_to_start") or []
        if ready:
            return ready[0]
    return None


def epic_fully_done(project_root: Path, epic: str) -> bool:
    if not epic or epic == "backlog":
        return False
    try:
        status = tickets_status(project_root, epic)
    except OrchestratorHalt:
        return False
    tickets = status.get("tickets") or []
    if not tickets:
        return False
    return all(t.get("state") == "done" or t.get("status") == "done" for t in tickets)


def build_prompt(ref: str, *, halt_after_planning: bool = False) -> str:
    base = f"Run skill bmad-build-auto for ticket {ref}. Do not start any other ticket."
    if halt_after_planning:
        return base + " Halt after planning."
    return base


def retro_prompt(epic_ref: str) -> str:
    return f"Run skill bmad-retrospective -H {epic_ref}. Headless."


def process_ticket(
    *,
    project_root: Path,
    ref: str,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
    followup_used: bool = False,
) -> str | None:
    """Process one ticket. Returns epic slug if that epic just became fully done."""
    try:
        found = tickets_find(project_root, ref)
    except OrchestratorHalt as e:
        if e.shutdown == SHUTDOWN_ERROR and "no ticket matches" in (e.detail or ""):
            raise OrchestratorHalt(SHUTDOWN_TICKET_NOT_RESOLVED, e.detail) from e
        raise

    ticket_ref = str(found.get("ref") or ref)
    epic = found.get("epic")
    plan_path = Path(found["plan"]) if found.get("plan") else None
    plan_fm = read_frontmatter(plan_path) if plan_path else {}
    plan_status = str(plan_fm.get("status") or "")

    plan_checkpoint = bool(found.get("plan_checkpoint"))
    done_checkpoint = bool(found.get("done_checkpoint"))

    # plan_checkpoint: halt-after-planning when plan is missing/draft (or not yet ready-for-dev).
    # If already ready-for-dev+, dispatch a normal implement resume.
    post_plan_statuses = (
        "ready-for-dev",
        "in-progress",
        "in-review",
        "built",
        "done",
        "blocked",
    )
    halt_after_planning = bool(
        plan_checkpoint and plan_status not in post_plan_statuses
    )

    if not dry_run:
        require_clean_tree(project_root)

    prompt = build_prompt(ticket_ref, halt_after_planning=halt_after_planning)
    agent = run_cursor_agent(
        project_root=project_root, model=model, prompt=prompt, dry_run=dry_run
    )

    unit = UnitReport(
        ref=ticket_ref,
        kind="ticket",
        epic=str(epic) if epic else None,
        tokens=usage_dict(agent.usage),
        agent_id=agent.agent_id,
        run_id=agent.run_id,
    )

    if dry_run:
        unit.outcome = "dry_run"
        unit.plan_status = plan_status or None
        report.add(unit)
        return None

    if agent.error:
        unit.outcome = "error"
        unit.reason = agent.error
        report.add(unit)
        raise OrchestratorHalt(SHUTDOWN_ERROR, agent.error)

    # Re-read plan after agent
    try:
        found = tickets_find(project_root, ticket_ref)
    except OrchestratorHalt:
        pass
    plan_path = Path(found["plan"]) if found.get("plan") else plan_path
    plan_fm = read_frontmatter(plan_path) if plan_path else {}
    plan_status = str(plan_fm.get("status") or "")
    unit.plan_status = plan_status or None
    done_checkpoint = bool(found.get("done_checkpoint")) or done_checkpoint

    if halt_after_planning:
        unit.outcome = "checkpoint"
        unit.reason = "plan_checkpoint: waiting for human plan approval"
        report.add(unit)
        raise OrchestratorHalt(
            SHUTDOWN_PLAN_CHECKPOINT, f"ticket {ticket_ref}: plan checkpoint"
        )

    if plan_status == "blocked":
        reason = str(
            plan_fm.get("blocked_reason") or found.get("blocked_reason") or "blocked"
        )
        unit.outcome = "blocked"
        unit.reason = reason
        report.add(unit)
        raise OrchestratorHalt(SHUTDOWN_BLOCKED, f"ticket {ticket_ref}: {reason}")

    if plan_status not in ("built", "done"):
        unit.outcome = "error"
        unit.reason = (
            f"unexpected plan status after agent: {plan_status or '(missing)'}"
        )
        report.add(unit)
        raise OrchestratorHalt(SHUTDOWN_ERROR, unit.reason)

    deferred_items = plan_fm.get("deferred") or []
    if not isinstance(deferred_items, list):
        deferred_items = []
    if plan_path and deferred_items:
        unit.deferred_count = append_deferred(plan_path, project_root, deferred_items)

    if done_checkpoint:
        unit.outcome = "checkpoint"
        unit.reason = "done_checkpoint: waiting for human continue"
        report.add(unit)
        raise OrchestratorHalt(
            SHUTDOWN_DONE_CHECKPOINT, f"ticket {ticket_ref}: done checkpoint"
        )

    followup = bool(plan_fm.get("followup_review_recommended"))
    if followup and not followup_used:
        unit.outcome = "followup"
        report.add(unit)
        # One extra re-dispatch, then continue to mark policy on the second result.
        return process_ticket(
            project_root=project_root,
            ref=ticket_ref,
            report=report,
            model=model,
            dry_run=dry_run,
            no_push=no_push,
            followup_used=True,
        )

    if plan_path:
        tickets_mark_done(project_root, ticket_ref, plan_path)
    unit.outcome = "done"

    pr_url = None
    if has_unpushed_or_new_commits(project_root):
        pr_url = ensure_push_and_pr(
            project_root,
            epic=str(epic) if epic else None,
            refs=[ticket_ref],
            no_push=no_push,
            dry_run=dry_run,
        )
        unit.pr_url = pr_url
    report.add(unit)

    if epic and epic_fully_done(project_root, str(epic)):
        return str(epic)
    return None


def run_retrospective(
    *,
    project_root: Path,
    epic: str,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
) -> None:
    if not dry_run:
        require_clean_tree(project_root)
    agent = run_cursor_agent(
        project_root=project_root,
        model=model,
        prompt=retro_prompt(epic),
        dry_run=dry_run,
    )
    unit = UnitReport(
        ref=epic,
        kind="retrospective",
        epic=epic,
        tokens=usage_dict(agent.usage),
        agent_id=agent.agent_id,
        run_id=agent.run_id,
    )
    if dry_run:
        unit.outcome = "dry_run"
        report.add(unit)
        return
    if agent.error:
        unit.outcome = "error"
        unit.reason = agent.error
        report.add(unit)
        raise OrchestratorHalt(SHUTDOWN_ERROR, agent.error)
    unit.outcome = "done"
    pr_url = ensure_push_and_pr(
        project_root,
        epic=epic,
        refs=[f"retrospective:{epic}"],
        no_push=no_push,
        dry_run=dry_run,
    )
    unit.pr_url = pr_url
    report.add(unit)


def maybe_retro_after(
    epic: str | None,
    *,
    project_root: Path,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
    retros_done: set[str],
) -> None:
    if not epic or epic in retros_done or epic == "backlog":
        return
    if not epic_fully_done(project_root, epic):
        return
    run_retrospective(
        project_root=project_root,
        epic=epic,
        report=report,
        model=model,
        dry_run=dry_run,
        no_push=no_push,
    )
    retros_done.add(epic)


def resolve_project_root(raw: str | None) -> Path:
    if raw:
        root = Path(raw).resolve()
    else:
        here = Path.cwd().resolve()
        root = None
        for p in [here, *here.parents]:
            if (p / "_bmad").is_dir():
                root = p
                break
        if root is None:
            raise SystemExit(
                "no project root: pass --project-root (folder containing _bmad/)"
            )
    if not (root / "_bmad").is_dir():
        raise SystemExit(f"no _bmad/ under {root}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--ticket", metavar="REF", help="orchestrate a single ticket")
    g.add_argument(
        "--epic", metavar="REF", help="orchestrate all ready tickets in an epic"
    )
    p.add_argument(
        "--model",
        default="composer-2.5",
        help="Cursor model id (default: composer-2.5)",
    )
    p.add_argument(
        "--project-root", default=None, help="project root containing _bmad/"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="resolve queue and print prompts only"
    )
    p.add_argument(
        "--no-push", action="store_true", help="skip git push and gh pr create"
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = RunReport()
    project_root = resolve_project_root(args.project_root)
    retros_done: set[str] = set()

    try:
        if args.ticket:
            epic = process_ticket(
                project_root=project_root,
                ref=args.ticket,
                report=report,
                model=args.model,
                dry_run=args.dry_run,
                no_push=args.no_push,
            )
            maybe_retro_after(
                epic,
                project_root=project_root,
                report=report,
                model=args.model,
                dry_run=args.dry_run,
                no_push=args.no_push,
                retros_done=retros_done,
            )
            report.shutdown = SHUTDOWN_COMPLETED

        elif args.epic:
            while True:
                nxt = tickets_next(project_root, args.epic)
                ready = nxt.get("ready_to_start") or []
                if not ready:
                    break
                ref = str(ready[0].get("ref") or ready[0].get("id"))
                epic = process_ticket(
                    project_root=project_root,
                    ref=ref,
                    report=report,
                    model=args.model,
                    dry_run=args.dry_run,
                    no_push=args.no_push,
                )
                # In dry-run, avoid infinite loop on the same ready ticket.
                if args.dry_run:
                    break
                maybe_retro_after(
                    epic or args.epic,
                    project_root=project_root,
                    report=report,
                    model=args.model,
                    dry_run=args.dry_run,
                    no_push=args.no_push,
                    retros_done=retros_done,
                )
            if not args.dry_run and epic_fully_done(project_root, args.epic):
                maybe_retro_after(
                    args.epic,
                    project_root=project_root,
                    report=report,
                    model=args.model,
                    dry_run=args.dry_run,
                    no_push=args.no_push,
                    retros_done=retros_done,
                )
            report.shutdown = SHUTDOWN_COMPLETED

        else:
            # All mode: walk ready tickets/bugs across active initiative (+ backlog).
            seen: set[str] = set()
            while True:
                nxt = tickets_next(project_root)
                item = first_ready(nxt)
                if not item:
                    break
                ref = str(item.get("ref") or item.get("id"))
                if ref in seen:
                    raise OrchestratorHalt(
                        SHUTDOWN_ERROR,
                        f"ready ticket {ref} did not leave ready_to_start; refusing to loop",
                    )
                seen.add(ref)
                if args.dry_run:
                    process_ticket(
                        project_root=project_root,
                        ref=ref,
                        report=report,
                        model=args.model,
                        dry_run=True,
                        no_push=args.no_push,
                    )
                    break
                epic = process_ticket(
                    project_root=project_root,
                    ref=ref,
                    report=report,
                    model=args.model,
                    dry_run=False,
                    no_push=args.no_push,
                )
                maybe_retro_after(
                    epic,
                    project_root=project_root,
                    report=report,
                    model=args.model,
                    dry_run=False,
                    no_push=args.no_push,
                    retros_done=retros_done,
                )
            report.shutdown = SHUTDOWN_COMPLETED

    except OrchestratorHalt as halt:
        report.shutdown = halt.shutdown
        report.shutdown_detail = halt.detail

    report.print_human(sys.stderr)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if report.shutdown == SHUTDOWN_COMPLETED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
