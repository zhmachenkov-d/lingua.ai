"""Post-dev artifact checks and optional verify commands."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .constants import log
from .plan_io import find_build_auto_result, read_frontmatter, ticket_slug_from_ref
from .policy import VerifyPolicy
from .scm import run_git

TERMINAL_OK = frozenset({"built", "done"})


@dataclass
class VerifyResult:
    ok: bool
    plan_status: str | None = None
    plan_path: Path | None = None
    plan_fm: dict[str, Any] = field(default_factory=dict)
    result_path: Path | None = None
    status_from_result_only: bool = False
    messages: list[str] = field(default_factory=list)
    command_outputs: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.ok:
            return "verify ok"
        return "; ".join(self.messages) or "verify failed"


def resolve_plan_status(
    *,
    project_root: Path,
    ticket_ref: str,
    plan_path: Path | None,
    plan_fm: dict[str, Any] | None = None,
) -> tuple[str, Path | None, dict[str, Any], Path | None, bool]:
    """Return (status, plan_path, fm, result_path, status_from_result_only)."""
    fm = dict(plan_fm or (read_frontmatter(plan_path) if plan_path else {}))
    status = str(fm.get("status") or "")
    result_path: Path | None = None
    status_from_result_only = False
    if not status:
        result_path = find_build_auto_result(
            project_root, ticket_slug_from_ref(ticket_ref)
        )
        if result_path is not None:
            result_fm = read_frontmatter(result_path)
            result_status = str(result_fm.get("status") or "")
            if result_status:
                status = result_status
                status_from_result_only = True
                if not fm.get("blocked_reason") and result_fm.get("blocked_reason"):
                    fm = {**fm, "blocked_reason": result_fm["blocked_reason"]}
                # Prefer followup/deferred from result when plan missing.
                for key in ("followup_review_recommended", "deferred"):
                    if key not in fm and key in result_fm:
                        fm[key] = result_fm[key]
    return status, plan_path, fm, result_path, status_from_result_only


def worktree_has_diff(project_root: Path, baseline_rev: str | None) -> bool:
    """True when the worktree has commits or unstaged changes vs baseline."""
    if baseline_rev:
        ahead = run_git(
            project_root,
            "rev-list",
            "--count",
            f"{baseline_rev}..HEAD",
            check=False,
        )
        try:
            if int((ahead.stdout or "0").strip() or "0") > 0:
                return True
        except ValueError:
            pass
        diff = run_git(
            project_root,
            "diff",
            "--quiet",
            baseline_rev,
            check=False,
        )
        if diff.returncode != 0:
            return True
    porcelain = run_git(project_root, "status", "--porcelain", check=False)
    return bool(porcelain.stdout.strip())


def run_verify_commands(
    project_root: Path, commands: list[str]
) -> tuple[bool, list[str]]:
    outputs: list[str] = []
    for cmd in commands:
        log.info("verify command: %s", cmd)
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        chunk = (
            f"$ {cmd}\n"
            f"exit={proc.returncode}\n"
            f"{(proc.stdout or '').rstrip()}\n"
            f"{(proc.stderr or '').rstrip()}"
        ).strip()
        outputs.append(chunk)
        if proc.returncode != 0:
            return False, outputs
    return True, outputs


def verify_unit(
    *,
    project_root: Path,
    ticket_ref: str,
    plan_path: Path | None,
    policy: VerifyPolicy,
    baseline_rev: str | None,
    expect_diff: bool,
    plan_fm: dict[str, Any] | None = None,
) -> VerifyResult:
    """Artifact + optional command verification after a build/fix attempt."""
    status, plan_path, fm, result_path, from_result = resolve_plan_status(
        project_root=project_root,
        ticket_ref=ticket_ref,
        plan_path=plan_path,
        plan_fm=plan_fm,
    )
    result = VerifyResult(
        ok=False,
        plan_status=status or None,
        plan_path=plan_path,
        plan_fm=fm,
        result_path=result_path,
        status_from_result_only=from_result,
    )
    if status == "blocked":
        result.messages.append("plan status blocked")
        return result
    if status not in TERMINAL_OK:
        result.messages.append(
            f"unexpected plan status after agent: {status or '(missing)'}"
        )
        return result

    if expect_diff and policy.require_diff:
        if not worktree_has_diff(project_root, baseline_rev):
            result.messages.append("expected non-empty diff vs baseline")
            return result

    if policy.commands:
        ok, outputs = run_verify_commands(project_root, policy.commands)
        result.command_outputs = outputs
        if not ok:
            result.messages.append("verify command failed")
            return result

    result.ok = True
    return result
