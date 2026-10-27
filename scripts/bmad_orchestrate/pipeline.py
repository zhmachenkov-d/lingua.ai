"""Per-ticket unit pipeline: worktree → build → verify → review → land → harvest."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .agent import agent_call_limits, run_cursor_agent, usage_dict
from .constants import (
    SHUTDOWN_BLOCKED,
    SHUTDOWN_COMPLETED,
    SHUTDOWN_DONE_CHECKPOINT,
    SHUTDOWN_ERROR,
    SHUTDOWN_PAUSED,
    SHUTDOWN_PLAN_CHECKPOINT,
    SHUTDOWN_TICKET_NOT_RESOLVED,
    SHUTDOWN_UNREFINED_BUGS,
    OrchestratorHalt,
    log,
)
from .plan_io import (
    append_deferred,
    blocked_reason_from_artifact,
    format_blocked_redispatch_steps,
    format_missing_status_next_steps,
    read_frontmatter,
)
from .policy import Policy
from .report import RunReport, UnitReport, log_cumulative_tokens
from .run_state import (
    PAUSE_BLOCKED,
    PAUSE_DONE_CHECKPOINT,
    PAUSE_EPIC_BOUNDARY,
    PAUSE_PLAN_CHECKPOINT,
    RunState,
    UnitAttemptState,
    append_journal,
    pause_run,
    save_run,
)
from .scm import (
    WorktreeSession,
    checkout_work_branch,
    create_unit_worktree,
    land_unit,
    require_clean_tree,
)
from .tickets_io import tickets_find, tickets_mark_done, tickets_status
from .tracker import tracker_post_report
from .verify import verify_unit


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


def _is_bug_row(row: dict[str, Any]) -> bool:
    if str(row.get("type") or "").lower() == "bug":
        return True
    name = str(row.get("ref") or row.get("file") or "")
    return name.startswith("bug-")


def _refine_rows(next_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in next_payload.get("ready_to_refine") or []:
        if isinstance(item, dict):
            rows.append(item)
    backlog = next_payload.get("backlog")
    if isinstance(backlog, dict):
        for item in backlog.get("ready_to_refine") or []:
            if isinstance(item, dict):
                rows.append(item)
    return rows


def collect_unrefined_bugs(next_payload: dict[str, Any]) -> list[dict[str, str]]:
    """Bug rows in ready_to_refine (initiative + nested backlog)."""
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in _refine_rows(next_payload):
        if not _is_bug_row(row):
            continue
        ref = str(row.get("ref") or row.get("file") or row.get("id") or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        entry: dict[str, str] = {"ref": ref}
        title = str(row.get("title") or "").strip()
        if title:
            entry["title"] = title
        out.append(entry)
    return out


def explain_unrefined_bugs(bugs: list[dict[str, str]], stream=sys.stderr) -> None:
    print("=== Unrefined bugs (not buildable yet) ===", file=stream)
    for bug in bugs:
        title = bug.get("title") or ""
        suffix = f" — {title}" if title else ""
        print(f"  {bug['ref']}{suffix}", file=stream)
    print(
        "These bugs sit in ready_to_refine until refined: true.\n"
        "This orchestrator only runs bmad-build-auto; it does not refine.\n"
        "Ask Sofia (skill bmad-agent-po) to refine each ticket, then re-run.",
        file=stream,
    )


def prompt_unrefined_bugs_action() -> str:
    """Interactive choice: continue | abort. Loops until a valid answer."""
    while True:
        try:
            answer = (
                input(
                    "Unrefined bugs waiting. [c]ontinue with ready_to_start only, "
                    "[a]bort so you can refine first? "
                )
                .strip()
                .lower()
            )
        except EOFError:
            return "abort"
        if answer in ("c", "continue"):
            return "continue"
        if answer in ("a", "abort"):
            return "abort"
        print("Please enter c or a.", file=sys.stderr)


def gate_unrefined_bugs(
    report: RunReport,
    next_payload: dict[str, Any],
    *,
    yes: bool,
    ready_exists: bool,
    enabled: bool = True,
) -> None:
    """Explain unrefined bugs; optionally ask; halt when abort or only-bugs queue."""
    if not enabled:
        return
    bugs = collect_unrefined_bugs(next_payload)
    report.unrefined_bugs = bugs
    if not bugs:
        return
    explain_unrefined_bugs(bugs)
    log.warning("unrefined bugs count=%s", len(bugs))
    interactive = sys.stdin.isatty() and not yes
    if interactive:
        action = prompt_unrefined_bugs_action()
        log.info("unrefined bugs user action=%s", action)
        if action == "abort":
            refs = ", ".join(b["ref"] for b in bugs)
            raise OrchestratorHalt(
                SHUTDOWN_UNREFINED_BUGS,
                f"aborted with unrefined bugs: {refs}",
            )
    if not ready_exists:
        refs = ", ".join(b["ref"] for b in bugs)
        raise OrchestratorHalt(
            SHUTDOWN_UNREFINED_BUGS,
            f"no ready_to_start work; refine first: {refs}",
        )


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


def build_prompt(
    ref: str,
    *,
    halt_after_planning: bool = False,
    fix_context: str | None = None,
    free_form_intent: str | None = None,
) -> str:
    if free_form_intent:
        base = (
            f"Run skill bmad-build-auto for free-form intent. "
            f"Intent: {free_form_intent}. Do not start any other ticket."
        )
    else:
        base = (
            f"Run skill bmad-build-auto for ticket {ref}. "
            "Do not start any other ticket."
        )
    if halt_after_planning:
        return base + " Halt after planning."
    if fix_context:
        return (
            base + "\n\nPrevious verification failed. Fix the issues below, then leave "
            "the plan status as built/done when verification would pass.\n\n"
            f"{fix_context}"
        )
    return base


def review_prompt(ref: str) -> str:
    return (
        f"Run skill bmad-build-auto for ticket {ref} in follow-up review mode. "
        "Perform an adversarial fresh-context review of the implementation against "
        "the plan. Fix any clear defects you find. Do not start any other ticket."
    )


def retro_prompt(epic_ref: str) -> str:
    return f"Run skill bmad-retrospective -H {epic_ref}. Headless."


def _finish_ticket_unit(
    *,
    project_root: Path,
    report: RunReport,
    unit: UnitReport,
    tracker_id: str | None,
    shutdown: str | None = None,
    shutdown_detail: str | None = None,
) -> None:
    """Record a ticket unit, then post the full RunReport to the tracker when terminal."""
    report.add(unit)
    log_cumulative_tokens(report)
    if unit.outcome in {"dry_run", "followup", "plateau_deferred"}:
        return
    tid = (tracker_id or "").strip()
    if not tid:
        return
    if shutdown is not None:
        report.shutdown = shutdown
        report.shutdown_detail = shutdown_detail
    tracker_post_report(project_root, tracker_id=tid, body=report.format_human())


def _should_review(
    policy: Policy, plan_fm: dict[str, Any], followup_reviews: int
) -> bool:
    if followup_reviews >= policy.effective_max_followup_reviews:
        return False
    if policy.review.trigger == "never":
        return False
    if policy.review.trigger == "always":
        return True
    return bool(plan_fm.get("followup_review_recommended"))


def process_ticket(
    *,
    project_root: Path,
    ref: str,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
    policy: Policy | None = None,
    run_state: RunState | None = None,
    followup_used: bool = False,
    resume_agent_id: str | None = None,
    free_form_intent: str | None = None,
) -> str | None:
    """Process one ticket. Returns epic slug if that epic just became fully done.

    When ``run_state`` + ``policy`` are provided, uses the full resilient pipeline
    (worktree, verify, budgets, plateau-defer, durable pauses). Without them,
    preserves the legacy single-pass path for unit tests / simple callers.
    """
    if policy is not None and run_state is not None:
        return _process_ticket_pipeline(
            project_root=project_root,
            ref=ref,
            report=report,
            model=model,
            dry_run=dry_run,
            no_push=no_push,
            policy=policy,
            run_state=run_state,
            free_form_intent=free_form_intent,
        )
    return _process_ticket_legacy(
        project_root=project_root,
        ref=ref,
        report=report,
        model=model,
        dry_run=dry_run,
        no_push=no_push,
        followup_used=followup_used,
        resume_agent_id=resume_agent_id,
        remote="pr" if not no_push else "none",
    )


def _process_ticket_legacy(
    *,
    project_root: Path,
    ref: str,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
    followup_used: bool = False,
    resume_agent_id: str | None = None,
    remote: str = "pr",
) -> str | None:
    """Original single-pass ticket path (used by existing unit tests)."""
    try:
        found = tickets_find(project_root, ref)
    except OrchestratorHalt as e:
        if e.shutdown == SHUTDOWN_ERROR and "no ticket matches" in (e.detail or ""):
            raise OrchestratorHalt(SHUTDOWN_TICKET_NOT_RESOLVED, e.detail) from e
        raise

    ticket_ref = str(found.get("ref") or ref)
    epic = found.get("epic")
    ticket_type = str(found.get("type") or "").strip() or None
    ticket_title = str(found.get("title") or "").strip() or None
    plan_path = Path(found["plan"]) if found.get("plan") else None
    plan_fm = read_frontmatter(plan_path) if plan_path else {}
    plan_status = str(plan_fm.get("status") or "")
    tracker_id = str(found.get("tracker_id") or "").strip() or None

    plan_checkpoint = bool(found.get("plan_checkpoint"))
    done_checkpoint = bool(found.get("done_checkpoint"))

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
        checkout_work_branch(project_root, ticket_ref)

    prompt = build_prompt(ticket_ref, halt_after_planning=halt_after_planning)
    agent = run_cursor_agent(
        project_root=project_root,
        model=model,
        prompt=prompt,
        dry_run=dry_run,
        resume_agent_id=resume_agent_id,
        **agent_call_limits(),
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
        _finish_ticket_unit(
            project_root=project_root,
            report=report,
            unit=unit,
            tracker_id=tracker_id,
        )
        return None

    if agent.error:
        unit.outcome = "error"
        unit.reason = agent.error
        _finish_ticket_unit(
            project_root=project_root,
            report=report,
            unit=unit,
            tracker_id=tracker_id,
            shutdown=SHUTDOWN_ERROR,
            shutdown_detail=agent.error,
        )
        raise OrchestratorHalt(SHUTDOWN_ERROR, agent.error)

    try:
        found = tickets_find(project_root, ticket_ref)
        tracker_id = str(found.get("tracker_id") or "").strip() or tracker_id
        ticket_type = str(found.get("type") or "").strip() or ticket_type
        ticket_title = str(found.get("title") or "").strip() or ticket_title
    except OrchestratorHalt:
        pass
    plan_path = Path(found["plan"]) if found.get("plan") else plan_path
    plan_fm = read_frontmatter(plan_path) if plan_path else {}
    plan_status = str(plan_fm.get("status") or "")
    result_path: Path | None = None
    status_from_result_only = False
    if not plan_status:
        from .plan_io import find_build_auto_result, ticket_slug_from_ref

        result_path = find_build_auto_result(
            project_root, ticket_slug_from_ref(ticket_ref)
        )
        if result_path is not None:
            result_fm = read_frontmatter(result_path)
            result_status = str(result_fm.get("status") or "")
            if result_status:
                plan_status = result_status
                status_from_result_only = True
                if not plan_fm.get("blocked_reason") and result_fm.get(
                    "blocked_reason"
                ):
                    plan_fm = {**plan_fm, "blocked_reason": result_fm["blocked_reason"]}

    unit.plan_status = plan_status or None
    done_checkpoint = bool(found.get("done_checkpoint")) or done_checkpoint

    if halt_after_planning:
        unit.outcome = "checkpoint"
        unit.reason = "plan_checkpoint: waiting for human plan approval"
        detail = f"ticket {ticket_ref}: plan checkpoint"
        _finish_ticket_unit(
            project_root=project_root,
            report=report,
            unit=unit,
            tracker_id=tracker_id,
            shutdown=SHUTDOWN_PLAN_CHECKPOINT,
            shutdown_detail=detail,
        )
        raise OrchestratorHalt(SHUTDOWN_PLAN_CHECKPOINT, detail)

    if plan_status == "blocked":
        artifact = (
            result_path
            if status_from_result_only
            else (plan_path if plan_path and plan_path.is_file() else result_path)
        )
        reason = blocked_reason_from_artifact(artifact, plan_fm)
        if reason == "blocked":
            reason = str(found.get("blocked_reason") or "blocked")
        unit.outcome = "blocked"
        unit.reason = reason
        detail = f"ticket {ticket_ref}: {reason}"
        report.next_steps = format_blocked_redispatch_steps(
            ticket_ref=ticket_ref,
            reason=reason,
            artifact_path=artifact,
            plan_path=plan_path,
            status_from_result_only=status_from_result_only,
            model=model,
        )
        _finish_ticket_unit(
            project_root=project_root,
            report=report,
            unit=unit,
            tracker_id=tracker_id,
            shutdown=SHUTDOWN_BLOCKED,
            shutdown_detail=detail,
        )
        raise OrchestratorHalt(SHUTDOWN_BLOCKED, detail)

    if plan_status not in ("built", "done"):
        unit.outcome = "error"
        unit.reason = (
            f"unexpected plan status after agent: {plan_status or '(missing)'}"
        )
        if not plan_status:
            report.next_steps = format_missing_status_next_steps(
                ticket_ref=ticket_ref,
                plan_path=plan_path,
                model=model,
            )
        _finish_ticket_unit(
            project_root=project_root,
            report=report,
            unit=unit,
            tracker_id=tracker_id,
            shutdown=SHUTDOWN_ERROR,
            shutdown_detail=unit.reason,
        )
        raise OrchestratorHalt(SHUTDOWN_ERROR, unit.reason)

    deferred_items = plan_fm.get("deferred") or []
    if not isinstance(deferred_items, list):
        deferred_items = []
    if plan_path and deferred_items:
        unit.deferred_count = append_deferred(plan_path, project_root, deferred_items)

    if done_checkpoint:
        unit.outcome = "checkpoint"
        unit.reason = "done_checkpoint: waiting for human continue"
        detail = f"ticket {ticket_ref}: done checkpoint"
        _finish_ticket_unit(
            project_root=project_root,
            report=report,
            unit=unit,
            tracker_id=tracker_id,
            shutdown=SHUTDOWN_DONE_CHECKPOINT,
            shutdown_detail=detail,
        )
        raise OrchestratorHalt(SHUTDOWN_DONE_CHECKPOINT, detail)

    followup = bool(plan_fm.get("followup_review_recommended"))
    if followup and not followup_used:
        unit.outcome = "followup"
        _finish_ticket_unit(
            project_root=project_root,
            report=report,
            unit=unit,
            tracker_id=tracker_id,
        )
        return process_ticket(
            project_root=project_root,
            ref=ticket_ref,
            report=report,
            model=model,
            dry_run=dry_run,
            no_push=no_push,
            followup_used=True,
            resume_agent_id=agent.agent_id,
        )

    if plan_path:
        tickets_mark_done(
            project_root,
            ticket_ref,
            plan_path,
            tracker_id=tracker_id,
        )
    unit.outcome = "done"

    pr_url = None
    if remote == "pr" and not no_push:
        from .scm import ensure_push_pr_and_merge, has_unpushed_or_new_commits

        if has_unpushed_or_new_commits(project_root):
            pr_url = ensure_push_pr_and_merge(
                project_root,
                epic=str(epic) if epic else None,
                refs=[ticket_ref],
                no_push=no_push,
                dry_run=dry_run,
                ticket_type=ticket_type,
                title=ticket_title,
                tracker_id=tracker_id,
                plan_path=plan_path,
                kind="ticket",
            )
            unit.pr_url = pr_url
    _finish_ticket_unit(
        project_root=project_root,
        report=report,
        unit=unit,
        tracker_id=tracker_id,
        shutdown=SHUTDOWN_COMPLETED,
    )

    if epic and epic_fully_done(project_root, str(epic)):
        return str(epic)
    return None


def _process_ticket_pipeline(
    *,
    project_root: Path,
    ref: str,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
    policy: Policy,
    run_state: RunState,
    free_form_intent: str | None = None,
) -> str | None:
    """Full resilient pipeline with worktree, verify, review, plateau-defer."""
    try:
        found = tickets_find(project_root, ref)
    except OrchestratorHalt as e:
        if e.shutdown == SHUTDOWN_ERROR and "no ticket matches" in (e.detail or ""):
            raise OrchestratorHalt(SHUTDOWN_TICKET_NOT_RESOLVED, e.detail) from e
        raise

    ticket_ref = str(found.get("ref") or ref)
    epic = found.get("epic")
    ticket_type = str(found.get("type") or "").strip() or None
    ticket_title = str(found.get("title") or "").strip() or None
    plan_path = Path(found["plan"]) if found.get("plan") else None
    plan_fm = read_frontmatter(plan_path) if plan_path else {}
    plan_status = str(plan_fm.get("status") or "")
    tracker_id = str(found.get("tracker_id") or "").strip() or None
    plan_checkpoint = (
        bool(found.get("plan_checkpoint")) and policy.gates.plan_checkpoint
    )
    done_checkpoint = (
        bool(found.get("done_checkpoint")) and policy.gates.done_checkpoint
    )

    post_plan_statuses = (
        "ready-for-dev",
        "in-progress",
        "in-review",
        "built",
        "done",
        "blocked",
    )
    halt_after_planning = bool(
        plan_checkpoint
        and plan_status not in post_plan_statuses
        and not (
            run_state.current_unit
            and run_state.current_unit.extra.get("plan_checkpoint_cleared")
        )
    )

    unit_state = run_state.current_unit
    if unit_state is None or unit_state.ref != ticket_ref:
        unit_state = UnitAttemptState(ref=ticket_ref, kind="ticket", phase="setup")
        run_state.current_unit = unit_state
    save_run(project_root, run_state)

    log.info(
        "ticket start ref=%s epic=%s plan_status=%s isolation=%s remote=%s",
        ticket_ref,
        epic,
        plan_status or "(none)",
        policy.scm.isolation,
        policy.scm.remote,
    )

    session: WorktreeSession | None = None
    agent_cwd = project_root
    baseline_rev: str | None = None

    if dry_run:
        prompt = build_prompt(
            ticket_ref,
            halt_after_planning=halt_after_planning,
            free_form_intent=free_form_intent,
        )
        agent = run_cursor_agent(
            project_root=project_root,
            model=model,
            prompt=prompt,
            dry_run=True,
            **agent_call_limits(policy.limits),
        )
        unit = UnitReport(
            ref=ticket_ref,
            kind="ticket",
            epic=str(epic) if epic else None,
            outcome="dry_run",
            plan_status=plan_status or None,
            tokens=usage_dict(agent.usage),
        )
        _finish_ticket_unit(
            project_root=project_root,
            report=report,
            unit=unit,
            tracker_id=tracker_id,
        )
        return None

    require_clean_tree(project_root)

    if policy.scm.isolation == "worktree":
        session = create_unit_worktree(
            project_root,
            run_id=run_state.run_id,
            ref=ticket_ref,
            target_branch=policy.scm.target_branch or run_state.target_branch,
        )
        agent_cwd = session.path
        baseline_rev = session.baseline_rev
        unit_state.worktree_path = str(session.path)
        unit_state.branch = session.branch
        unit_state.baseline_rev = baseline_rev
    else:
        branch = checkout_work_branch(project_root, ticket_ref)
        unit_state.branch = branch
        from .scm import run_git

        baseline_rev = run_git(project_root, "rev-parse", "HEAD").stdout.strip()
        unit_state.baseline_rev = baseline_rev

    save_run(project_root, run_state)
    append_journal(
        project_root,
        run_state.run_id,
        {"event": "unit_setup", "ref": ticket_ref, "branch": unit_state.branch},
    )

    # --- plan checkpoint pause ---
    if halt_after_planning:
        unit_state.phase = "plan_checkpoint"
        save_run(project_root, run_state)
        prompt = build_prompt(
            ticket_ref,
            halt_after_planning=True,
            free_form_intent=free_form_intent,
        )
        agent = run_cursor_agent(
            project_root=project_root,
            model=model,
            prompt=prompt,
            dry_run=False,
            cwd=agent_cwd,
            **agent_call_limits(policy.limits),
        )
        unit = UnitReport(
            ref=ticket_ref,
            kind="ticket",
            epic=str(epic) if epic else None,
            outcome="checkpoint",
            reason="plan_checkpoint: waiting for human plan approval",
            tokens=usage_dict(agent.usage),
            agent_id=agent.agent_id,
            run_id=agent.run_id,
        )
        detail = f"ticket {ticket_ref}: plan checkpoint"
        _finish_ticket_unit(
            project_root=project_root,
            report=report,
            unit=unit,
            tracker_id=tracker_id,
            shutdown=SHUTDOWN_PLAN_CHECKPOINT,
            shutdown_detail=detail,
        )
        pause_run(
            project_root,
            run_state,
            reason=PAUSE_PLAN_CHECKPOINT,
            detail=detail,
            ticket=ticket_ref,
        )
        raise OrchestratorHalt(SHUTDOWN_PLAN_CHECKPOINT, detail)

    # --- build / verify loop ---
    unit_state.phase = "build"
    fix_context: str | None = None
    last_agent_id: str | None = None
    last_verify_summary = ""
    plan_fm = read_frontmatter(plan_path) if plan_path else {}
    verify_plan = plan_path

    while True:
        if unit_state.dev_attempts >= policy.limits.max_dev_attempts:
            # Plateau-defer: record and continue the outer loop.
            return _plateau_defer(
                project_root=project_root,
                run_state=run_state,
                unit_state=unit_state,
                report=report,
                ticket_ref=ticket_ref,
                epic=str(epic) if epic else None,
                tracker_id=tracker_id,
                reason=last_verify_summary or "dev attempt budget exhausted",
                session=session,
            )

        unit_state.dev_attempts += 1
        unit_state.phase = "build"
        save_run(project_root, run_state)
        prompt = build_prompt(
            ticket_ref,
            fix_context=fix_context,
            free_form_intent=free_form_intent,
        )
        # Always fresh Agent.create for each fix attempt after the first? First may
        # resume only within the same implementer cycle — plan says review is fresh;
        # fix attempts may continue. Use no resume so each verify-fix is cleaner.
        agent = run_cursor_agent(
            project_root=project_root,
            model=model,
            prompt=prompt,
            dry_run=False,
            cwd=agent_cwd,
            resume_agent_id=None,
            **agent_call_limits(policy.limits),
        )
        last_agent_id = agent.agent_id
        unit_state.agent_id = agent.agent_id
        append_journal(
            project_root,
            run_state.run_id,
            {
                "event": "dev_attempt",
                "ref": ticket_ref,
                "attempt": unit_state.dev_attempts,
                "agent_id": agent.agent_id,
            },
        )

        if agent.error:
            fix_context = agent.error
            last_verify_summary = agent.error
            unit_state.last_verify = agent.error
            save_run(project_root, run_state)
            continue

        # Refresh plan metadata from main project root (tickets store).
        try:
            found = tickets_find(project_root, ticket_ref)
            tracker_id = str(found.get("tracker_id") or "").strip() or tracker_id
            ticket_type = str(found.get("type") or "").strip() or ticket_type
            ticket_title = str(found.get("title") or "").strip() or ticket_title
            plan_path = Path(found["plan"]) if found.get("plan") else plan_path
            done_checkpoint = (
                bool(found.get("done_checkpoint")) and policy.gates.done_checkpoint
            ) or done_checkpoint
        except OrchestratorHalt:
            pass

        # Prefer worktree copies of plan/result when isolation=worktree.
        verify_root = agent_cwd
        verify_plan = plan_path
        if session is not None and plan_path is not None:
            try:
                rel = plan_path.resolve().relative_to(project_root.resolve())
                candidate = session.path / rel
                if candidate.is_file():
                    verify_plan = candidate
            except ValueError:
                pass

        vresult = verify_unit(
            project_root=verify_root,
            ticket_ref=ticket_ref,
            plan_path=verify_plan,
            policy=policy.verify,
            baseline_rev=baseline_rev,
            expect_diff=True,
        )
        plan_fm = vresult.plan_fm
        plan_status = vresult.plan_status or ""
        unit_state.last_verify = vresult.summary
        last_verify_summary = vresult.summary
        save_run(project_root, run_state)

        if plan_status == "blocked":
            artifact = vresult.result_path or vresult.plan_path
            reason = blocked_reason_from_artifact(artifact, plan_fm)
            unit = UnitReport(
                ref=ticket_ref,
                kind="ticket",
                epic=str(epic) if epic else None,
                plan_status=plan_status,
                outcome="blocked",
                reason=reason,
                tokens=usage_dict(agent.usage),
                agent_id=agent.agent_id,
                run_id=agent.run_id,
            )
            detail = f"ticket {ticket_ref}: {reason}"
            report.next_steps = format_blocked_redispatch_steps(
                ticket_ref=ticket_ref,
                reason=reason,
                artifact_path=artifact,
                plan_path=plan_path,
                status_from_result_only=vresult.status_from_result_only,
                model=model,
            )
            _finish_ticket_unit(
                project_root=project_root,
                report=report,
                unit=unit,
                tracker_id=tracker_id,
                shutdown=SHUTDOWN_BLOCKED,
                shutdown_detail=detail,
            )
            run_state.blocked_refs.append({"ref": ticket_ref, "reason": reason})
            pause_run(
                project_root,
                run_state,
                reason=PAUSE_BLOCKED,
                detail=detail,
                ticket=ticket_ref,
            )
            raise OrchestratorHalt(SHUTDOWN_BLOCKED, detail)

        if not vresult.ok:
            if not plan_status:
                # Missing status — treat as hard error with next steps after budget.
                fix_context = format_missing_status_next_steps(
                    ticket_ref=ticket_ref,
                    plan_path=plan_path,
                    model=model,
                )
            else:
                outputs = "\n\n".join(vresult.command_outputs) or vresult.summary
                fix_context = outputs
            continue

        # verify passed
        break

    # --- optional fresh-context review ---
    followup_reviews = unit_state.followup_reviews
    while _should_review(policy, plan_fm, followup_reviews):
        if unit_state.review_cycles >= policy.limits.max_review_cycles:
            break
        unit_state.review_cycles += 1
        followup_reviews += 1
        unit_state.followup_reviews = followup_reviews
        unit_state.phase = "review"
        save_run(project_root, run_state)
        append_journal(
            project_root,
            run_state.run_id,
            {
                "event": "review",
                "ref": ticket_ref,
                "cycle": unit_state.review_cycles,
            },
        )
        # Fresh agent — never resume implementer.
        review_agent = run_cursor_agent(
            project_root=project_root,
            model=model,
            prompt=review_prompt(ticket_ref),
            dry_run=False,
            cwd=agent_cwd,
            resume_agent_id=None,
            **agent_call_limits(policy.limits),
        )
        last_agent_id = review_agent.agent_id or last_agent_id
        if review_agent.error:
            log.warning("review agent error: %s", review_agent.error)
        vresult = verify_unit(
            project_root=agent_cwd,
            ticket_ref=ticket_ref,
            plan_path=verify_plan,
            policy=policy.verify,
            baseline_rev=baseline_rev,
            expect_diff=True,
        )
        plan_fm = vresult.plan_fm
        if not vresult.ok:
            if unit_state.dev_attempts >= policy.limits.max_dev_attempts:
                return _plateau_defer(
                    project_root=project_root,
                    run_state=run_state,
                    unit_state=unit_state,
                    report=report,
                    ticket_ref=ticket_ref,
                    epic=str(epic) if epic else None,
                    tracker_id=tracker_id,
                    reason=vresult.summary,
                    session=session,
                )
            # One more implementer pass for review findings, then re-verify.
            unit_state.dev_attempts += 1
            fix_outputs = "\n\n".join(vresult.command_outputs) or vresult.summary
            fix_agent = run_cursor_agent(
                project_root=project_root,
                model=model,
                prompt=build_prompt(ticket_ref, fix_context=fix_outputs),
                dry_run=False,
                cwd=agent_cwd,
                **agent_call_limits(policy.limits),
            )
            last_agent_id = fix_agent.agent_id or last_agent_id
            vresult = verify_unit(
                project_root=agent_cwd,
                ticket_ref=ticket_ref,
                plan_path=verify_plan,
                policy=policy.verify,
                baseline_rev=baseline_rev,
                expect_diff=True,
            )
            plan_fm = vresult.plan_fm
            if not vresult.ok:
                continue
        # Review passed; stop when trigger=recommended after one successful cycle.
        if policy.review.trigger == "recommended":
            break

    # Sync plan_fm from worktree back — harvest deferred from verified fm.
    deferred_items = plan_fm.get("deferred") or []
    if not isinstance(deferred_items, list):
        deferred_items = []
    deferred_count = 0
    harvest_plan = plan_path
    if session is not None and plan_path is not None:
        try:
            rel = plan_path.resolve().relative_to(project_root.resolve())
            candidate = session.path / rel
            if candidate.is_file():
                harvest_plan = candidate
                # Copy deferred-bearing plan status back by reading fm already have.
        except ValueError:
            pass
    if harvest_plan and deferred_items:
        deferred_count = append_deferred(harvest_plan, project_root, deferred_items)
        # Also append using main-tree plan path when worktree path was used so
        # initiative_dir_for still resolves under project_root.
        if harvest_plan != plan_path and plan_path:
            try:
                append_deferred(plan_path, project_root, deferred_items)
            except OrchestratorHalt:
                pass

    # --- done checkpoint ---
    if done_checkpoint and not unit_state.extra.get("done_checkpoint_cleared"):
        unit_state.phase = "done_checkpoint"
        save_run(project_root, run_state)
        unit = UnitReport(
            ref=ticket_ref,
            kind="ticket",
            epic=str(epic) if epic else None,
            plan_status=plan_status or None,
            outcome="checkpoint",
            reason="done_checkpoint: waiting for human continue",
            deferred_count=deferred_count,
            agent_id=last_agent_id,
        )
        detail = f"ticket {ticket_ref}: done checkpoint"
        _finish_ticket_unit(
            project_root=project_root,
            report=report,
            unit=unit,
            tracker_id=tracker_id,
            shutdown=SHUTDOWN_DONE_CHECKPOINT,
            shutdown_detail=detail,
        )
        pause_run(
            project_root,
            run_state,
            reason=PAUSE_DONE_CHECKPOINT,
            detail=detail,
            ticket=ticket_ref,
        )
        raise OrchestratorHalt(SHUTDOWN_DONE_CHECKPOINT, detail)

    # --- mark done + land ---
    unit_state.phase = "landing"
    save_run(project_root, run_state)
    if plan_path:
        tickets_mark_done(
            project_root,
            ticket_ref,
            plan_path,
            tracker_id=tracker_id,
        )

    effective_no_push = no_push or policy.scm.remote != "pr"
    pr_url = land_unit(
        project_root,
        isolation=policy.scm.isolation,
        remote=policy.scm.remote,
        no_push=effective_no_push,
        dry_run=False,
        session=session,
        epic=str(epic) if epic else None,
        refs=[ticket_ref],
        ticket_type=ticket_type,
        title=ticket_title,
        tracker_id=tracker_id,
        plan_path=plan_path,
        kind="ticket",
    )

    unit = UnitReport(
        ref=ticket_ref,
        kind="ticket",
        epic=str(epic) if epic else None,
        plan_status=plan_status or "built",
        outcome="done",
        deferred_count=deferred_count,
        agent_id=last_agent_id,
        pr_url=pr_url,
    )
    _finish_ticket_unit(
        project_root=project_root,
        report=report,
        unit=unit,
        tracker_id=tracker_id,
        shutdown=SHUTDOWN_COMPLETED,
    )
    run_state.completed_refs.append(ticket_ref)
    run_state.current_unit = None
    run_state.pause_ticket = None
    save_run(project_root, run_state)
    append_journal(
        project_root,
        run_state.run_id,
        {"event": "unit_done", "ref": ticket_ref, "pr_url": pr_url},
    )

    if epic and epic_fully_done(project_root, str(epic)):
        return str(epic)
    return None


def _plateau_defer(
    *,
    project_root: Path,
    run_state: RunState,
    unit_state: UnitAttemptState,
    report: RunReport,
    ticket_ref: str,
    epic: str | None,
    tracker_id: str | None,
    reason: str,
    session: WorktreeSession | None,
) -> str | None:
    """Record plateau-defer and continue (returns None to outer loop)."""
    unit_state.plateau_deferred = True
    unit_state.outcome = "plateau_deferred"
    unit_state.reason = reason
    unit_state.phase = "plateau"
    if ticket_ref not in run_state.deferred_refs:
        run_state.deferred_refs.append(ticket_ref)
    unit = UnitReport(
        ref=ticket_ref,
        kind="ticket",
        epic=epic,
        outcome="plateau_deferred",
        reason=reason,
        agent_id=unit_state.agent_id,
    )
    _finish_ticket_unit(
        project_root=project_root,
        report=report,
        unit=unit,
        tracker_id=tracker_id,
    )
    append_journal(
        project_root,
        run_state.run_id,
        {"event": "plateau_deferred", "ref": ticket_ref, "reason": reason},
    )
    # Best-effort cleanup of worktree without merging.
    if session is not None:
        from .scm import cleanup_worktree

        try:
            cleanup_worktree(project_root, session, delete_branch=True)
        except OrchestratorHalt:
            log.warning("worktree cleanup after plateau failed ref=%s", ticket_ref)
    run_state.current_unit = None
    save_run(project_root, run_state)
    log.warning("plateau-deferred ref=%s reason=%s", ticket_ref, reason)
    # Do not pause the whole run — continue to next ticket.
    return None


def run_retrospective(
    *,
    project_root: Path,
    epic: str,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
    policy: Policy | None = None,
    run_state: RunState | None = None,
) -> None:
    ref = f"retrospective:{epic}"
    log.info("retrospective start epic=%s", epic)
    if not dry_run:
        require_clean_tree(project_root)
        isolation = policy.scm.isolation if policy else "inplace"
        session: WorktreeSession | None = None
        cwd = project_root
        if isolation == "worktree" and run_state is not None:
            session = create_unit_worktree(
                project_root,
                run_id=run_state.run_id,
                ref=f"retro-{epic}",
                target_branch=policy.scm.target_branch if policy else None,
            )
            cwd = session.path
        else:
            checkout_work_branch(project_root, f"retro-{epic}")
            session = None
    else:
        session = None
        cwd = project_root

    agent = run_cursor_agent(
        project_root=project_root,
        model=model,
        prompt=retro_prompt(epic),
        dry_run=dry_run,
        cwd=cwd if not dry_run else None,
        **agent_call_limits(policy.limits if policy else None),
    )
    unit = UnitReport(
        ref=ref,
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

    remote = policy.scm.remote if policy else ("pr" if not no_push else "none")
    effective_no_push = no_push or remote != "pr"
    isolation = policy.scm.isolation if policy else "inplace"
    pr_url = land_unit(
        project_root,
        isolation=isolation,
        remote=remote,
        no_push=effective_no_push,
        dry_run=False,
        session=session,
        epic=epic,
        refs=[ref],
        kind="retrospective",
    )
    unit.outcome = "done"
    unit.pr_url = pr_url
    report.add(unit)
    log_cumulative_tokens(report)

    if (
        policy
        and policy.gates.epic_boundary_pause
        and run_state is not None
        and not dry_run
    ):
        pause_run(
            project_root,
            run_state,
            reason=PAUSE_EPIC_BOUNDARY,
            detail=f"epic {epic} retrospective complete",
            ticket=epic,
        )
        raise OrchestratorHalt(
            SHUTDOWN_PAUSED,
            f"paused at epic boundary after retrospective: {epic}",
        )


def maybe_retro_after(
    epic: str | None,
    *,
    project_root: Path,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
    retros_done: set[str],
    policy: Policy | None = None,
    run_state: RunState | None = None,
) -> None:
    if not epic or epic == "backlog" or epic in retros_done:
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
        policy=policy,
        run_state=run_state,
    )
    retros_done.add(epic)
    if run_state is not None:
        if epic not in run_state.retros_done:
            run_state.retros_done.append(epic)
        save_run(project_root, run_state)
