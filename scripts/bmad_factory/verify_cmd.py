"""Execute policy.verify commands before mark-done / PR landing."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from .constants import SHUTDOWN_ERROR, FactoryHalt, log
from .policy import Policy, VerifyPolicy
from .scm import commits_ahead_of_default, default_branch_tip, run_git


def has_code_diff_vs_target(project_root: Path, base: str | None = None) -> bool:
    """True when HEAD differs from the merge target (commits and/or file diff)."""
    tip = base or default_branch_tip(project_root)
    if tip is None:
        return commits_ahead_of_default(project_root) > 0
    ahead = run_git(
        project_root, "rev-list", "--count", f"{tip}..HEAD", check=False
    )
    try:
        if int((ahead.stdout or "0").strip() or "0") > 0:
            return True
    except ValueError:
        pass
    diff = run_git(
        project_root, "diff", "--name-only", f"{tip}...HEAD", check=False
    )
    if (diff.stdout or "").strip():
        return True
    # Uncommitted changes (should be rare after require_clean_tree, but catch them).
    porcelain = run_git(project_root, "status", "--porcelain", check=False)
    return bool((porcelain.stdout or "").strip())


def run_verify_commands(
    project_root: Path,
    verify: VerifyPolicy,
    *,
    ticket_ref: str | None = None,
    agent_run_id: str | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Run each verify command; non-zero exit raises FactoryHalt."""
    if not verify.commands:
        log.info("verify: no commands configured; skipping")
        return

    base_env = os.environ.copy()
    if ticket_ref:
        base_env["QUALITY_TICKET"] = ticket_ref
    if agent_run_id:
        base_env["QUALITY_AGENT_RUN_ID"] = agent_run_id
    if env:
        base_env.update(env)

    for raw in verify.commands:
        cmd = raw.strip()
        if not cmd:
            continue
        log.info("verify: running %s", cmd)
        try:
            argv = shlex.split(cmd)
        except ValueError as exc:
            raise FactoryHalt(
                SHUTDOWN_ERROR, f"verify command not parseable: {cmd!r} ({exc})"
            ) from exc
        proc = subprocess.run(
            argv,
            cwd=project_root,
            env=base_env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            detail = (
                proc.stderr.strip()
                or proc.stdout.strip()
                or f"verify command exited {proc.returncode}: {cmd}"
            )
            raise FactoryHalt(
                SHUTDOWN_ERROR,
                f"verify failed ({proc.returncode}): {cmd}\n{detail}",
            )
        if proc.stdout.strip():
            log.info("verify stdout: %s", proc.stdout.strip()[:500])


def run_policy_verify(
    project_root: Path,
    policy: Policy,
    *,
    ticket_ref: str | None = None,
    agent_run_id: str | None = None,
) -> None:
    """Apply require_diff (if set) then run verify.commands."""
    verify = policy.verify
    if verify.require_diff and not has_code_diff_vs_target(project_root):
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            "verify.require_diff: no code diff vs target branch; "
            "refusing to mark done / open PR",
        )
    run_verify_commands(
        project_root,
        verify,
        ticket_ref=ticket_ref,
        agent_run_id=agent_run_id,
    )
