"""Git helpers, worktree isolation, and optional PR remote landing."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    BRANCH_SLUG_RE,
    MERGE_POLL_INTERVAL_S,
    MERGE_TIMEOUT_S,
    PROTECTED_BRANCHES,
    SHUTDOWN_DIRTY_TREE,
    SHUTDOWN_ERROR,
    OrchestratorHalt,
    log,
)
from .plan_io import read_frontmatter
from .tracker import _tickets_table, load_store_config


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
    log.info("checking clean working tree")
    proc = run_git(project_root, "status", "--porcelain")
    if proc.stdout.strip():
        raise OrchestratorHalt(SHUTDOWN_DIRTY_TREE, "working tree is not clean")


def current_branch(project_root: Path) -> str:
    return run_git(project_root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def default_branch(project_root: Path) -> str:
    """Return the repo default branch (main/master), preferring ``gh`` metadata."""
    proc = subprocess.run(
        ["gh", "repo", "view", "--json", "defaultBranchRef"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
            name = (data.get("defaultBranchRef") or {}).get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    for candidate in ("main", "master"):
        check = run_git(
            project_root,
            "rev-parse",
            "--verify",
            f"refs/heads/{candidate}",
            check=False,
        )
        if check.returncode == 0:
            return candidate
    return "main"


def default_branch_tip(project_root: Path) -> str | None:
    """Resolve a rev for the default branch tip (prefer ``origin/<default>``)."""
    base = default_branch(project_root)
    for tip in (f"origin/{base}", base):
        check = run_git(project_root, "rev-parse", "--verify", tip, check=False)
        if check.returncode == 0:
            return tip
    return None


def commits_ahead_of_default(project_root: Path) -> int:
    """Count commits on HEAD that are not reachable from the default branch tip."""
    tip = default_branch_tip(project_root)
    if tip is None:
        return 0
    proc = run_git(project_root, "rev-list", "--count", f"{tip}..HEAD")
    try:
        return int(proc.stdout.strip() or "0")
    except ValueError:
        return 0


def has_unpushed_or_new_commits(project_root: Path) -> bool:
    """True when HEAD has commits ahead of the default branch (and is not protected)."""
    branch = current_branch(project_root)
    if branch in PROTECTED_BRANCHES:
        return False
    return commits_ahead_of_default(project_root) > 0


def sanitize_branch_slug(ref: str) -> str:
    slug = ref.strip().lower().replace(" ", "-")
    slug = BRANCH_SLUG_RE.sub("-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-._")
    return slug or "work"


def checkout_work_branch(project_root: Path, ref: str) -> str:
    """Ensure a non-protected work branch ``bmad/<ref>`` from an up-to-date default."""
    branch = current_branch(project_root)
    if branch not in PROTECTED_BRANCHES:
        log.info("already on work branch=%s", branch)
        return branch
    default = default_branch(project_root)
    if branch != default:
        log.info("checkout default branch=%s", default)
        run_git(project_root, "checkout", default)
    log.info("git pull --ff-only on %s", default)
    pull = run_git(project_root, "pull", "--ff-only", check=False)
    if pull.returncode != 0:
        run_git(project_root, "pull")
    name = f"bmad/{sanitize_branch_slug(ref)}"
    exists = run_git(project_root, "rev-parse", "--verify", name, check=False)
    if exists.returncode == 0:
        log.info("checkout existing work branch=%s", name)
        run_git(project_root, "checkout", name)
    else:
        log.info("create work branch=%s from=%s", name, default)
        run_git(project_root, "checkout", "-b", name)
    return name


def worktree_branch_name(run_id: str, ref: str) -> str:
    """Branch naming: ``bmad-orch/<run_id>/<slug>``."""
    return f"bmad-orch/{sanitize_branch_slug(run_id)}/{sanitize_branch_slug(ref)}"


def worktree_path_for(project_root: Path, run_id: str, ref: str) -> Path:
    """Filesystem path for an isolated worktree under ``.bmad-orchestrate/worktrees/``."""
    return (
        project_root
        / ".bmad-orchestrate"
        / "worktrees"
        / sanitize_branch_slug(run_id)
        / sanitize_branch_slug(ref)
    )


def resolve_target_branch(project_root: Path, configured: str | None) -> str:
    if configured and configured.strip():
        return configured.strip()
    return default_branch(project_root)


def _refresh_target_branch(project_root: Path, target: str) -> str:
    """Checkout target in the main repo and fast-forward; return tip SHA."""
    cur = current_branch(project_root)
    if cur != target:
        run_git(project_root, "checkout", target)
    pull = run_git(project_root, "pull", "--ff-only", check=False)
    if pull.returncode != 0:
        run_git(project_root, "pull", check=False)
    tip = run_git(project_root, "rev-parse", "HEAD").stdout.strip()
    return tip


@dataclass
class WorktreeSession:
    path: Path
    branch: str
    baseline_rev: str
    target_branch: str


def create_unit_worktree(
    project_root: Path,
    *,
    run_id: str,
    ref: str,
    target_branch: str | None = None,
) -> WorktreeSession:
    """Create (or reuse) a worktree + branch for one ticket unit."""
    target = resolve_target_branch(project_root, target_branch)
    baseline = _refresh_target_branch(project_root, target)
    branch = worktree_branch_name(run_id, ref)
    path = worktree_path_for(project_root, run_id, ref)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = run_git(project_root, "rev-parse", "--verify", branch, check=False)
    listed = run_git(project_root, "worktree", "list", "--porcelain", check=False)
    already = path.is_dir() and str(path) in (listed.stdout or "")

    if already:
        log.info("reuse worktree path=%s branch=%s", path, branch)
    elif existing.returncode == 0:
        log.info("add worktree for existing branch=%s path=%s", branch, path)
        if path.exists():
            # Stale directory without worktree registration.
            shutil.rmtree(path)
        run_git(project_root, "worktree", "add", str(path), branch)
    else:
        log.info("create worktree branch=%s path=%s from=%s", branch, path, baseline)
        if path.exists():
            shutil.rmtree(path)
        run_git(
            project_root,
            "worktree",
            "add",
            "-b",
            branch,
            str(path),
            baseline,
        )
    tip = run_git(path, "rev-parse", "HEAD").stdout.strip()
    return WorktreeSession(
        path=path, branch=branch, baseline_rev=tip, target_branch=target
    )


def _commit_worktree_if_dirty(
    worktree: Path,
    *,
    message: str,
) -> bool:
    """Stage and commit dirty files in the worktree. Returns True if a commit was made."""
    status = run_git(worktree, "status", "--porcelain")
    if not status.stdout.strip():
        return False
    run_git(worktree, "add", "-A")
    run_git(worktree, "commit", "-m", message)
    return True


def squash_merge_worktree(
    project_root: Path,
    session: WorktreeSession,
    *,
    subject: str,
) -> bool:
    """Squash-merge the worktree branch into the target branch in the main repo.

    Returns True when a squash commit was created.
    """
    # Ensure agent changes are committed inside the worktree first.
    _commit_worktree_if_dirty(session.path, message=subject)

    ahead = run_git(
        project_root,
        "rev-list",
        "--count",
        f"{session.target_branch}..{session.branch}",
        check=False,
    )
    try:
        count = int((ahead.stdout or "0").strip() or "0")
    except ValueError:
        count = 0
    if count < 1:
        log.info(
            "no commits to squash-merge branch=%s into=%s",
            session.branch,
            session.target_branch,
        )
        return False

    cur = current_branch(project_root)
    if cur != session.target_branch:
        run_git(project_root, "checkout", session.target_branch)

    log.info(
        "squash-merge %s into %s subject=%s",
        session.branch,
        session.target_branch,
        subject,
    )
    merge = run_git(
        project_root,
        "merge",
        "--squash",
        session.branch,
        check=False,
    )
    if merge.returncode != 0:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            merge.stderr.strip()
            or merge.stdout.strip()
            or f"git merge --squash {session.branch} failed",
        )
    # Empty squash (no content change) — abort quietly.
    staged = run_git(project_root, "diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        log.info("squash produced empty tree; skipping commit")
        run_git(project_root, "reset", "--hard", "HEAD", check=False)
        return False
    run_git(project_root, "commit", "-m", subject)
    return True


def cleanup_worktree(
    project_root: Path, session: WorktreeSession, *, delete_branch: bool = True
) -> None:
    """Remove the worktree directory and optionally delete the feature branch."""
    log.info("remove worktree path=%s branch=%s", session.path, session.branch)
    rm = run_git(
        project_root,
        "worktree",
        "remove",
        "--force",
        str(session.path),
        check=False,
    )
    if rm.returncode != 0 and session.path.exists():
        shutil.rmtree(session.path, ignore_errors=True)
        run_git(project_root, "worktree", "prune", check=False)
    if delete_branch:
        run_git(project_root, "branch", "-D", session.branch, check=False)


def land_unit(
    project_root: Path,
    *,
    isolation: str,
    remote: str,
    no_push: bool,
    dry_run: bool,
    session: WorktreeSession | None,
    epic: str | None,
    refs: list[str],
    ticket_type: str | None = None,
    title: str | None = None,
    tracker_id: str | None = None,
    plan_path: Path | None = None,
    kind: str = "ticket",
) -> str | None:
    """Land unit changes: local squash (worktree) and/or optional PR remote."""
    if dry_run:
        return None

    subject = _pr_title_for_ticket(
        epic=epic,
        refs=refs,
        ticket_type=ticket_type,
        title=title,
        kind=kind,
    )

    if isolation == "worktree" and session is not None:
        _commit_worktree_if_dirty(session.path, message=subject)
        if remote == "pr" and not no_push:
            # Push/PR/merge from the worktree feature branch, then prune worktree.
            url = ensure_push_pr_and_merge(
                session.path,
                epic=epic,
                refs=refs,
                no_push=False,
                dry_run=False,
                ticket_type=ticket_type,
                title=title,
                tracker_id=tracker_id,
                plan_path=plan_path,
                kind=kind,
            )
            cleanup_worktree(project_root, session, delete_branch=False)
            run_git(project_root, "checkout", session.target_branch, check=False)
            pull = run_git(project_root, "pull", "--ff-only", check=False)
            if pull.returncode != 0:
                run_git(project_root, "pull", check=False)
            return url
        squash_merge_worktree(project_root, session, subject=subject)
        cleanup_worktree(project_root, session, delete_branch=True)
        return None

    # inplace isolation
    if remote == "pr" and not no_push and has_unpushed_or_new_commits(project_root):
        return ensure_push_pr_and_merge(
            project_root,
            epic=epic,
            refs=refs,
            no_push=False,
            dry_run=False,
            ticket_type=ticket_type,
            title=title,
            tracker_id=tracker_id,
            plan_path=plan_path,
            kind=kind,
        )
    return None


def _gh_pr_view(project_root: Path, fields: str) -> dict[str, Any] | None:
    proc = subprocess.run(
        ["gh", "pr", "view", "--json", fields],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


_PR_EXCERPT_CAP = 800


def _commit_type_for_ticket(ticket_type: str | None, *, kind: str = "ticket") -> str:
    if kind == "retrospective":
        return "chore"
    t = (ticket_type or "").strip().lower()
    if t in {"bug", "bugfix"}:
        return "fix"
    return "feat"


def _pr_title_for_ticket(
    *,
    epic: str | None,
    refs: list[str],
    ticket_type: str | None = None,
    title: str | None = None,
    kind: str = "ticket",
) -> str:
    commit_type = _commit_type_for_ticket(ticket_type, kind=kind)
    epic_slug = epic or "build"
    if kind == "retrospective":
        desc = "retrospective"
    else:
        raw = (title or "").strip()
        if raw:
            desc = raw[0].lower() + raw[1:]
        else:
            desc = f"orchestrated build for {', '.join(refs)}"
    prefix = f"{commit_type}({epic_slug}): "
    budget = 72 - len(prefix)
    if budget < 1:
        return f"{commit_type}({epic_slug})"[:72]
    if len(desc) > budget:
        desc = desc[: max(budget - 1, 0)].rstrip() + "…"
    return prefix + desc


def _tracker_display(store: str, tracker_id: str | None) -> str | None:
    tid = (tracker_id or "").strip()
    if not tid:
        return None
    if store == "github":
        return f"#{tid.lstrip('#')}"
    return tid


def _plan_body_text(plan_path: Path) -> str:
    text = plan_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4 :]
    return text


def _extract_problem_approach(text: str) -> str | None:
    contract = re.search(
        r"<intent-contract>(.*?)</intent-contract>",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    block = contract.group(1) if contract else text
    problem = re.search(
        r"\*\*Problem:\*\*\s*(.+?)(?=\n\s*\*\*[A-Z]|\n\n|\Z)", block, flags=re.DOTALL
    )
    approach = re.search(
        r"\*\*Approach:\*\*\s*(.+?)(?=\n\s*\*\*[A-Z]|\n\n|\Z)", block, flags=re.DOTALL
    )
    parts: list[str] = []
    if problem:
        parts.append(f"**Problem:** {problem.group(1).strip()}")
    if approach:
        parts.append(f"**Approach:** {approach.group(1).strip()}")
    return "\n\n".join(parts) if parts else None


def _extract_auto_run_summary(text: str) -> str | None:
    section = re.search(
        r"^## Auto Run Result\s*\n(.*?)(?=^## |\Z)",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    if not section:
        return None
    body = section.group(1)
    summary = re.search(r"-\s*\*\*Summary:\*\*\s*(.+)", body)
    if summary:
        return summary.group(1).strip()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return None


def _extract_plan_excerpt(plan_path: Path | None) -> str:
    if not plan_path or not plan_path.is_file():
        return ""
    text = _plan_body_text(plan_path)
    excerpt = _extract_problem_approach(text)
    if not excerpt:
        excerpt = _extract_auto_run_summary(text)
    if not excerpt:
        fm = read_frontmatter(plan_path)
        bits: list[str] = []
        title = str(fm.get("title") or "").strip()
        if title:
            bits.append(title)
        for para in re.split(r"\n\s*\n", text):
            cleaned = para.strip()
            if not cleaned or cleaned.startswith("#") or cleaned.startswith("<"):
                continue
            bits.append(cleaned)
            if len(bits) >= 3:
                break
        excerpt = "\n\n".join(bits)
    if len(excerpt) > _PR_EXCERPT_CAP:
        excerpt = excerpt[: _PR_EXCERPT_CAP - 1].rstrip() + "…"
    return excerpt


def _extract_verification_checks(plan_path: Path | None) -> list[str]:
    if not plan_path or not plan_path.is_file():
        return []
    text = _plan_body_text(plan_path)
    section = re.search(
        r"^## Verification\s*\n(.*?)(?=^## |\Z)", text, flags=re.DOTALL | re.MULTILINE
    )
    if not section:
        return []
    checks: list[str] = []
    for line in section.group(1).splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^[-*]\s+", "", cleaned)
        cleaned = re.sub(r"^\*\*[^*]+\*\*:?\s*", "", cleaned)
        if not cleaned:
            continue
        if len(cleaned) > 120:
            cleaned = cleaned[:119] + "…"
        checks.append(cleaned)
        if len(checks) >= 5:
            break
    return checks


def _pr_body_for_ticket(
    *,
    project_root: Path,
    ref: str,
    title: str | None = None,
    tracker_id: str | None = None,
    plan_path: Path | None = None,
    kind: str = "ticket",
) -> str:
    if kind == "retrospective":
        return "\n".join(
            [
                "## Summary",
                f"- Retrospective for `{ref}`",
                "",
                "## Test plan",
                "- [ ] Review retrospective output",
                "- [ ] Confirm CI on this PR",
            ]
        )
    cfg = load_store_config(project_root)
    store = str(_tickets_table(cfg).get("store") or "repo")
    tracker = _tracker_display(store, tracker_id)
    lines = [
        "## Summary",
        f"- Ticket: `{ref}`",
    ]
    if tracker:
        lines.append(f"- Tracker: {tracker}")
    if title:
        lines.append(f"- Title: {title}")
    excerpt = _extract_plan_excerpt(plan_path)
    if excerpt:
        lines.extend(["", "## Plan excerpt", excerpt])
    lines.extend(
        [
            "",
            "## Test plan",
            "- [ ] Review agent-produced commits and plan status",
            "- [ ] Confirm CI on this PR",
        ]
    )
    for check in _extract_verification_checks(plan_path):
        lines.append(f"- [ ] {check}")
    return "\n".join(lines)


def _is_merge_not_ready(err: str) -> bool:
    lower = err.lower()
    needles = (
        "required status check",
        "required checks",
        "checks pending",
        "not mergeable",
        "merge is blocked",
        "blocked by",
        "review required",
        "status check",
        "waiting on",
        "must be up to date",
    )
    return any(n in lower for n in needles)


def _wait_for_pr_merged(project_root: Path, *, url: str | None) -> None:
    deadline = time.monotonic() + MERGE_TIMEOUT_S
    while time.monotonic() < deadline:
        info = _gh_pr_view(project_root, "state,url")
        if info and str(info.get("state") or "").upper() == "MERGED":
            log.info("PR merged after wait url=%s", info.get("url") or url)
            return
        log.info(
            "waiting for PR merge url=%s remaining≈%ss",
            url,
            max(0, int(deadline - time.monotonic())),
        )
        time.sleep(MERGE_POLL_INTERVAL_S)
    raise OrchestratorHalt(
        SHUTDOWN_ERROR,
        f"timed out waiting for PR merge after {MERGE_TIMEOUT_S}s url={url}",
    )


def merge_pr(project_root: Path, *, subject: str) -> None:
    info = _gh_pr_view(project_root, "url,title,state,mergeable")
    if info is None:
        raise OrchestratorHalt(SHUTDOWN_ERROR, "no PR found to merge")
    state = str(info.get("state") or "").upper()
    url = info.get("url")
    if state == "MERGED":
        log.info("PR already merged url=%s", url)
        return
    mergeable = str(info.get("mergeable") or "").upper()
    if mergeable == "CONFLICTING":
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"PR has merge conflicts url={url}")
    log.info("gh pr merge --squash --delete-branch subject=%s url=%s", subject, url)
    merge = subprocess.run(
        [
            "gh",
            "pr",
            "merge",
            "--squash",
            "--delete-branch",
            "--subject",
            subject,
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if merge.returncode == 0:
        log.info("merged PR url=%s", url)
        return
    err = merge.stderr.strip() or merge.stdout.strip() or "gh pr merge failed"
    if not _is_merge_not_ready(err):
        raise OrchestratorHalt(SHUTDOWN_ERROR, err)
    log.info("enabling auto-merge for PR url=%s reason=%s", url, err)
    auto = subprocess.run(
        [
            "gh",
            "pr",
            "merge",
            "--auto",
            "--squash",
            "--delete-branch",
            "--subject",
            subject,
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if auto.returncode != 0:
        auto_err = (
            auto.stderr.strip() or auto.stdout.strip() or "gh pr merge --auto failed"
        )
        if "already enabled" not in auto_err.lower():
            raise OrchestratorHalt(SHUTDOWN_ERROR, auto_err)
    _wait_for_pr_merged(project_root, url=str(url) if url else None)


def return_to_main(project_root: Path, feature_branch: str) -> None:
    default = default_branch(project_root)
    current = current_branch(project_root)
    log.info(
        "return to default=%s from feature_branch=%s current=%s",
        default,
        feature_branch,
        current,
    )
    if current != default:
        run_git(project_root, "checkout", default)
    pull = run_git(project_root, "pull", "--ff-only", check=False)
    if pull.returncode != 0:
        run_git(project_root, "pull")
    if not feature_branch or feature_branch in PROTECTED_BRANCHES:
        return
    if feature_branch == default:
        return
    exists = run_git(project_root, "rev-parse", "--verify", feature_branch, check=False)
    if exists.returncode != 0:
        return
    delete = run_git(project_root, "branch", "-d", feature_branch, check=False)
    if delete.returncode != 0:
        # Squash merges often leave the local branch "not fully merged".
        log.info("force-delete local branch after squash=%s", feature_branch)
        run_git(project_root, "branch", "-D", feature_branch)


def ensure_push_and_pr(
    project_root: Path,
    *,
    epic: str | None,
    refs: list[str],
    no_push: bool,
    dry_run: bool,
    ticket_type: str | None = None,
    title: str | None = None,
    tracker_id: str | None = None,
    plan_path: Path | None = None,
    kind: str = "ticket",
) -> str | None:
    if dry_run or no_push:
        log.info(
            "skip push/PR/merge dry_run=%s no_push=%s refs=%s", dry_run, no_push, refs
        )
        return None
    branch = current_branch(project_root)
    if branch in PROTECTED_BRANCHES:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"refusing to push protected branch {branch}"
        )
    ahead = commits_ahead_of_default(project_root)
    if ahead < 1:
        log.info(
            "skip push/PR: no commits ahead of default branch=%s refs=%s",
            default_branch(project_root),
            refs,
        )
        return None
    log.info("git push -u origin HEAD branch=%s", branch)
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

    view = _gh_pr_view(project_root, "url,title")
    if view and view.get("url"):
        url = view.get("url")
        log.info("existing PR url=%s", url)
        return str(url) if url else None

    pr_title = _pr_title_for_ticket(
        epic=epic,
        refs=refs,
        ticket_type=ticket_type,
        title=title,
        kind=kind,
    )
    base = default_branch(project_root)
    body = _pr_body_for_ticket(
        project_root=project_root,
        ref=refs[0] if refs else (epic or "unknown"),
        title=title,
        tracker_id=tracker_id,
        plan_path=plan_path,
        kind=kind,
    )
    log.info("gh pr create title=%s base=%s", pr_title, base)
    create = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--title",
            pr_title,
            "--body",
            body,
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if create.returncode != 0:
        # Race: PR may exist now
        view2 = _gh_pr_view(project_root, "url")
        if view2 and view2.get("url"):
            url = view2.get("url")
            log.info("PR appeared after create race url=%s", url)
            return str(url) if url else None
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            create.stderr.strip() or create.stdout.strip() or "gh pr create failed",
        )
    url_lines = (create.stdout or "").strip().splitlines()
    url = url_lines[-1] if url_lines else None
    log.info("created PR url=%s", url)
    return url


def ensure_push_pr_and_merge(
    project_root: Path,
    *,
    epic: str | None,
    refs: list[str],
    no_push: bool,
    dry_run: bool,
    ticket_type: str | None = None,
    title: str | None = None,
    tracker_id: str | None = None,
    plan_path: Path | None = None,
    kind: str = "ticket",
) -> str | None:
    """Push, ensure PR, squash-merge with conventional subject, return to default."""
    if dry_run or no_push:
        log.info(
            "skip push/PR/merge dry_run=%s no_push=%s refs=%s", dry_run, no_push, refs
        )
        return None
    feature_branch = current_branch(project_root)
    url = ensure_push_and_pr(
        project_root,
        epic=epic,
        refs=refs,
        no_push=False,
        dry_run=False,
        ticket_type=ticket_type,
        title=title,
        tracker_id=tracker_id,
        plan_path=plan_path,
        kind=kind,
    )
    if url is None:
        # No commits ahead of default (or push/PR skipped); do not merge.
        return None
    info = _gh_pr_view(project_root, "url,title")
    subject = str((info or {}).get("title") or "").strip() or _pr_title_for_ticket(
        epic=epic,
        refs=refs,
        ticket_type=ticket_type,
        title=title,
        kind=kind,
    )
    if info and info.get("url"):
        url = str(info["url"])
    merge_pr(project_root, subject=subject)
    return_to_main(project_root, feature_branch)
    return url
