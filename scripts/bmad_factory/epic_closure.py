"""Epic-boundary retrospective: run headless retro, close epic, materialize backlog tickets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .agent import agent_call_limits, run_cursor_agent, usage_dict
from .constants import SHUTDOWN_ERROR, FactoryHalt, log
from .pick import CLOSURE_REJECTED, EPIC_CLOSED
from .plan_io import read_frontmatter
from .policy import Policy
from .report import RunReport, UnitReport, log_cumulative_tokens
from .run_state import RunState, append_journal, save_run
from .tickets_io import _github_mark_done, _load_store_config

ACCEPT_VERDICTS = frozenset({"accepted", "accepted-with-open-items"})
TICKETABLE_DISPOSITIONS = frozenset({"fix-now", "defer"})
SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class ActionItem:
    id: str
    kind: str
    disposition: str
    title: str
    owner: str = ""
    summary: str = ""


@dataclass
class EpicClosureResult:
    closed: bool
    verdict: str | None
    closure: str | None
    detail: str
    retro_path: Path | None = None
    epic_path: Path | None = None
    created_tickets: list[str] = field(default_factory=list)
    skipped_tickets: list[str] = field(default_factory=list)
    materialize_errors: list[str] = field(default_factory=list)


def build_retro_prompt(epic_slug: str) -> str:
    return (
        f"Run skill bmad-retrospective -H {epic_slug}. "
        "Do not start any other ticket or skill."
    )


def normalize_epic_slug(slug: str) -> str:
    s = str(slug or "").strip()
    if not s:
        return s
    return s if s.startswith("epic-") else f"epic-{s}"


def find_epic_paths(project_root: Path, slug: str) -> tuple[Path | None, Path | None]:
    folder_name = normalize_epic_slug(slug)
    output = project_root / "_bmad-output"
    if not output.is_dir():
        return None, None
    epic_md: Path | None = None
    for path in sorted(output.rglob(f"{folder_name}.md")):
        if path.parent.name == folder_name and path.name == f"{folder_name}.md":
            epic_md = path
            break
    if epic_md is None:
        return None, None
    retro = epic_md.parent / f"{folder_name}-retrospective.md"
    return epic_md, retro if retro.is_file() else epic_md.parent / f"{folder_name}-retrospective.md"


def find_backlog_dir(project_root: Path) -> Path | None:
    output = project_root / "_bmad-output"
    candidate = output / "backlog"
    if candidate.is_dir():
        return candidate
    return None


def parse_action_items(fm: dict[str, Any]) -> list[ActionItem]:
    raw = fm.get("action_items")
    if not isinstance(raw, list):
        return []
    out: list[ActionItem] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        aid = str(item.get("id") or f"item-{i + 1}").strip()
        out.append(
            ActionItem(
                id=aid,
                kind=str(item.get("kind") or "remediation").strip().lower(),
                disposition=str(item.get("disposition") or "").strip().lower(),
                title=str(item.get("title") or aid).strip(),
                owner=str(item.get("owner") or "").strip(),
                summary=str(item.get("summary") or "").strip(),
            )
        )
    return out


def parse_retro_contract(retro_md: Path) -> tuple[str | None, str | None, list[ActionItem]]:
    fm = read_frontmatter(retro_md)
    verdict = str(fm.get("verdict") or "").strip().lower() or None
    closure = str(fm.get("closure") or "").strip().lower() or None
    if closure not in {"recommended", "refused", None}:
        closure = None
    if closure is None and verdict:
        closure = "recommended" if verdict in ACCEPT_VERDICTS else "refused"
    return verdict, closure, parse_action_items(fm)


def extract_section(text: str, heading: str) -> str:
    """Return markdown body under ``## {heading}`` until the next ``##``."""
    pattern = re.compile(
        rf"^##[ \t]+{re.escape(heading)}[ \t]*\n(.*?)(?=^##[ \t]+|\Z)",
        re.M | re.S,
    )
    m = pattern.search(text)
    if not m:
        return ""
    return m.group(1).strip()


