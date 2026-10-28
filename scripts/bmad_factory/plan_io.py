"""Plan frontmatter, result artifacts, deferred ledger append."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .constants import SHUTDOWN_ERROR, FactoryHalt, log


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


def ticket_slug_from_ref(ref: str) -> str:
    name = Path(str(ref)).name
    if name.endswith(".md"):
        return name[:-3]
    return name


def find_build_auto_result(project_root: Path, slug: str) -> Path | None:
    output = project_root / "_bmad-output"
    if not output.is_dir():
        return None
    matches = sorted(output.rglob(f"bmad-build-auto-result-{slug}.md"))
    return matches[0] if matches else None


def blocked_reason_from_artifact(path: Path | None, fm: dict[str, Any]) -> str:
    reason = str(fm.get("blocked_reason") or "").strip()
    if reason:
        return reason
    if path is None or not path.is_file():
        return "blocked"
    for line in path.read_text(encoding="utf-8").splitlines():
        lower = line.lower().strip()
        if lower.startswith("blocking condition:"):
            value = line.split(":", 1)[1].strip()
            return value or "blocked"
        if lower.startswith("- **blocking condition:**") or lower.startswith(
            "- **blocking condition**:"
        ):
            value = line.split(":", 1)[1].strip().strip("*").strip()
            return value or "blocked"
    return "blocked"


def _fix_cause_guidance(reason: str) -> str:
    lowered = reason.lower()
    if "intent gap" in lowered or "unclear intent" in lowered:
        return (
            "Pin the open choice in the ticket Notes, plan intent, and/or tracker "
            "issue comment (do not leave A vs B unresolved)."
        )
    if "dirty" in lowered or "version-control" in lowered:
        return "Clean the working tree (commit or stash) and ensure the branch fits the ticket."
    if "verification" in lowered:
        return (
            "Fix the failing verification command/check recorded under Auto Run Result."
        )
    if "no subagents" in lowered:
        return "Re-run in an environment where subagents are available."
    if "ticket not resolved" in lowered:
        return "Fix the ticket ref so `tickets.py find` resolves it."
    return "Resolve the blocking condition recorded in the artifact, then clear blocked status."


def format_blocked_redispatch_steps(
    *,
    ticket_ref: str,
    reason: str,
    artifact_path: Path | None,
    plan_path: Path | None,
    status_from_result_only: bool,
    model: str,
    cli_args: str,
) -> str:
    artifact = str(artifact_path) if artifact_path else "(none)"
    plan = (
        str(plan_path) if plan_path else "(unknown — from `tickets.py find` plan path)"
    )
    if status_from_result_only:
        clear_lines = [
            "3. Clear blocked so a later dispatch will run:",
            f"   - Create or update the plan at {plan}",
            "     with frontmatter `status: ready-for-dev` (or `in-progress` / `in-review`",
            "     as appropriate) and no `blocked_at` / `blocked_reason`.",
            f"   - After pinning intent, remove or ignore the stale result file at {artifact}.",
        ]
    else:
        clear_lines = [
            "3. Clear blocked so a later dispatch will run:",
            f"   - Edit plan frontmatter at {plan}: set `status` to the resume value",
            "     (`ready-for-dev`, `in-progress`, or `in-review`), and clear `blocked_at`",
            "     / `blocked_reason`.",
        ]
    lines = [
        "Next steps to re-dispatch:",
        f"1. What blocked it: ticket {ticket_ref}",
        f"   reason: {reason}",
        f"   artifact: {artifact}",
        f"2. Fix the cause: {_fix_cause_guidance(reason)}",
        *clear_lines,
        "4. Re-invoke the same factory command:",
        f"   uv run scripts/bmad_factory.py --verbose --model={model} {cli_args}",
    ]
    return "\n".join(lines)


def format_halt_reinvoke_steps(*, detail: str, cli_args: str, model: str) -> str:
    return "\n".join(
        [
            "Next steps:",
            f"1. {detail}",
            "2. Act on the gate (refine / approve / close epic / fix blocked), then re-invoke:",
            f"   uv run scripts/bmad_factory.py --verbose --model={model} {cli_args}",
            "   (use -y to ack plan-checkpoint / epic-closure when appropriate)",
        ]
    )


def set_plan_status(path: Path, status: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise FactoryHalt(SHUTDOWN_ERROR, f"plan has no frontmatter: {path}")
    end = text.find("\n---", 3)
    if end < 0:
        raise FactoryHalt(SHUTDOWN_ERROR, f"plan frontmatter not closed: {path}")
    block = text[3:end].strip("\n")
    data = yaml.safe_load(block) or {}
    if not isinstance(data, dict):
        raise FactoryHalt(SHUTDOWN_ERROR, f"plan frontmatter is not a mapping: {path}")
    data["status"] = status
    new_block = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip()
    path.write_text(f"---\n{new_block}\n---{text[end + 4 :]}", encoding="utf-8")


def initiative_dir_for(plan_path: Path, project_root: Path) -> Path:
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
    raise FactoryHalt(SHUTDOWN_ERROR, f"cannot locate initiative for plan {plan_path}")


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
    log.info("harvested %s deferred item(s) → %s", len(lines), dest)
    return len(lines)
