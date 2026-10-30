"""Deferred-work ledger harvest, triage, and bundle execution."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import agent_call_limits, run_cursor_agent, usage_dict
from .constants import (
    POLICY_DIRNAME,
    SHUTDOWN_DIRTY_TREE,
    SHUTDOWN_ERROR,
    FactoryHalt,
    log,
)
from .pick import THOROUGH_ALWAYS
from .pipeline import build_prompt
from .policy import Policy
from .report import RunReport, UnitReport, log_cumulative_tokens
from .run_state import (
    PAUSE_DIRTY_TREE,
    PAUSE_ERROR,
    RunState,
    UnitAttemptState,
    append_journal,
    create_run,
    pause_run,
    save_run,
)
from .scm import (
    checkout_work_branch,
    ensure_push_pr_and_merge,
    has_unpushed_or_new_commits,
    require_clean_tree,
)
from .verify_cmd import run_policy_verify

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
    """Locate deferred-work ledgers under ``_bmad-output`` (skip factory runs)."""
    found: list[Path] = []
    output = project_root / "_bmad-output"
    if not output.is_dir():
        return found
    for path in output.rglob(ledger_name):
        if POLICY_DIRNAME in path.parts:
            continue
        if path.is_file():
            found.append(path)
    return sorted(found)


def parse_ledger(path: Path) -> list[DeferredEntry]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    entries: list[DeferredEntry] = []
    chunks = re.split(r"(?=\n- source_plan:)", "\n" + text)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("- source_plan:"):
            continue
        if "status: closed" in chunk or "closed: true" in chunk.lower():
            continue
        m = ENTRY_RE.match(chunk)
        if not m:
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


def close_ledger_entries(path: Path, keys: set[str]) -> int:
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


def list_open_deferred(
    project_root: Path, *, ledger_name: str = "deferred-work.md"
) -> list[tuple[Path, DeferredEntry]]:
    out: list[tuple[Path, DeferredEntry]] = []
    for ledger in find_initiative_ledgers(project_root, ledger_name=ledger_name):
        for entry in parse_ledger(ledger):
            out.append((ledger, entry))
    return out


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
        "You are triaging a deferred-work ledger for an unattended BMAD factory.\n"
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
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0:
            raise FactoryHalt(SHUTDOWN_ERROR, "deferred triage returned non-JSON")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise FactoryHalt(SHUTDOWN_ERROR, "deferred triage JSON must be an object")

    def _keys(name: str) -> list[str]:
        raw = data.get(name) or []
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw if str(item) in known_keys]

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


def triage_to_dict(triage: SweepTriage) -> dict[str, Any]:
    return {
        "resolved": list(triage.resolved_keys),
        "skip": list(triage.skip_keys),
        "blocked": list(triage.blocked_keys),
        "bundles": [
            {
                "title": b.title,
                "intent": b.intent,
                "entry_keys": list(b.entry_keys),
                "needs_decision": bool(b.needs_decision),
                "decision_prompt": b.decision_prompt,
            }
            for b in triage.bundles
        ],
        "decisions": list(triage.decisions),
    }


def save_triage(triage_path: Path, triage: SweepTriage) -> None:
    """Persist triage so resume does not re-ask answered decisions."""
    triage_path.parent.mkdir(parents=True, exist_ok=True)
    triage_path.write_text(
        json.dumps(triage_to_dict(triage), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _prompt_decisions(
    triage: SweepTriage, *, triage_path: Path | None = None
) -> SweepTriage:
    """Ask for needs_decision bundles; persist each answer to triage.json.

    ``y`` keeps the bundle with ``needs_decision=false``. ``n`` / EOF drops it
    from the build queue (entry keys appended to ``skip``) so a later resume
    does not re-prompt. Ctrl+C persists progress then re-raises.
    """
    kept: list[SweepBundle] = []
    remaining = list(triage.bundles)

    def _persist(rest: list[SweepBundle]) -> None:
        if triage_path is None:
            return
        triage.bundles = kept + rest
        save_triage(triage_path, triage)

    try:
        while remaining:
            bundle = remaining.pop(0)
            if not bundle.needs_decision:
                kept.append(bundle)
                continue
            question = bundle.decision_prompt or bundle.title
            if not sys.stdin.isatty():
                log.warning("skip decision bundle (no TTY): %s", bundle.title)
                # Leave unresolved for a future attended resume.
                remaining.insert(0, bundle)
                break
            try:
                answer = input(
                    f"Deferred decision for [{bundle.title}]: {question} [y/N] "
                )
            except EOFError:
                answer = "n"
            except KeyboardInterrupt:
                remaining.insert(0, bundle)
                _persist(remaining)
                raise
            if answer.strip().lower() in {"y", "yes"}:
                bundle.needs_decision = False
                kept.append(bundle)
                log.info("operator approved bundle=%s", bundle.title)
            else:
                for key in bundle.entry_keys:
                    if key not in triage.skip_keys:
                        triage.skip_keys.append(key)
                log.info("operator skipped bundle=%s", bundle.title)
            _persist(remaining)
    except KeyboardInterrupt:
        _persist(remaining)
        raise

    # File keeps unanswered needs_decision bundles; this run only executes kept.
    if triage_path is not None:
        triage.bundles = kept + remaining
        save_triage(triage_path, triage)
    triage.bundles = kept
    return triage


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
    require_clean_tree(project_root)
    unit_state = UnitAttemptState(ref=synthetic_ref, kind="bundle", phase="build")
    run_state.current_unit = unit_state
    save_run(project_root, run_state)

    branch = checkout_work_branch(project_root, synthetic_ref)
    unit_state.branch = branch
    # Bundles have no ticket risk — thorough only when policy is always.
    thorough = policy.tickets.thorough_review == THOROUGH_ALWAYS

    agent = run_cursor_agent(
        project_root=project_root,
        model=model,
        prompt=build_prompt(synthetic_ref, thorough=thorough, free_form_intent=intent),
        dry_run=dry_run,
        **agent_call_limits(policy.limits),
    )
    if dry_run:
        unit = UnitReport(
            ref=synthetic_ref,
            kind="ticket",
            outcome="dry_run",
            tokens=usage_dict(agent.usage),
        )
        report.add(unit)
        run_state.current_unit = None
        save_run(project_root, run_state)
        return
    if agent.error:
        raise FactoryHalt(SHUTDOWN_ERROR, agent.error)

    run_policy_verify(
        project_root,
        policy,
        ticket_ref=synthetic_ref,
        agent_run_id=agent.run_id or agent.agent_id,
    )

    want_remote = policy.scm.remote == "pr-merge" and not no_push
    pr_url = None
    if want_remote and has_unpushed_or_new_commits(project_root):
        pr_url = ensure_push_pr_and_merge(
            project_root,
            epic=None,
            refs=[synthetic_ref],
            no_push=False,
            dry_run=False,
            title=intent[:60],
            kind="bundle",
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


def triage_path_for(project_root: Path, run_id: str) -> Path:
    return project_root / POLICY_DIRNAME / "runs" / run_id / "triage.json"


def _synthetic_ref(title: str) -> str:
    return f"deferred-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}"


def _load_entries(
    project_root: Path,
    policy: Policy,
    only: list[str] | None,
) -> tuple[list[Path], list[DeferredEntry], dict[str, Path]]:
    ledgers = find_initiative_ledgers(
        project_root, ledger_name=policy.sweep.ledger_name
    )
    entries: list[DeferredEntry] = []
    ledger_by_key: dict[str, Path] = {}
    only_filters = [o.strip().lower() for o in (only or []) if o and o.strip()]
    for ledger in ledgers:
        for entry in parse_ledger(ledger):
            if only_filters and not any(
                f in entry.key.lower() or f in entry.summary.lower()
                for f in only_filters
            ):
                continue
            entries.append(entry)
            ledger_by_key[entry.key] = ledger
    return ledgers, entries, ledger_by_key


def _load_existing_triage(
    triage_path: Path, known_keys: set[str]
) -> SweepTriage | None:
    if not triage_path.is_file():
        return None
    try:
        return parse_triage_response(
            triage_path.read_text(encoding="utf-8"), known_keys=known_keys
        )
    except (FactoryHalt, json.JSONDecodeError, OSError) as err:
        log.warning("deferred triage.json unusable (%s); will re-triage", err)
        return None


def _run_triage_agents(
    *,
    project_root: Path,
    policy: Policy,
    model: str,
    dry_run: bool,
    entries: list[DeferredEntry],
    triage_path: Path,
) -> SweepTriage | None:
    known = {e.key for e in entries}
    prompt = _triage_prompt(entries)
    agent = run_cursor_agent(
        project_root=project_root,
        model=model,
        prompt=prompt,
        dry_run=dry_run,
        **agent_call_limits(policy.limits),
    )
    if dry_run:
        return None
    if agent.error:
        raise FactoryHalt(SHUTDOWN_ERROR, agent.error)

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
        **agent_call_limits(policy.limits),
    )
    if agent2.error:
        raise FactoryHalt(SHUTDOWN_ERROR, agent2.error)
    if not triage_path.is_file():
        raise FactoryHalt(
            SHUTDOWN_ERROR, f"deferred triage did not write {triage_path}"
        )
    return parse_triage_response(
        triage_path.read_text(encoding="utf-8"), known_keys=known
    )


def _filter_remaining_bundles(
    triage: SweepTriage,
    *,
    completed_refs: set[str],
    only: list[str] | None,
) -> list[SweepBundle]:
    only_filters = [o.strip().lower() for o in (only or []) if o and o.strip()]
    remaining: list[SweepBundle] = []
    for bundle in triage.bundles:
        synthetic = _synthetic_ref(bundle.title)
        if synthetic in completed_refs:
            continue
        if only_filters:
            hay = " ".join([bundle.title, bundle.intent, *bundle.entry_keys]).lower()
            if not any(f in hay for f in only_filters):
                continue
        remaining.append(bundle)
    return remaining


def _execute_deferred_bundles(
    *,
    project_root: Path,
    report: RunReport,
    policy: Policy,
    run_state: RunState,
    model: str,
    dry_run: bool,
    no_push: bool,
    triage: SweepTriage,
    ledger_by_key: dict[str, Path],
    only: list[str] | None,
) -> None:
    # Finish an in-flight bundle before scanning remaining triage items.
    current = run_state.current_unit
    if (
        current
        and current.kind == "bundle"
        and current.ref
        and current.ref not in run_state.completed_refs
        and current.phase not in {"done", ""}
    ):
        matching = next(
            (b for b in triage.bundles if _synthetic_ref(b.title) == current.ref),
            None,
        )
        if matching and matching.intent.strip():
            log.info("deferred resume in-flight bundle ref=%s", current.ref)
            try:
                _run_bundle(
                    project_root=project_root,
                    report=report,
                    policy=policy,
                    run_state=run_state,
                    model=model,
                    dry_run=dry_run,
                    no_push=no_push,
                    synthetic_ref=current.ref,
                    intent=matching.intent,
                )
            except FactoryHalt as halt:
                _handle_bundle_halt(project_root, run_state, halt, title=matching.title)
            for key in matching.entry_keys:
                path = ledger_by_key.get(key)
                if path:
                    close_ledger_entries(path, {key})

    remaining = _filter_remaining_bundles(
        triage,
        completed_refs=set(run_state.completed_refs),
        only=only,
    )
    for bundle in remaining:
        if not bundle.intent.strip():
            log.warning("skip bundle with empty intent: %s", bundle.title)
            continue
        log.info(
            "deferred bundle build title=%s keys=%s", bundle.title, bundle.entry_keys
        )
        synthetic = _synthetic_ref(bundle.title)
        try:
            _run_bundle(
                project_root=project_root,
                report=report,
                policy=policy,
                run_state=run_state,
                model=model,
                dry_run=dry_run,
                no_push=no_push,
                synthetic_ref=synthetic,
                intent=bundle.intent,
            )
        except FactoryHalt as halt:
            _handle_bundle_halt(project_root, run_state, halt, title=bundle.title)
        for key in bundle.entry_keys:
            path = ledger_by_key.get(key)
            if path:
                close_ledger_entries(path, {key})


def _handle_bundle_halt(
    project_root: Path,
    run_state: RunState,
    halt: FactoryHalt,
    *,
    title: str,
) -> None:
    """Skip blocked bundles; pause + re-raise on dirty_tree / fatal error."""
    if halt.shutdown == "blocked":
        log.warning("deferred bundle blocked title=%s detail=%s", title, halt.detail)
        append_journal(
            project_root,
            run_state.run_id,
            {
                "event": "deferred_bundle_blocked",
                "title": title,
                "detail": halt.detail,
            },
        )
        run_state.current_unit = None
        save_run(project_root, run_state)
        return
    if halt.shutdown in {SHUTDOWN_DIRTY_TREE, "dirty_tree", SHUTDOWN_ERROR, "error"}:
        reason = (
            PAUSE_DIRTY_TREE
            if halt.shutdown in {SHUTDOWN_DIRTY_TREE, "dirty_tree"}
            else PAUSE_ERROR
        )
        log.warning(
            "deferred bundle halted title=%s shutdown=%s — pausing run",
            title,
            halt.shutdown,
        )
        if run_state.status == "running":
            pause_run(
                project_root,
                run_state,
                reason=reason,
                detail=halt.detail or halt.shutdown,
            )
        raise halt
    raise halt


def continue_deferred(
    *,
    project_root: Path,
    report: RunReport,
    policy: Policy,
    run_state: RunState,
    model: str,
    dry_run: bool,
    no_prompt: bool,
    no_push: bool = False,
    only: list[str] | None = None,
) -> RunState:
    """Continue (or finish triage for) an existing deferred run."""
    ledgers, entries, ledger_by_key = _load_entries(project_root, policy, only)
    run_state.meta = {
        **dict(run_state.meta or {}),
        "ledgers": [str(p) for p in ledgers],
        "entry_count": len(entries),
    }
    save_run(project_root, run_state)

    if not entries and not run_state.current_unit:
        # Allow resume of a run that already has triage/completed work with no
        # open ledger entries left.
        triage_path = triage_path_for(project_root, run_state.run_id)
        if not triage_path.is_file() and not run_state.completed_refs:
            log.info("deferred: no open entries")
            run_state.status = "completed"
            save_run(project_root, run_state)
            return run_state

    known = {e.key for e in entries}
    triage_file = triage_path_for(project_root, run_state.run_id)
    triage = _load_existing_triage(triage_file, known_keys=known)
    reused = triage is not None

    if triage is None:
        if not entries:
            log.info("deferred: no open entries")
            run_state.status = "completed"
            save_run(project_root, run_state)
            return run_state
        triage = _run_triage_agents(
            project_root=project_root,
            policy=policy,
            model=model,
            dry_run=dry_run,
            entries=entries,
            triage_path=triage_file,
        )
        if dry_run or triage is None:
            run_state.status = "completed"
            save_run(project_root, run_state)
            return run_state

        for key in triage.resolved_keys:
            path = ledger_by_key.get(key)
            if path:
                close_ledger_entries(path, {key})

        if not no_prompt and policy.sweep.attended_prompt:
            triage = _prompt_decisions(triage, triage_path=triage_file)
        else:
            # In-memory only: leave needs_decision bundles in triage.json so a
            # later attended resume can still ask.
            triage.bundles = [b for b in triage.bundles if not b.needs_decision]

        append_journal(
            project_root,
            run_state.run_id,
            {
                "event": "deferred_triage",
                "resolved": triage.resolved_keys,
                "bundles": [b.title for b in triage.bundles],
                "blocked": triage.blocked_keys,
                "skip": triage.skip_keys,
            },
        )
    else:
        log.info(
            "deferred resume reusing triage.json run_id=%s reused=%s",
            run_state.run_id,
            reused,
        )
        if not no_prompt and policy.sweep.attended_prompt:
            triage = _prompt_decisions(triage, triage_path=triage_file)
        else:
            triage.bundles = [b for b in triage.bundles if not b.needs_decision]

    _execute_deferred_bundles(
        project_root=project_root,
        report=report,
        policy=policy,
        run_state=run_state,
        model=model,
        dry_run=False if not dry_run else True,
        no_push=no_push,
        triage=triage,
        ledger_by_key=ledger_by_key,
        only=only,
    )

    run_state.status = "completed"
    save_run(project_root, run_state)
    return run_state


def run_deferred(
    *,
    project_root: Path,
    report: RunReport,
    policy: Policy,
    model: str,
    dry_run: bool,
    no_prompt: bool,
    no_push: bool = False,
    yes: bool = False,
    only: list[str] | None = None,
    run_state: RunState | None = None,
) -> RunState:
    """Triage deferred-work ledgers and execute decision-free bundles."""
    if run_state is None:
        ledgers, entries, _ledger_by_key = _load_entries(project_root, policy, only)
        run_state = create_run(
            project_root,
            mode="deferred",
            model=model,
            dry_run=dry_run,
            yes=yes,
            no_push=no_push,
            meta={"ledgers": [str(p) for p in ledgers], "entry_count": len(entries)},
        )
    return continue_deferred(
        project_root=project_root,
        report=report,
        policy=policy,
        run_state=run_state,
        model=model,
        dry_run=dry_run,
        no_prompt=no_prompt,
        no_push=no_push,
        only=only,
    )
