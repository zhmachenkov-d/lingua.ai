"""Per-ticket unit pipeline (inplace): build → harvest → mark done → land."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent import agent_call_limits, run_cursor_agent, usage_dict
from .constants import (
    SHUTDOWN_BLOCKED,
    SHUTDOWN_DONE_CHECKPOINT,
    SHUTDOWN_ERROR,
    SHUTDOWN_PLAN_CHECKPOINT,
    SHUTDOWN_TICKET_NOT_RESOLVED,
    FactoryHalt,
    log,
)
from .pick import Phase, wants_thorough
from .plan_io import (
    append_deferred,
    blocked_reason_from_artifact,
    find_build_auto_result,
    format_blocked_redispatch_steps,
    format_halt_reinvoke_steps,
    read_frontmatter,
    ticket_slug_from_ref,
)
from .policy import Policy
from .report import RunReport, UnitReport, log_cumulative_tokens
from .run_state import (
    PAUSE_BLOCKED,
    PAUSE_DONE_CHECKPOINT,
    PAUSE_PLAN_CHECKPOINT,
    RunState,
    UnitAttemptState,
    append_journal,
    pause_run,
    save_run,
)
from .scm import (
    checkout_work_branch,
    ensure_push_pr_and_merge,
    has_unpushed_or_new_commits,
    require_clean_tree,
    run_git,
)
from .tickets_io import tickets_find, tickets_mark_done, tickets_status


def build_prompt(
    ref: str,
    *,
    halt_after_planning: bool = False,
    thorough: bool = False,
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
    if thorough:
        base += " thorough"
    if halt_after_planning:
        return base + " Halt after planning."
    return base


def _cli_args_for_run(run_state: RunState) -> str:
    if run_state.mode == "ticket" and run_state.ticket:
        return f"--ticket {run_state.ticket}"
    if run_state.mode == "epic" and run_state.epic:
        return f"--epic {run_state.epic}"
    if run_state.mode == "backlog":
        return "--backlog"
    if run_state.mode == "deferred":
        return "--deferred"
    return ""


def epic_fully_done(
    project_root: Path, epic: str, *, policy: Policy | None = None
) -> bool:
    if not epic or epic == "backlog":
        return False
    try:
        status = tickets_status(project_root, epic, policy=policy)
    except FactoryHalt:
        return False
    tickets = status.get("tickets") or []
    if not tickets:
        return False
    return all(t.get("state") == "done" or t.get("status") == "done" for t in tickets)


def _resolve_plan_status(
    project_root: Path,
    ticket_ref: str,
    plan_path: Path | None,
    plan_fm: dict[str, Any],
) -> tuple[str, dict[str, Any], Path | None, bool]:
    status = str(plan_fm.get("status") or "")
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
                if not plan_fm.get("blocked_reason") and result_fm.get(
                    "blocked_reason"
                ):
                    plan_fm = {**plan_fm, "blocked_reason": result_fm["blocked_reason"]}
                for key in ("deferred",):
                    if key not in plan_fm and key in result_fm:
                        plan_fm[key] = result_fm[key]
    return status, plan_fm, result_path, status_from_result_only


def process_ticket(
    *,
    project_root: Path,
    ref: str,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
    policy: Policy,
    run_state: RunState,
) -> str | None:
    """Process one ticket. Returns epic slug if that epic just became fully done."""
    try:
        found = tickets_find(project_root, ref, policy=policy)
    except FactoryHalt as e:
        if e.shutdown == SHUTDOWN_ERROR and "no ticket matches" in (e.detail or ""):
            raise FactoryHalt(SHUTDOWN_TICKET_NOT_RESOLVED, e.detail) from e
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
    risk = str(found.get("risk") or plan_fm.get("risk") or "")
    thorough = wants_thorough(policy.tickets.thorough_review, risk)
    cli_args = _cli_args_for_run(run_state)

    unit_state = run_state.current_unit
    if unit_state is None or unit_state.ref != ticket_ref:
        unit_state = UnitAttemptState(ref=ticket_ref, kind="ticket", phase="setup")
        run_state.current_unit = unit_state
    save_run(project_root, run_state)

    post_plan_statuses = (
        "ready-for-dev",
        "in-progress",
        "in-review",
        "built",
        "done",
        "blocked",
    )
    plan_cleared = bool(unit_state.extra.get("plan_checkpoint_cleared"))
    done_cleared = bool(unit_state.extra.get("done_checkpoint_cleared"))
    # Re-invoke after plan checkpoint: continue implementation.
    if plan_cleared or (
        run_state.pause_reason in {PAUSE_PLAN_CHECKPOINT, "plan-checkpoint"}
        and plan_status in post_plan_statuses
        and plan_status not in {"", "draft"}
    ):
        plan_cleared = True
        unit_state.extra["plan_checkpoint_cleared"] = True

    # Re-invoke after done checkpoint with plan still built → land.
    if done_cleared or (
        unit_state.extra.get("awaiting_done_confirm")
        and plan_status in {"built", "done"}
    ):
        done_cleared = True
        unit_state.extra["done_checkpoint_cleared"] = True

    halt_after_planning = bool(
        plan_checkpoint and plan_status not in post_plan_statuses and not plan_cleared
    )

    log.info(
        "ticket start ref=%s epic=%s plan_status=%s thorough=%s halt_plan=%s",
        ticket_ref,
        epic,
        plan_status or "(none)",
        thorough,
        halt_after_planning,
    )

    if dry_run:
        prompt = build_prompt(
            ticket_ref, halt_after_planning=halt_after_planning, thorough=thorough
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
        report.add(unit)
        log_cumulative_tokens(report)
        return None

    # Done-checkpoint confirm path: skip agent, go straight to mark/land.
    if done_cleared and plan_status in {"built", "done"}:
        return _finish_built(
            project_root=project_root,
            report=report,
            policy=policy,
            run_state=run_state,
            unit_state=unit_state,
            ticket_ref=ticket_ref,
            epic=str(epic) if epic else None,
            ticket_type=ticket_type,
            ticket_title=ticket_title,
            tracker_id=tracker_id,
            plan_path=plan_path,
            plan_fm=plan_fm,
            plan_status=plan_status,
            no_push=no_push,
            dry_run=False,
            model=model,
            tokens=None,
            agent_id=unit_state.agent_id,
            run_id=None,
        )

    require_clean_tree(project_root)
    branch = checkout_work_branch(project_root, ticket_ref)
    unit_state.branch = branch
    unit_state.baseline_rev = run_git(project_root, "rev-parse", "HEAD").stdout.strip()
    save_run(project_root, run_state)
    append_journal(
        project_root,
        run_state.run_id,
        {"event": "unit_setup", "ref": ticket_ref, "branch": branch},
    )

    unit_state.phase = "plan_checkpoint" if halt_after_planning else "build"
    save_run(project_root, run_state)

    prompt = build_prompt(
        ticket_ref, halt_after_planning=halt_after_planning, thorough=thorough
    )
    agent = run_cursor_agent(
        project_root=project_root,
        model=model,
        prompt=prompt,
        dry_run=False,
        **agent_call_limits(policy.limits),
    )
    unit_state.agent_id = agent.agent_id

    if agent.error:
        unit = UnitReport(
            ref=ticket_ref,
            kind="ticket",
            epic=str(epic) if epic else None,
            outcome="error",
            reason=agent.error,
            tokens=usage_dict(agent.usage),
            agent_id=agent.agent_id,
            run_id=agent.run_id,
        )
        report.add(unit)
        pause_run(
            project_root,
            run_state,
            reason=PAUSE_BLOCKED,
            detail=agent.error,
            ticket=ticket_ref,
        )
        raise FactoryHalt(SHUTDOWN_ERROR, agent.error)

    try:
        found = tickets_find(project_root, ticket_ref, policy=policy)
        tracker_id = str(found.get("tracker_id") or "").strip() or tracker_id
        ticket_type = str(found.get("type") or "").strip() or ticket_type
        ticket_title = str(found.get("title") or "").strip() or ticket_title
        plan_path = Path(found["plan"]) if found.get("plan") else plan_path
        done_checkpoint = (
            bool(found.get("done_checkpoint")) and policy.gates.done_checkpoint
        ) or done_checkpoint
    except FactoryHalt:
        pass

    plan_fm = read_frontmatter(plan_path) if plan_path else {}
    plan_status, plan_fm, result_path, status_from_result_only = _resolve_plan_status(
        project_root, ticket_ref, plan_path, plan_fm
    )

    if halt_after_planning:
        unit = UnitReport(
            ref=ticket_ref,
            kind="ticket",
            epic=str(epic) if epic else None,
            outcome="checkpoint",
            reason="plan_checkpoint: waiting for human plan approval",
            plan_status=plan_status or None,
            tokens=usage_dict(agent.usage),
            agent_id=agent.agent_id,
            run_id=agent.run_id,
        )
        report.add(unit)
        detail = f"ticket {ticket_ref}: plan checkpoint"
        report.next_steps = format_halt_reinvoke_steps(
            detail=(
                f"Approve the story/plan for {ticket_ref}, then re-invoke "
                f"(use -y to record story approval)."
            ),
            cli_args=cli_args,
            model=model,
        )
        report.shutdown = SHUTDOWN_PLAN_CHECKPOINT
        report.shutdown_detail = detail
        pause_run(
            project_root,
            run_state,
            reason=PAUSE_PLAN_CHECKPOINT,
            detail=detail,
            ticket=ticket_ref,
        )
        raise FactoryHalt(SHUTDOWN_PLAN_CHECKPOINT, detail)

    if plan_status == "blocked":
        artifact = result_path or (
            plan_path if plan_path and plan_path.is_file() else None
        )
        reason = blocked_reason_from_artifact(artifact, plan_fm)
        if reason == "blocked":
            reason = str(found.get("blocked_reason") or "blocked")
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
        report.add(unit)
        detail = f"ticket {ticket_ref}: {reason}"
        report.next_steps = format_blocked_redispatch_steps(
            ticket_ref=ticket_ref,
            reason=reason,
            artifact_path=artifact,
            plan_path=plan_path,
            status_from_result_only=status_from_result_only,
            model=model,
            cli_args=cli_args,
        )
        report.shutdown = SHUTDOWN_BLOCKED
        report.shutdown_detail = detail
        run_state.blocked_refs.append({"ref": ticket_ref, "reason": reason})
        pause_run(
            project_root,
            run_state,
            reason=PAUSE_BLOCKED,
            detail=detail,
            ticket=ticket_ref,
        )
        raise FactoryHalt(SHUTDOWN_BLOCKED, detail)

    if plan_status not in ("built", "done"):
        reason = f"unexpected plan status after agent: {plan_status or '(missing)'}"
        unit = UnitReport(
            ref=ticket_ref,
            kind="ticket",
            epic=str(epic) if epic else None,
            plan_status=plan_status or None,
            outcome="error",
            reason=reason,
            tokens=usage_dict(agent.usage),
            agent_id=agent.agent_id,
            run_id=agent.run_id,
        )
        report.add(unit)
        report.next_steps = format_halt_reinvoke_steps(
            detail=reason, cli_args=cli_args, model=model
        )
        pause_run(
            project_root,
            run_state,
            reason=PAUSE_BLOCKED,
            detail=reason,
            ticket=ticket_ref,
        )
        raise FactoryHalt(SHUTDOWN_ERROR, reason)

    # Harvest deferred before done-checkpoint so findings are not lost.
    deferred_items = plan_fm.get("deferred") or []
    if not isinstance(deferred_items, list):
        deferred_items = []
    deferred_count = 0
    if plan_path and deferred_items:
        deferred_count = append_deferred(plan_path, project_root, deferred_items)

    if done_checkpoint and not done_cleared:
        unit_state.extra["awaiting_done_confirm"] = True
        unit_state.phase = "done_checkpoint"
        save_run(project_root, run_state)
        unit = UnitReport(
            ref=ticket_ref,
            kind="ticket",
            epic=str(epic) if epic else None,
            plan_status=plan_status,
            outcome="checkpoint",
            reason="done_checkpoint: waiting for human continue",
            deferred_count=deferred_count,
            tokens=usage_dict(agent.usage),
            agent_id=agent.agent_id,
            run_id=agent.run_id,
        )
        report.add(unit)
        detail = f"ticket {ticket_ref}: done checkpoint"
        report.next_steps = format_halt_reinvoke_steps(
            detail=(
                f"Review the built work for {ticket_ref}, then re-invoke the same "
                "command to mark done and land (push/PR/merge)."
            ),
            cli_args=cli_args,
            model=model,
        )
        report.shutdown = SHUTDOWN_DONE_CHECKPOINT
        report.shutdown_detail = detail
        pause_run(
            project_root,
            run_state,
            reason=PAUSE_DONE_CHECKPOINT,
            detail=detail,
            ticket=ticket_ref,
        )
        raise FactoryHalt(SHUTDOWN_DONE_CHECKPOINT, detail)

    return _finish_built(
        project_root=project_root,
        report=report,
        policy=policy,
        run_state=run_state,
        unit_state=unit_state,
        ticket_ref=ticket_ref,
        epic=str(epic) if epic else None,
        ticket_type=ticket_type,
        ticket_title=ticket_title,
        tracker_id=tracker_id,
        plan_path=plan_path,
        plan_fm=plan_fm,
        plan_status=plan_status,
        no_push=no_push,
        dry_run=False,
        model=model,
        tokens=usage_dict(agent.usage),
        agent_id=agent.agent_id,
        run_id=agent.run_id,
        deferred_count=deferred_count,
    )


def _finish_built(
    *,
    project_root: Path,
    report: RunReport,
    policy: Policy,
    run_state: RunState,
    unit_state: UnitAttemptState,
    ticket_ref: str,
    epic: str | None,
    ticket_type: str | None,
    ticket_title: str | None,
    tracker_id: str | None,
    plan_path: Path | None,
    plan_fm: dict[str, Any],
    plan_status: str,
    no_push: bool,
    dry_run: bool,
    model: str,
    tokens: dict[str, int] | None,
    agent_id: str | None,
    run_id: str | None,
    deferred_count: int = 0,
) -> str | None:
    del plan_fm, model  # reserved for future verify soft-checks
    if deferred_count == 0 and plan_path:
        items = read_frontmatter(plan_path).get("deferred") or []
        if isinstance(items, list) and items:
            # Already harvested on first built pass; ignore duplicates.
            pass

    if policy.tickets.mark_done == "auto" and plan_path:
        tickets_mark_done(
            project_root,
            ticket_ref,
            plan_path,
            tracker_id=tracker_id,
            policy=policy,
        )

    unit = UnitReport(
        ref=ticket_ref,
        kind="ticket",
        epic=epic,
        plan_status=plan_status,
        outcome="done",
        deferred_count=deferred_count,
        tokens=tokens,
        agent_id=agent_id,
        run_id=run_id,
    )

    want_remote = policy.scm.remote == "pr-merge" and not no_push
    if want_remote and has_unpushed_or_new_commits(project_root):
        pr_url = ensure_push_pr_and_merge(
            project_root,
            epic=epic,
            refs=[ticket_ref],
            no_push=False,
            dry_run=dry_run,
            ticket_type=ticket_type,
            title=ticket_title,
            tracker_id=tracker_id,
            plan_path=plan_path,
            kind="ticket",
        )
        unit.pr_url = pr_url

    report.add(unit)
    log_cumulative_tokens(report)
    if ticket_ref not in run_state.completed_refs:
        run_state.completed_refs.append(ticket_ref)
    run_state.task_phases[ticket_ref] = str(Phase.DONE)
    unit_state.phase = "done"
    unit_state.outcome = "done"
    unit_state.extra.pop("awaiting_done_confirm", None)
    run_state.current_unit = None
    save_run(project_root, run_state)
    append_journal(
        project_root,
        run_state.run_id,
        {"event": "unit_done", "ref": ticket_ref, "pr": unit.pr_url},
    )

    if epic and epic_fully_done(project_root, epic, policy=policy):
        return epic
    return None
