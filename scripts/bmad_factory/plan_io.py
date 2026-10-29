"""Plan frontmatter, result artifacts, deferred ledger append."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

from .constants import SHUTDOWN_ERROR, FactoryHalt, log

_OUTPUT_DIRNAME = "_bmad-output"
_BMAD_CONFIG_LAYERS = (
    Path("_bmad/config.toml"),
    Path("_bmad/custom/config.toml"),
    Path("_bmad/custom/config.user.toml"),
)

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)


def load_frontmatter_data(block: str, *, path: Path) -> Any:
    try:
        return yaml.safe_load(block)
    except yaml.YAMLError as err:
        raise FactoryHalt(
            SHUTDOWN_ERROR, f"invalid YAML frontmatter in {path}: {err}"
        ) from err


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
    data = load_frontmatter_data(block, path=path) or {}
    return data if isinstance(data, dict) else {}


def set_frontmatter_value(text: str, key: str, value: str) -> str:
    """Set or remove one frontmatter key without rewriting other lines.

    Empty ``value`` removes the key. Matches tickets.py: only the ``key:`` line
    changes, so inline lists and multi-line values for other keys stay intact.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise FactoryHalt(SHUTDOWN_ERROR, "ticket has no frontmatter")
    block = m.group(1)
    pattern = re.compile(rf"^{re.escape(key)}:.*$\n?", re.MULTILINE)
    if value == "":
        block = pattern.sub("", block).rstrip("\n")
    elif pattern.search(block):
        block = pattern.sub(lambda _: f"{key}: {value}\n", block, count=1).rstrip("\n")
    else:
        block = f"{block}\n{key}: {value}"
    return text[: m.start(1)] + block + text[m.end(1) :]


def update_frontmatter_fields(path: Path, updates: dict[str, Any]) -> None:
    """Surgically set frontmatter keys (string values; ``None`` removes)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise FactoryHalt(SHUTDOWN_ERROR, f"no frontmatter: {path}")
    end = text.find("\n---", 3)
    if end < 0:
        raise FactoryHalt(SHUTDOWN_ERROR, f"frontmatter not closed: {path}")
    for key, value in updates.items():
        if value is None:
            text = set_frontmatter_value(text, key, "")
        else:
            text = set_frontmatter_value(text, key, str(value))
    path.write_text(text, encoding="utf-8")


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


def format_halt_reinvoke_steps(
    *,
    detail: str,
    cli_args: str,
    model: str,
    run_id: str | None = None,
) -> str:
    resume_bit = (
        f"   or: uv run scripts/bmad_factory.py --resume {run_id} --verbose "
        f"--model={model}"
        if run_id
        else None
    )
    stop_bit = (
        f"   if a live run is stuck: uv run scripts/bmad_factory.py --stop {run_id}"
        if run_id
        else None
    )
    lines = [
        "Next steps:",
        f"1. {detail}",
        "2. Act on the gate (refine / approve plan / remediate rejected epic / "
        "fix blocked), then re-invoke:",
        f"   uv run scripts/bmad_factory.py --verbose --model={model} {cli_args}",
    ]
    if resume_bit:
        lines.append(resume_bit)
    lines.append(
        "   (use -y to ack plan-checkpoint, or to force-ack an epic-boundary "
        "after a refused retrospective when you intentionally proceed)"
    )
    if stop_bit:
        lines.append(stop_bit)
    return "\n".join(lines)


def set_plan_status(path: Path, status: str) -> None:
    if not path.is_file():
        raise FactoryHalt(SHUTDOWN_ERROR, f"plan has no frontmatter: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise FactoryHalt(SHUTDOWN_ERROR, f"plan has no frontmatter: {path}")
    if text.find("\n---", 3) < 0:
        raise FactoryHalt(SHUTDOWN_ERROR, f"plan frontmatter not closed: {path}")
    update_frontmatter_fields(path, {"status": status})


def _merge_toml(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_toml(out[key], value)
        else:
            out[key] = value
    return out


def _active_initiative_name(project_root: Path) -> str | None:
    """Return ``core.active_initiative`` from merged BMad config layers, if set."""
    merged: dict[str, Any] = {}
    for rel in _BMAD_CONFIG_LAYERS:
        path = project_root / rel
        if not path.is_file():
            continue
        try:
            layer = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if isinstance(layer, dict):
            merged = _merge_toml(merged, layer)
    core = merged.get("core")
    if not isinstance(core, dict):
        return None
    name = core.get("active_initiative")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def initiative_dir_for(plan_path: Path, project_root: Path) -> Path:
    root = project_root.resolve()
    plan = plan_path.resolve()
    for parent in [plan.parent, *plan.parents]:
        if parent == root or root not in parent.parents:
            break
        if (parent / "deferred-work.md").is_file():
            return parent
        if (parent / "tickets").is_dir() and (
            (parent / f"{parent.name}.md").is_file()
            or parent.name.startswith("initiative")
        ):
            return parent
    for parent in plan.parents:
        if parent.name.startswith("initiative") and (parent / "tickets").is_dir():
            return parent
    # Top-level backlog / output-root plans: BMAD puts deferred under
    # {output}/{active_initiative}/, else {output}/.
    output = root / _OUTPUT_DIRNAME
    try:
        plan.relative_to(output)
    except ValueError as err:
        raise FactoryHalt(
            SHUTDOWN_ERROR, f"cannot locate initiative for plan {plan_path}"
        ) from err
    active = _active_initiative_name(root)
    if active:
        cand = output / active
        if cand.is_dir():
            return cand
    return output


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