def extract_acceptance_detail(retro_md: Path) -> str:
    if not retro_md.is_file():
        return f"(retrospective file missing: {retro_md})"
    text = retro_md.read_text(encoding="utf-8")
    parts: list[str] = []
    acceptance = extract_section(text, "Acceptance verdict")
    if acceptance:
        parts.append("Acceptance verdict:\n" + acceptance)
    assumptions = extract_section(text, "Assumptions")
    if assumptions:
        parts.append("Assumptions:\n" + assumptions)
    if not parts:
        fm = read_frontmatter(retro_md)
        parts.append(
            f"verdict={fm.get('verdict')!r} closure={fm.get('closure')!r} "
            f"(no Acceptance verdict section)"
        )
    return "\n\n".join(parts)


def _title_slug(title: str) -> str:
    slug = SLUG_RE.sub("-", title.lower()).strip("-")[:60].rstrip("-")
    return slug or "untitled"


def retro_marker(epic_slug: str, action_id: str) -> str:
    return f"retro:{normalize_epic_slug(epic_slug)}:{action_id}"


def backlog_has_marker(backlog_dir: Path, marker: str) -> bool:
    needle = marker.lower()
    for path in backlog_dir.glob("*.md"):
        if path.name.endswith("-plan.md"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if needle in text.lower():
            return True
    return False


def update_frontmatter_fields(path: Path, updates: dict[str, Any]) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise FactoryHalt(SHUTDOWN_ERROR, f"no frontmatter: {path}")
    end = text.find("\n---", 3)
    if end < 0:
        raise FactoryHalt(SHUTDOWN_ERROR, f"frontmatter not closed: {path}")
    block = text[3:end].strip("\n")
    data = yaml.safe_load(block) or {}
    if not isinstance(data, dict):
        raise FactoryHalt(SHUTDOWN_ERROR, f"frontmatter is not a mapping: {path}")
    for key, value in updates.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    new_block = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip()
    path.write_text(f"---\n{new_block}\n---{text[end + 4 :]}", encoding="utf-8")


def close_epic_container(
    project_root: Path,
    epic_md: Path,
    *,
    policy: Policy | None = None,
) -> None:
    del policy  # reserved for future tickets-script close
    fm = read_frontmatter(epic_md)
    tracker_id = str(fm.get("tracker_id") or "").strip()
    updates: dict[str, Any] = {"status": "done"}
    cfg = _load_store_config(project_root)
    tickets = cfg.get("tickets") if isinstance(cfg.get("tickets"), dict) else {}
    store = str((tickets or {}).get("store") or "repo")
    if store == "github" and tracker_id:
        _github_mark_done(project_root, tracker_id, cfg)
        updates["tracker_status"] = "done"
    elif tracker_id:
        updates["tracker_status"] = "done"
    update_frontmatter_fields(epic_md, updates)
    log.info("closed epic file=%s store=%s tracker_id=%s", epic_md, store, tracker_id or "(none)")


def _bug_leaf_body(
    *,
    title: str,
    summary: str,
    marker: str,
    kind: str,
    owner: str,
    retro_rel: str,
    refine: bool,
) -> str:
    notes = [
        f"{marker}",
        f"From retrospective {retro_rel} ({kind}).",
    ]
    if owner:
        notes.append(f"Owner: {owner}")
    if refine:
        notes.append(
            "Spec reconciliation: Sofia must apply the reconciliation to the "
            "named source ticket; do not treat this leaf as the edit itself."
        )
    notes_block = "\n".join(f"- {n}" for n in notes)
    desc = summary or title
    title_yaml = yaml.safe_dump(title, allow_unicode=True).strip()
    refine_line = "refine: true\n" if refine else ""
    return (
        f"---\n"
        f"type: bug\n"
        f"title: {title_yaml}\n"
        f"parent: none\n"
        f"covers: []\n"
        f"after: []\n"
        f"refined: false\n"
        f"{refine_line}"
        f"hitl: false\n"
        f"risk: medium\n"
        f"severity: P2\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"## Description\n\n"
        f"{desc}\n\n"
        f"## Reproduction\n\n"
        f"See retrospective action item evidence.\n\n"
        f"**Actual:** defect or gap as described above.\n"
        f"**Expected:** behavior after the remediation lands.\n\n"
        f"## Cause Hypothesis\n\n"
        f"Recorded in the retrospective action item summary.\n\n"
        f"## Acceptance Criteria\n\n"
        f"1. **Expected behavior holds**\n"
        f"   **Given** the conditions in the retrospective summary\n"
        f"   **When** the remediation is applied\n"
        f"   **Then** the gap described no longer reproduces\n"
        f"2. **Tests cover the condition**\n"
        f"   **Given** the relevant test suite\n"
        f"   **When** it runs\n"
        f"   **Then** coverage exists for the fixed condition where applicable\n"
        f"3. **Or: no change is needed, with proof**\n"
        f"   **Given** the reproduction\n"
        f"   **When** it is run on the current code\n"
        f"   **Then** expected behavior already holds, with evidence in Notes "
        f"— this supersedes 1 and 2\n\n"
        f"## References\n\n"
        f"- retrospective — {retro_rel}\n\n"
        f"## Notes\n\n"
        f"{notes_block}\n"
    )


def materialize_action_items(
    project_root: Path,
    *,
    epic_slug: str,
    retro_md: Path,
    action_items: list[ActionItem],
) -> tuple[list[str], list[str], list[str]]:
    """Create backlog leaves for ticketable action items.

    Returns (created paths, skipped ids, errors).
    """
    created: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    backlog = find_backlog_dir(project_root)
    if backlog is None:
        ticketable = [a for a in action_items if a.disposition in TICKETABLE_DISPOSITIONS]
        if ticketable:
            errors.append(
                f"no backlog/ under _bmad-output; cannot materialize "
                f"{len(ticketable)} action item(s)"
            )
        return created, skipped, errors

    try:
        retro_rel = str(retro_md.relative_to(project_root))
    except ValueError:
        retro_rel = str(retro_md)

    for item in action_items:
        if item.disposition == "accept-as-is":
            skipped.append(item.id)
            continue
        if item.disposition not in TICKETABLE_DISPOSITIONS:
            skipped.append(item.id)
            continue
        marker = retro_marker(epic_slug, item.id)
        if backlog_has_marker(backlog, marker):
            skipped.append(item.id)
            log.info("skip existing backlog marker=%s", marker)
            continue
        refine = item.kind == "spec-reconciliation"
        slug = _title_slug(item.title)
        path = backlog / f"bug-{slug}.md"
        n = 2
        while path.exists():
            path = backlog / f"bug-{slug}-{n}.md"
            n += 1
        try:
            body = _bug_leaf_body(
                title=item.title,
                summary=item.summary,
                marker=marker,
                kind=item.kind,
                owner=item.owner,
                retro_rel=retro_rel,
                refine=refine,
            )
            path.write_text(body, encoding="utf-8")
            try:
                created.append(str(path.relative_to(project_root)))
            except ValueError:
                created.append(str(path))
            log.info("materialized action item id=%s path=%s", item.id, path)
        except OSError as err:
            errors.append(f"{item.id}: {err}")
    return created, skipped, errors


def _refuse_detail(
    *,
    epic_slug: str,
    verdict: str | None,
    closure: str | None,
    retro_md: Path | None,
    reason: str,
) -> str:
    lines = [
        f"cannot close {normalize_epic_slug(epic_slug)}: {reason}",
        f"verdict={verdict!r} closure={closure!r}",
    ]
    if retro_md is not None:
        lines.append(f"retrospective: {retro_md}")
        lines.append(extract_acceptance_detail(retro_md))
    return "\n".join(lines)


def process_epic_closure(
    *,
    project_root: Path,
    epic_slug: str,
    report: RunReport,
    policy: Policy,
    run_state: RunState,
    model: str,
    dry_run: bool = False,
) -> EpicClosureResult:
    slug = normalize_epic_slug(epic_slug)
    epic_md, retro_md = find_epic_paths(project_root, slug)
    if epic_md is None:
        detail = f"cannot close {slug}: epic file not found under _bmad-output"
        unit = UnitReport(
            ref=slug,
            kind="retrospective",
            epic=slug,
            outcome="error",
            reason=detail,
        )
        report.add(unit)
        return EpicClosureResult(
            closed=False, verdict=None, closure=None, detail=detail
        )

    prior = run_state.ticket_epic_closures.get(slug)
    if prior == CLOSURE_REJECTED:
        detail = _refuse_detail(
            epic_slug=slug,
            verdict=prior,
            closure="refused",
            retro_md=retro_md if retro_md and retro_md.is_file() else None,
            reason="prior retrospective refused closure this run",
        )
        return EpicClosureResult(
            closed=False,
            verdict=prior,
            closure="refused",
            detail=detail,
            retro_path=retro_md if retro_md and retro_md.is_file() else None,
            epic_path=epic_md,
        )

    if prior in ACCEPT_VERDICTS:
        fm = read_frontmatter(epic_md)
        if str(fm.get("status") or "") not in EPIC_CLOSED:
            try:
                close_epic_container(project_root, epic_md, policy=policy)
            except FactoryHalt as err:
                detail = _refuse_detail(
                    epic_slug=slug,
                    verdict=prior,
                    closure="recommended",
                    retro_md=retro_md if retro_md and retro_md.is_file() else None,
                    reason=f"close retry failed: {err.detail or err}",
                )
                return EpicClosureResult(
                    closed=False,
                    verdict=prior,
                    closure="recommended",
                    detail=detail,
                    retro_path=retro_md if retro_md and retro_md.is_file() else None,
                    epic_path=epic_md,
                )
        created: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        if retro_md and retro_md.is_file():
            _, _, items = parse_retro_contract(retro_md)
            created, skipped, errors = materialize_action_items(
                project_root,
                epic_slug=slug,
                retro_md=retro_md,
                action_items=items,
            )
        detail = f"closed {slug} (reused verdict={prior})"
        if errors:
            detail += "; materialize warnings: " + "; ".join(errors)
        unit = UnitReport(
            ref=slug,
            kind="retrospective",
            epic=slug,
            outcome="closed",
            plan_status=prior,
            reason=detail if errors else None,
        )
        report.add(unit)
        return EpicClosureResult(
            closed=True,
            verdict=prior,
            closure="recommended",
            detail=detail,
            retro_path=retro_md if retro_md and retro_md.is_file() else None,
            epic_path=epic_md,
            created_tickets=created,
            skipped_tickets=skipped,
            materialize_errors=errors,
        )

    if dry_run:
        prompt = build_retro_prompt(slug)
        agent = run_cursor_agent(
            project_root=project_root,
            model=model,
            prompt=prompt,
            dry_run=True,
            **agent_call_limits(policy.limits),
        )
        unit = UnitReport(
            ref=slug,
            kind="retrospective",
            epic=slug,
            outcome="dry_run",
            tokens=usage_dict(agent.usage),
        )
        report.add(unit)
        return EpicClosureResult(
            closed=False,
            verdict=None,
            closure=None,
            detail=f"[dry-run] would run retrospective for {slug}",
            epic_path=epic_md,
            retro_path=retro_md,
        )

    log.info("epic closure start slug=%s", slug)
    append_journal(
        project_root,
        run_state.run_id,
        {"event": "epic_retrospective_start", "epic": slug},
    )
    agent = run_cursor_agent(
        project_root=project_root,
        model=model,
        prompt=build_retro_prompt(slug),
        dry_run=False,
        **agent_call_limits(policy.limits),
    )
    if agent.error:
        detail = _refuse_detail(
            epic_slug=slug,
            verdict=None,
            closure=None,
            retro_md=retro_md if retro_md and retro_md.is_file() else None,
            reason=f"retrospective agent failed: {agent.error}",
        )
        unit = UnitReport(
            ref=slug,
            kind="retrospective",
            epic=slug,
            outcome="error",
            reason=detail,
            tokens=usage_dict(agent.usage),
            agent_id=agent.agent_id,
            run_id=agent.run_id,
        )
        report.add(unit)
        log_cumulative_tokens(report)
        return EpicClosureResult(
            closed=False,
            verdict=None,
            closure=None,
            detail=detail,
            epic_path=epic_md,
            retro_path=retro_md if retro_md and retro_md.is_file() else None,
        )

    # Re-resolve after agent may have written the file.
    _, retro_md = find_epic_paths(project_root, slug)
    if retro_md is None or not retro_md.is_file():
        detail = _refuse_detail(
            epic_slug=slug,
            verdict=None,
            closure=None,
            retro_md=None,
            reason="retrospective file missing after agent run",
        )
        unit = UnitReport(
            ref=slug,
            kind="retrospective",
            epic=slug,
            outcome="error",
            reason=detail,
            tokens=usage_dict(agent.usage),
            agent_id=agent.agent_id,
            run_id=agent.run_id,
        )
        report.add(unit)
        log_cumulative_tokens(report)
        return EpicClosureResult(
            closed=False,
            verdict=None,
            closure=None,
            detail=detail,
            epic_path=epic_md,
        )

    verdict, closure, items = parse_retro_contract(retro_md)
    if verdict not in ACCEPT_VERDICTS or closure == "refused":
        reason = (
            "retrospective refused closure"
            if closure == "refused" or verdict == "rejected"
            else f"unusable verdict {verdict!r}"
        )
        detail = _refuse_detail(
            epic_slug=slug,
            verdict=verdict,
            closure=closure,
            retro_md=retro_md,
            reason=reason,
        )
        unit = UnitReport(
            ref=slug,
            kind="retrospective",
            epic=slug,
            outcome="rejected",
            plan_status=verdict,
            reason=detail,
            tokens=usage_dict(agent.usage),
            agent_id=agent.agent_id,
            run_id=agent.run_id,
        )
        report.add(unit)
        log_cumulative_tokens(report)
        return EpicClosureResult(
            closed=False,
            verdict=verdict or CLOSURE_REJECTED,
            closure=closure or "refused",
            detail=detail,
            retro_path=retro_md,
            epic_path=epic_md,
        )

    try:
        close_epic_container(project_root, epic_md, policy=policy)
    except FactoryHalt as err:
        detail = _refuse_detail(
            epic_slug=slug,
            verdict=verdict,
            closure=closure,
            retro_md=retro_md,
            reason=f"close failed: {err.detail or err}",
        )
        unit = UnitReport(
            ref=slug,
            kind="retrospective",
            epic=slug,
            outcome="error",
            plan_status=verdict,
            reason=detail,
            tokens=usage_dict(agent.usage),
            agent_id=agent.agent_id,
            run_id=agent.run_id,
        )
        report.add(unit)
        log_cumulative_tokens(report)
        return EpicClosureResult(
            closed=False,
            verdict=verdict,
            closure=closure,
            detail=detail,
            retro_path=retro_md,
            epic_path=epic_md,
        )

    created, skipped, errors = materialize_action_items(
        project_root,
        epic_slug=slug,
        retro_md=retro_md,
        action_items=items,
    )
    detail = (
        f"closed {slug} verdict={verdict}; "
        f"created={len(created)} skipped={len(skipped)} materialize_errors={len(errors)}"
    )
    if errors:
        detail += "\n" + "\n".join(errors)
    unit = UnitReport(
        ref=slug,
        kind="retrospective",
        epic=slug,
        outcome="closed",
        plan_status=verdict,
        reason=detail if errors else None,
        tokens=usage_dict(agent.usage),
        agent_id=agent.agent_id,
        run_id=agent.run_id,
    )
    report.add(unit)
    log_cumulative_tokens(report)
    append_journal(
        project_root,
        run_state.run_id,
        {
            "event": "epic_closed",
            "epic": slug,
            "verdict": verdict,
            "created": created,
            "errors": errors,
        },
    )
    save_run(project_root, run_state)
    return EpicClosureResult(
        closed=True,
        verdict=verdict,
        closure=closure or "recommended",
        detail=detail,
        retro_path=retro_md,
        epic_path=epic_md,
        created_tickets=created,
        skipped_tickets=skipped,
        materialize_errors=errors,
    )
