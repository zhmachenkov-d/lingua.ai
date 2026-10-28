"""Git helpers and PR remote landing (inplace only — no worktrees)."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .constants import (
    BRANCH_PREFIX,
    BRANCH_SLUG_RE,
    MERGE_POLL_INTERVAL_S,
    MERGE_TIMEOUT_S,
    PROTECTED_BRANCHES,
    SHUTDOWN_DIRTY_TREE,
    SHUTDOWN_ERROR,
    FactoryHalt,
    log,
)
from .plan_io import read_frontmatter


def run_git(
    project_root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args], cwd=project_root, capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise FactoryHalt(
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
        raise FactoryHalt(SHUTDOWN_DIRTY_TREE, "working tree is not clean")


def current_branch(project_root: Path) -> str:
    return run_git(project_root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def default_branch(project_root: Path) -> str:
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
    base = default_branch(project_root)
    for tip in (f"origin/{base}", base):
        check = run_git(project_root, "rev-parse", "--verify", tip, check=False)
        if check.returncode == 0:
            return tip
    return None


def commits_ahead_of_default(project_root: Path) -> int:
    tip = default_branch_tip(project_root)
    if tip is None:
        return 0
    proc = run_git(project_root, "rev-list", "--count", f"{tip}..HEAD")
    try:
        return int(proc.stdout.strip() or "0")
    except ValueError:
        return 0


def has_unpushed_or_new_commits(project_root: Path) -> bool:
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
    """Ensure a non-protected work branch ``factory/<ref>`` from an up-to-date default."""
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
    name = f"{BRANCH_PREFIX}/{sanitize_branch_slug(ref)}"
    exists = run_git(project_root, "rev-parse", "--verify", name, check=False)
    if exists.returncode == 0:
        log.info("checkout existing work branch=%s", name)
        run_git(project_root, "checkout", name)
    else:
        log.info("create work branch=%s from=%s", name, default)
        run_git(project_root, "checkout", "-b", name)
    return name


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
    if kind == "bundle":
        return "chore"
    t = (ticket_type or "").strip().lower()
    if t in {"bug", "bugfix"}:
        return "fix"
    return "feat"


def pr_title_for_ticket(
    *,
    epic: str | None,
    refs: list[str],
    ticket_type: str | None = None,
    title: str | None = None,
    kind: str = "ticket",
) -> str:
    commit_type = _commit_type_for_ticket(ticket_type, kind=kind)
    epic_slug = epic or "build"
    if kind == "bundle":
        desc = (title or "deferred bundle").strip()
        desc = desc[0].lower() + desc[1:] if desc else "deferred bundle"
    else:
        raw = (title or "").strip()
        if raw:
            desc = raw[0].lower() + raw[1:]
        else:
            desc = f"factory build for {', '.join(refs)}"
    prefix = f"{commit_type}({epic_slug}): "
    budget = 72 - len(prefix)
    if budget < 1:
        return f"{commit_type}({epic_slug})"[:72]
    if len(desc) > budget:
        desc = desc[: max(budget - 1, 0)].rstrip() + "…"
    return prefix + desc


def _plan_body_text(plan_path: Path) -> str:
    text = plan_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4 :]
    return text


def _extract_plan_excerpt(plan_path: Path | None) -> str:
    if not plan_path or not plan_path.is_file():
        return ""
    text = _plan_body_text(plan_path)
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
    excerpt = "\n\n".join(parts)
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


def _pr_body_for_ticket(
    *,
    ref: str,
    title: str | None = None,
    tracker_id: str | None = None,
    plan_path: Path | None = None,
    kind: str = "ticket",
) -> str:
    if kind == "bundle":
        return "\n".join(
            [
                "## Summary",
                f"- Deferred bundle: `{ref}`",
                f"- Intent: {title or '(none)'}",
                "",
                "## Test plan",
                "- [ ] Review agent-produced commits",
                "- [ ] Confirm CI on this PR",
            ]
        )
    lines = [
        "## Summary",
        f"- Ticket: `{ref}`",
    ]
    if tracker_id:
        lines.append(f"- Tracker: #{str(tracker_id).lstrip('#')}")
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
    raise FactoryHalt(
        SHUTDOWN_ERROR,
        f"timed out waiting for PR merge after {MERGE_TIMEOUT_S}s url={url}",
    )


def merge_pr(project_root: Path, *, subject: str) -> None:
    info = _gh_pr_view(project_root, "url,title,state,mergeable")
    if info is None:
        raise FactoryHalt(SHUTDOWN_ERROR, "no PR found to merge")
    state = str(info.get("state") or "").upper()
    url = info.get("url")
    if state == "MERGED":
        log.info("PR already merged url=%s", url)
        return
    mergeable = str(info.get("mergeable") or "").upper()
    if mergeable == "CONFLICTING":
        raise FactoryHalt(SHUTDOWN_ERROR, f"PR has merge conflicts url={url}")
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
        raise FactoryHalt(SHUTDOWN_ERROR, err)
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
            raise FactoryHalt(SHUTDOWN_ERROR, auto_err)
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
        raise FactoryHalt(SHUTDOWN_ERROR, f"refusing to push protected branch {branch}")
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
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            push.stderr.strip() or push.stdout.strip() or "git push failed",
        )

    view = _gh_pr_view(project_root, "url,title")
    if view and view.get("url"):
        url = view.get("url")
        log.info("existing PR url=%s", url)
        return str(url) if url else None

    pr_title = pr_title_for_ticket(
        epic=epic,
        refs=refs,
        ticket_type=ticket_type,
        title=title,
        kind=kind,
    )
    base = default_branch(project_root)
    body = _pr_body_for_ticket(
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
        view2 = _gh_pr_view(project_root, "url")
        if view2 and view2.get("url"):
            url = view2.get("url")
            log.info("PR appeared after create race url=%s", url)
            return str(url) if url else None
        raise FactoryHalt(
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
        return None
    info = _gh_pr_view(project_root, "url,title")
    subject = str((info or {}).get("title") or "").strip() or pr_title_for_ticket(
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
