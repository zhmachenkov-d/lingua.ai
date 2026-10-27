"""Deferred-work ledger harvest, triage, and bundle execution."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import run_cursor_agent
from .constants import SHUTDOWN_ERROR, OrchestratorHalt, log
from .policy import Policy
from .report import RunReport
from .run_state import RunState, append_journal, create_run, save_run

ENTRY_RE = re.compile(
    r"^- source_plan:\s*`?([^`\n]+)`?\s*\n"
    r"  summary:\s*(.+)\n"
    r"  evidence:\s*(.+)(?:\n  location:\s*(.+))?(?:\n  severity:\s*(.+))?",
    re.MULTILINE,
)


@dataclass
class DeferredEntry:
    source_plan: str
    summary: str
    evidence: str
    location: str | None = None
    severity: str | None = None
    raw: str = ""
    closed: bool = False

    @property
    def key(self) -> str:
        return f"{self.source_plan}::{self.summary.strip()}"


@dataclass
class SweepBundle:
    title: str
    intent: str
    entry_keys: list[str] = field(default_factory=list)
    needs_decision: bool = False
    decision_prompt: str | None = None


@dataclass
class SweepTriage:
    resolved_keys: list[str] = field(default_factory=list)
    skip_keys: list[str] = field(default_factory=list)
    blocked_keys: list[str] = field(default_factory=list)
    bundles: list[SweepBundle] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)


def find_initiative_ledgers(
    project_root: Path, *, ledger_name: str = "deferred-work.md"
) -> list[Path]:
    """Locate deferred-work ledgers under the project (initiative folders)."""
    found: list[Path] = []
    for path in project_root.rglob(ledger_name):
        # Skip worktrees / output noise.
        parts = set(path.parts)
        if ".bmad-orchestrate" in parts or "_bmad-output" in parts:
            continue
        if path.is_file():
            found.append(path)
    return sorted(found)


def parse_ledger(path: Path) -> list[DeferredEntry]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    entries: list[DeferredEntry] = []
    # Split on top-level bullets that start with source_plan.
    chunks = re.split(r"(?=\n- source_plan:)", "\n" + text)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("- source_plan:"):
            continue
        if "status: closed" in chunk or "closed: true" in chunk.lower():
            continue
        m = ENTRY_RE.match(chunk)
        if not m:
            # Fallback loose parse.
            lines = chunk.splitlines()
            meta: dict[str, str] = {}
            for line in lines:
                if ":" in line:
                    key, _, val = line.lstrip("- ").partition(":")
                    meta[key.strip()] = val.strip().strip("`")
            if not meta.get("source_plan"):
                continue
            entries.append(
                DeferredEntry(
                    source_plan=meta.get("source_plan", ""),
                    summary=meta.get("summary", ""),
                    evidence=meta.get("evidence", ""),
                    location=meta.get("location"),
                    severity=meta.get("severity"),
                    raw=chunk,
                )
            )
            continue
        entries.append(
            DeferredEntry(
                source_plan=m.group(1).strip(),
                summary=m.group(2).strip(),
                evidence=m.group(3).strip(),
                location=(m.group(4) or "").strip() or None,
                severity=(m.group(5) or "").strip() or None,
                raw=chunk,
            )
        )
    return entries


def harvest_plan_deferred(plan_path: Path, project_root: Path, items: list[Any]) -> int:
    """Append plan ``deferred:`` items into the initiative ledger (alias)."""
    from .plan_io import append_deferred

    return append_deferred(plan_path, project_root, items)


def close_ledger_entries(path: Path, keys: set[str]) -> int:
    """Mark matching open entries as closed in the ledger file."""
    if not keys or not path.is_file():
        return 0
    text = path.read_text(encoding="utf-8")
    entries = parse_ledger(path)
    closed = 0
    new_text = text
    for entry in entries:
        if entry.key not in keys:
            continue
        if "status: closed" in entry.raw:
            continue
        replacement = entry.raw.rstrip() + "\n  status: closed\n"
        if entry.raw in new_text:
            new_text = new_text.replace(entry.raw, replacement, 1)
            closed += 1
    if closed:
        path.write_text(new_text, encoding="utf-8")
    return closed


def _triage_prompt(entries: list[DeferredEntry]) -> str:
    payload = [
        {
            "key": e.key,
            "source_plan": e.source_plan,
            "summary": e.summary,
            "evidence": e.evidence,
            "location": e.location,
            "severity": e.severity,
        }
        for e in entries
    ]
    return (
        "You are triaging a deferred-work ledger for an unattended BMAD orchestrator.\n"
        "Partition the open entries into JSON only (no markdown fences) with shape:\n"
        "{\n"
        '  "resolved": ["key", ...],\n'
        '  "skip": ["key", ...],\n'
        '  "blocked": ["key", ...],\n'
        '  "bundles": [\n'
        "    {\n"
        '      "title": "...",\n'
        '      "intent": "free-form build intent for bmad-build-auto",\n'
        '      "entry_keys": ["key", ...],\n'
        '      "needs_decision": false,\n'
        '      "decision_prompt": null\n'
        "    }\n"
        "  ],\n"
        '  "decisions": [{"key": "...", "question": "..."}]\n'
        "}\n"
        "Rules: group related items into buildable bundles; mark truly obsolete as "
        "resolved; needs_decision=true when a human choice is required before build.\n"
        f"Open entries JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
    )


def parse_triage_response(text: str, known_keys: set[str]) -> SweepTriage:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find a JSON object substring.
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0:
            raise OrchestratorHalt(SHUTDOWN_ERROR, "sweep triage returned non-JSON")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise OrchestratorHalt(SHUTDOWN_ERROR, "sweep triage JSON must be an object")

    def _keys(name: str) -> list[str]:
        raw = data.get(name) or []
        if not isinstance(raw, list):
            return []
        out = []
        for item in raw:
            key = str(item)
            if key in known_keys:
                out.append(key)
        return out

    triage = SweepTriage(
        resolved_keys=_keys("resolved"),
        skip_keys=_keys("skip"),
        blocked_keys=_keys("blocked"),
    )
    for b in data.get("bundles") or []:
        if not isinstance(b, dict):
            continue
        entry_keys = [
            str(k) for k in (b.get("entry_keys") or []) if str(k) in known_keys
        ]
        triage.bundles.append(
            SweepBundle(
                title=str(b.get("title") or "bundle"),
                intent=str(b.get("intent") or "").strip(),
                entry_keys=entry_keys,
                needs_decision=bool(b.get("needs_decision")),
                decision_prompt=(
                    str(b["decision_prompt"]) if b.get("decision_prompt") else None
                ),
            )
        )
    for d in data.get("decisions") or []:
        if isinstance(d, dict):
            triage.decisions.append(d)
    return triage


def _prompt_decisions(triage: SweepTriage) -> SweepTriage:
    """Attended TTY: ask about decision-needed bundles; drop rejected ones."""
    kept: list[SweepBundle] = []
    for bundle in triage.bundles:
        if not bundle.needs_decision:
            kept.append(bundle)
            continue
        question = bundle.decision_prompt or bundle.title
        if not sys.stdin.isatty():
            log.warning("skip decision bundle (no TTY): %s", bundle.title)
            continue
        try:
            answer = input(f"Sweep decision for [{bundle.title}]: {question} [y/N] ")
        except EOFError:
            answer = "n"
        if answer.strip().lower() in {"y", "yes"}:
            bundle.needs_decision = False
            kept.append(bundle)
        else:
            log.info("operator skipped bundle=%s", bundle.title)
    triage.bundles = kept
    return triage


def run_sweep(
    *,
    project_root: Path,
    report: RunReport,
    policy: Policy,
    model: str,
    dry_run: bool,
    no_prompt: bool,
    no_push: bool = False,
    yes: bool = False,
) -> RunState:
    """Triage deferred-work ledgers and execute decision-free bundles."""
    ledgers = find_initiative_ledgers(
        project_root, ledger_name=policy.sweep.ledger_name
    )
    entries: list[DeferredEntry] = []
    ledger_by_key: dict[str, Path] = {}
    for ledger in ledgers:
        for entry in parse_ledger(ledger):
            entries.append(entry)
            ledger_by_key[entry.key] = ledger

    run_state = create_run(
        project_root,
        mode="sweep",
        model=model,
        dry_run=dry_run,
        yes=yes,
        no_push=no_push,
        meta={"ledgers": [str(p) for p in ledgers], "entry_count": len(entries)},
    )
    if not entries:
        log.info("sweep: no open deferred entries")
        run_state.status = "completed"
        save_run(project_root, run_state)
        return run_state

    known = {e.key for e in entries}
    prompt = _triage_prompt(entries)
    agent = run_cursor_agent(
        project_root=project_root,
        model=model,
        prompt=prompt,
        dry_run=dry_run,
    )
    if dry_run:
        run_state.status = "completed"
        save_run(project_root, run_state)
        return run_state
    if agent.error:
        raise OrchestratorHalt(SHUTDOWN_ERROR, agent.error)

    # The streaming agent does not return assistant text on AgentRunResult.
    # Ask a tiny follow-up file write via a second structured prompt that writes
    # triage JSON to a known path under .bmad-orchestrate.
    triage_path = (
        project_root / ".bmad-orchestrate" / "runs" / run_state.run_id / "triage.json"
    )
    write_prompt = (
        prompt
        + f"\n\nWrite the JSON result to `{triage_path}` exactly (create parents)."
    )
    agent2 = run_cursor_agent(
        project_root=project_root,
        model=model,
        prompt=write_prompt,
        dry_run=False,
        resume_agent_id=agent.agent_id,
    )
    if agent2.error:
        raise OrchestratorHalt(SHUTDOWN_ERROR, agent2.error)
    if not triage_path.is_file():
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"sweep triage did not write {triage_path}"
        )
    triage = parse_triage_response(
        triage_path.read_text(encoding="utf-8"), known_keys=known
    )

    # Close resolved entries.
    resolved = set(triage.resolved_keys)
    for key in resolved:
        path = ledger_by_key.get(key)
        if path:
            close_ledger_entries(path, {key})

    if not no_prompt and policy.sweep.attended_prompt:
        triage = _prompt_decisions(triage)
    else:
        triage.bundles = [b for b in triage.bundles if not b.needs_decision]

    append_journal(
        project_root,
        run_state.run_id,
        {
            "event": "sweep_triage",
            "resolved": triage.resolved_keys,
            "bundles": [b.title for b in triage.bundles],
            "blocked": triage.blocked_keys,
            "skip": triage.skip_keys,
        },
    )

    for bundle in triage.bundles:
        if not bundle.intent.strip():
            log.warning("skip bundle with empty intent: %s", bundle.title)
            continue
        log.info("sweep bundle build title=%s keys=%s", bundle.title, bundle.entry_keys)
        # Free-form intent through the same pipeline (no ticket ref in tickets.py).
        # Use a synthetic ref for worktree naming; process via free_form_intent.
        synthetic = (
            f"sweep-{re.sub(r'[^a-z0-9]+', '-', bundle.title.lower()).strip('-')}"
        )
        try:
            # tickets_find will fail for synthetic refs — use a dedicated helper path.
            _run_bundle(
                project_root=project_root,
                report=report,
                policy=policy,
                run_state=run_state,
                model=model,
                dry_run=False,
                no_push=no_push,
                synthetic_ref=synthetic,
                intent=bundle.intent,
            )
        except OrchestratorHalt as halt:
            if halt.shutdown in {"blocked", "error", "plateau_deferred"}:
                log.warning(
                    "sweep bundle halted title=%s shutdown=%s",
                    bundle.title,
                    halt.shutdown,
                )
                continue
            raise
        # Close bundled entries on success.
        for key in bundle.entry_keys:
            path = ledger_by_key.get(key)
            if path:
                close_ledger_entries(path, {key})

    run_state.status = "completed"
    save_run(project_root, run_state)
    return run_state


def _run_bundle(
    *,
    project_root: Path,
    report: RunReport,
    policy: Policy,
    run_state: RunState,
    model: str,
    dry_run: bool,
    no_push: bool,
    synthetic_ref: str,
    intent: str,
) -> None:
    """Execute a sweep bundle via build-auto free-form intent in a worktree."""
    from .agent import run_cursor_agent, usage_dict
    from .pipeline import build_prompt
    from .report import UnitReport, log_cumulative_tokens
    from .run_state import UnitAttemptState
    from .scm import create_unit_worktree, land_unit, require_clean_tree

    require_clean_tree(project_root)
    unit_state = UnitAttemptState(ref=synthetic_ref, kind="bundle", phase="build")
    run_state.current_unit = unit_state
    save_run(project_root, run_state)

    session = None
    cwd = project_root
    baseline = None
    if policy.scm.isolation == "worktree":
        session = create_unit_worktree(
            project_root,
            run_id=run_state.run_id,
            ref=synthetic_ref,
            target_branch=policy.scm.target_branch,
        )
        cwd = session.path
        baseline = session.baseline_rev
        unit_state.worktree_path = str(session.path)
        unit_state.branch = session.branch
        unit_state.baseline_rev = baseline

    while unit_state.dev_attempts < policy.limits.max_dev_attempts:
        unit_state.dev_attempts += 1
        fix = unit_state.last_verify
        agent = run_cursor_agent(
            project_root=project_root,
            model=model,
            prompt=build_prompt(
                synthetic_ref, fix_context=fix, free_form_intent=intent
            ),
            dry_run=dry_run,
            cwd=cwd,
        )
        if agent.error:
            unit_state.last_verify = agent.error
            continue
        # For free-form bundles, artifact verify is soft: require_diff only.
        from .policy import VerifyPolicy

        soft = VerifyPolicy(
            commands=list(policy.verify.commands),
            require_diff=policy.verify.require_diff,
        )
        # Bypass plan status by temporarily accepting via a local check.
        from .verify import run_verify_commands, worktree_has_diff

        ok = True
        messages: list[str] = []
        if soft.require_diff and not worktree_has_diff(cwd, baseline):
            ok = False
            messages.append("expected non-empty diff vs baseline")
        if ok and soft.commands:
            ok, outputs = run_verify_commands(cwd, soft.commands)
            if not ok:
                messages.append("verify command failed")
                unit_state.last_verify = "\n\n".join(outputs)
                continue
        if not ok:
            unit_state.last_verify = "; ".join(messages)
            continue

        effective_no_push = no_push or policy.scm.remote != "pr"
        pr_url = land_unit(
            project_root,
            isolation=policy.scm.isolation,
            remote=policy.scm.remote,
            no_push=effective_no_push,
            dry_run=False,
            session=session,
            epic=None,
            refs=[synthetic_ref],
            kind="ticket",
            title=intent[:60],
        )
        unit = UnitReport(
            ref=synthetic_ref,
            kind="ticket",
            outcome="done",
            agent_id=agent.agent_id,
            run_id=agent.run_id,
            tokens=usage_dict(agent.usage),
            pr_url=pr_url,
        )
        report.add(unit)
        log_cumulative_tokens(report)
        run_state.completed_refs.append(synthetic_ref)
        run_state.current_unit = None
        save_run(project_root, run_state)
        return

    # Plateau for bundle — skip without failing whole sweep.
    unit = UnitReport(
        ref=synthetic_ref,
        kind="ticket",
        outcome="plateau_deferred",
        reason=unit_state.last_verify or "bundle attempt budget exhausted",
    )
    report.add(unit)
    if session is not None:
        from .scm import cleanup_worktree

        cleanup_worktree(project_root, session, delete_branch=True)
    run_state.deferred_refs.append(synthetic_ref)
    run_state.current_unit = None
    save_run(project_root, run_state)
