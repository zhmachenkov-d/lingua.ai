"""CLI: --ticket / --epic / --backlog / --deferred / --resume / --stop / --status."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .agent import cancel_active_agent
from .constants import (
    DEFAULT_MODEL_ID,
    SHUTDOWN_COMPLETED,
    FactoryHalt,
    configure_logging,
    log,
)
from .deferred import continue_deferred
from .epic_closure import ACCEPT_VERDICTS, process_epic_closure
from .pick import (
    CLOSURE_REJECTED,
    EPIC_CLOSED,
    HALT_AWAITING_CLOSURE,
    HALT_EPIC_REJECTED,
    Dispatch,
    Halt,
    Phase,
    PickScope,
    Skip,
    decide_pick,
    plan_planned,
)
from .pipeline import process_ticket
from .plan_io import format_halt_reinvoke_steps, read_frontmatter
from .policy import load_policy
from .report import RunReport, format_token_cost_from_report
from .run_lock import (
    ProjectLock,
    RunLock,
    ensure_process_group,
    is_run_alive,
    kill_process_group,
    lock_holder_pid,
    stop_run_process,
)
from .run_state import (
    PAUSE_DONE_CHECKPOINT,
    PAUSE_PICK_EPIC_BOUNDARY,
    PAUSE_PICK_PLAN_CHECKPOINT,
    PAUSE_PLAN_CHECKPOINT,
    PAUSE_SIGNAL,
    PAUSE_STOPPED,
    RunState,
    classify_run,
    clear_pause,
    create_run,
    find_resumable_run,
    load_run,
    pause_run,
    save_run,
)
from .status_cmd import cmd_status
from .ticketmodel import NextView, StatusView
from .tickets_io import load_find_result, load_next_view, load_status_view


def resolve_project_root(raw: str | None) -> Path:
    if raw:
        root = Path(raw).resolve()
    else:
        here = Path.cwd().resolve()
        root = None
        for p in [here, *here.parents]:
            if (p / "_bmad").is_dir():
                root = p
                break
        if root is None:
            raise SystemExit(
                "no project root: pass --project-root (folder containing _bmad/)"
            )
    if not (root / "_bmad").is_dir():
        raise SystemExit(f"no _bmad/ under {root}")
    return root


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "BMAD factory — lean autonomous ticket/epic/backlog/deferred loop. "
            "HITL gates halt with next steps; re-invoke the same CLI args or "
            "use --resume RUN_ID to continue."
        )
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--ticket", metavar="REF", help="build a single ticket")
    g.add_argument("--epic", metavar="REF", help="build ready tickets in an epic")
    g.add_argument(
        "--backlog",
        action="store_true",
        help="build items from the initiative nested backlog/",
    )
    g.add_argument(
        "--deferred",
        action="store_true",
        help="triage deferred-work.md and build free-form bundles",
    )
    g.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="resume a paused or stale run by id",
    )
    g.add_argument(
        "--stop",
        metavar="RUN_ID",
        help="terminate a live run's process group and mark it paused",
    )
    g.add_argument(
        "--status",
        nargs="?",
        const="",
        default=None,
        metavar="RUN_ID",
        help="rich status (optional run_id)",
    )

    p.add_argument(
        "--model",
        default=DEFAULT_MODEL_ID,
        help="Cursor model id (default: auto with optimize_for=balanced)",
    )
    p.add_argument(
        "--project-root", default=None, help="project root containing _bmad/"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="resolve queue and print prompts only"
    )
    p.add_argument(
        "--no-push",
        action="store_true",
        help="skip git push / PR / merge even when policy scm.remote=pr-merge",
    )
    p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="non-interactive: auto-ack plan-checkpoint / epic-closure on re-invoke",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="write the final report / status JSON to stdout",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log factory steps at INFO",
    )
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="logging level (overrides --verbose; default WARNING)",
    )
    p.add_argument(
        "--no-prompt",
        action="store_true",
        help="with --deferred: build only decision-free bundles",
    )
    p.add_argument(
        "--only",
        metavar="KEY",
        action="append",
        default=None,
        help="with --deferred: only entries whose key contains KEY (repeatable)",
    )
    return p


def _configure_from_args(args: argparse.Namespace) -> None:
    if getattr(args, "log_level", None):
        log_level = args.log_level
    elif getattr(args, "verbose", False):
        log_level = "INFO"
    else:
        log_level = "WARNING"
    configure_logging(log_level)


def _finish_report(report: RunReport, *, as_json: bool) -> int:
    log.info(
        "factory finish shutdown=%s %s",
        report.shutdown,
        format_token_cost_from_report(report),
    )
    report.print_human(sys.stderr)
    if as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if report.shutdown == SHUTDOWN_COMPLETED:
        return 0
    return 1


def _pick_scope(*, ticket: str | None, epic: str | None, backlog: bool) -> PickScope:
    if backlog:
        return PickScope(backlog=True)
    if ticket:
        return PickScope(ref=ticket)
    if epic:
        return PickScope(epic=epic)
    return PickScope()


def _task_phases(run_state: RunState) -> dict[str, Phase]:
    out: dict[str, Phase] = {}
    for ref, raw in (run_state.task_phases or {}).items():
        try:
            out[ref] = Phase(raw)
        except ValueError:
            out[ref] = Phase.PENDING
    for ref in run_state.completed_refs:
        out.setdefault(ref, Phase.DONE)
    for ref in run_state.deferred_refs:
        out.setdefault(ref, Phase.DEFERRED)
    return out


def _record_phase(run_state: RunState, ref: str, phase: Phase) -> None:
    run_state.task_phases[ref] = str(phase)


def _cli_args_label(args: argparse.Namespace, run_state: RunState | None = None) -> str:
    if getattr(args, "resume", None) and run_state is not None:
        return f"--resume {run_state.run_id}"
    if args.ticket:
        return f"--ticket {args.ticket}"
    if args.epic:
        return f"--epic {args.epic}"
    if args.backlog:
        return "--backlog"
    if args.deferred:
        return "--deferred"
    if getattr(args, "resume", None):
        return f"--resume {args.resume}"
    return "--status"


def _apply_reinvoke_acks(
    run_state: RunState, *, yes: bool, project_root: Path, policy: Any
) -> None:
    """On re-invoke of a paused run, apply -y or detect cleared gates."""
    reason = run_state.pause_reason
    target = run_state.pause_ticket

    if reason in {PAUSE_PLAN_CHECKPOINT, PAUSE_PICK_PLAN_CHECKPOINT} and target:
        approved = False
        if yes:
            approved = True
        else:
            try:
                found = load_find_result(project_root, target, policy=policy)
                if plan_planned(found.row.status) or (
                    found.row.refined and found.row.ref in (target,)
                ):
                    if found.row.status not in {"", "draft"}:
                        approved = True
                plan = Path(found.plan) if found.plan else None
                if plan and plan.is_file():
                    fm = read_frontmatter(plan)
                    if plan_planned(str(fm.get("status") or "")):
                        approved = True
            except FactoryHalt:
                pass
        if approved and target not in run_state.ticket_story_approvals:
            run_state.ticket_story_approvals.append(target)
        if run_state.current_unit and run_state.current_unit.ref == target:
            run_state.current_unit.extra["plan_checkpoint_cleared"] = True
            run_state.current_unit.phase = "build"

    if reason == PAUSE_DONE_CHECKPOINT and target:
        if run_state.current_unit and run_state.current_unit.ref == target:
            run_state.current_unit.extra["done_checkpoint_cleared"] = True
            run_state.current_unit.phase = "landing"

    if reason == PAUSE_PICK_EPIC_BOUNDARY and target:
        if yes or target not in run_state.ticket_epic_closure_acked:
            closed = False
            try:
                status = load_status_view(project_root, policy=policy)
                for epic in status.epics:
                    if epic.slug == target and epic.status in EPIC_CLOSED:
                        closed = True
                        break
            except FactoryHalt:
                pass
            if yes or closed:
                if target not in run_state.ticket_epic_closure_acked:
                    run_state.ticket_epic_closure_acked.append(target)


def _views_for_mode(
    project_root: Path,
    *,
    mode: str,
    policy: Any,
) -> tuple[NextView, StatusView]:
    next_view = load_next_view(project_root, policy=policy)
    status_view = load_status_view(project_root, policy=policy)
    if mode != "backlog":
        return next_view, status_view
    if next_view.backlog_error:
        raise FactoryHalt(
            "backlog-fault",
            f"backlog unreadable: {next_view.backlog_error}",
        )
    if next_view.backlog is None:
        raise FactoryHalt(
            "backlog-fault",
            "no nested backlog/ folder on the active initiative",
        )
    if status_view.backlog is None or status_view.backlog_error:
        raise FactoryHalt(
            "backlog-fault",
            status_view.backlog_error or "no nested backlog status view",
        )
    return next_view.backlog, status_view.backlog


def _execute_pick_loop(
    *,
    project_root: Path,
    report: RunReport,
    policy: Any,
    run_state: RunState,
    model: str,
    dry_run: bool,
    no_push: bool,
    ticket: str | None,
    epic: str | None,
    backlog: bool,
    cli_label: str,
) -> None:
    scope = _pick_scope(ticket=ticket, epic=epic, backlog=backlog)
    mode = run_state.mode

    while True:
        if run_state.status == "paused":
            return

        next_view, status_view = _views_for_mode(project_root, mode=mode, policy=policy)
        decision = decide_pick(
            next_view,
            status_view,
            _task_phases(run_state),
            run_state.ticket_epic_closures,
            frozenset(run_state.ticket_story_approvals),
            scope,
            acked=frozenset(run_state.ticket_epic_closure_acked),
        )

        if isinstance(decision, Skip):
            log.info(
                "pick skip reason=%s held=%s waiting=%s",
                decision.reason,
                decision.held,
                decision.waiting,
            )
            report.shutdown = SHUTDOWN_COMPLETED
            run_state.status = "completed"
            save_run(project_root, run_state)
            return

        if isinstance(decision, Halt):
            if decision.cause == HALT_AWAITING_CLOSURE and decision.key:
                log.info(
                    "pick epic-boundary auto-closure key=%s detail=%s",
                    decision.key,
                    decision.detail,
                )
                result = process_epic_closure(
                    project_root=project_root,
                    epic_slug=decision.key,
                    report=report,
                    policy=policy,
                    run_state=run_state,
                    model=model,
                    dry_run=dry_run,
                )
                if dry_run:
                    report.shutdown = SHUTDOWN_COMPLETED
                    run_state.status = "completed"
                    save_run(project_root, run_state)
                    return
                if result.closed:
                    verdict = result.verdict or "accepted"
                    run_state.ticket_epic_closures[decision.key] = verdict
                    if decision.key not in run_state.ticket_epic_closure_acked:
                        run_state.ticket_epic_closure_acked.append(decision.key)
                    save_run(project_root, run_state)
                    continue
                refuse_verdict = result.verdict
                if refuse_verdict in ACCEPT_VERDICTS:
                    # Close failed after an accepting verdict — keep verdict, do not ack.
                    run_state.ticket_epic_closures[decision.key] = refuse_verdict
                else:
                    run_state.ticket_epic_closures[decision.key] = CLOSURE_REJECTED
                detail = result.detail or decision.detail
                log.info(
                    "pick halt cause=%s stage=%s key=%s detail=%s",
                    HALT_EPIC_REJECTED,
                    decision.stage,
                    decision.key,
                    detail,
                )
                pause_run(
                    project_root,
                    run_state,
                    reason=decision.stage,
                    detail=detail,
                    ticket=decision.key or None,
                )
                report.shutdown = HALT_EPIC_REJECTED
                report.shutdown_detail = detail
                report.next_steps = format_halt_reinvoke_steps(
                    detail=detail,
                    cli_args=cli_label,
                    model=model,
                    run_id=run_state.run_id,
                )
                save_run(project_root, run_state)
                raise FactoryHalt(HALT_EPIC_REJECTED, detail)

            log.info(
                "pick halt cause=%s stage=%s key=%s detail=%s",
                decision.cause,
                decision.stage,
                decision.key,
                decision.detail,
            )
            pause_run(
                project_root,
                run_state,
                reason=decision.stage,
                detail=decision.detail,
                ticket=decision.key or None,
            )
            report.shutdown = decision.cause
            report.shutdown_detail = decision.detail
            report.next_steps = format_halt_reinvoke_steps(
                detail=decision.detail,
                cli_args=cli_label,
                model=model,
                run_id=run_state.run_id,
            )
            save_run(project_root, run_state)
            raise FactoryHalt(decision.cause, decision.detail)

        assert isinstance(decision, Dispatch)
        ref = decision.ref
        log.info("pick dispatch ref=%s notes=%s", ref, len(decision.notes))
        if ref in run_state.seen_refs and ref not in run_state.deferred_refs:
            current = run_state.current_unit
            if not (current and current.ref == ref):
                raise FactoryHalt(
                    "error",
                    f"ready ticket {ref} already seen this run; refusing to loop",
                )
        if ref not in run_state.seen_refs:
            run_state.seen_refs.append(ref)
        save_run(project_root, run_state)

        if dry_run:
            process_ticket(
                project_root=project_root,
                ref=ref,
                report=report,
                model=model,
                dry_run=True,
                no_push=no_push,
                policy=policy,
                run_state=run_state,
            )
            report.shutdown = SHUTDOWN_COMPLETED
            run_state.status = "completed"
            save_run(project_root, run_state)
            return

        _record_phase(run_state, ref, Phase.DEV_RUNNING)
        save_run(project_root, run_state)
        done_epic = process_ticket(
            project_root=project_root,
            ref=ref,
            report=report,
            model=model,
            dry_run=False,
            no_push=no_push,
            policy=policy,
            run_state=run_state,
        )
        if run_state.status == "paused":
            return

        _record_phase(run_state, ref, Phase.DONE)
        if done_epic and done_epic not in run_state.committed_epics:
            run_state.committed_epics.append(done_epic)
        save_run(project_root, run_state)

        if ticket:
            report.shutdown = SHUTDOWN_COMPLETED
            run_state.status = "completed"
            save_run(project_root, run_state)
            return


class _RunSession:
    """Holds locks + signal state for one factory invocation."""

    def __init__(
        self,
        project_root: Path,
        run_state: RunState,
        *,
        project_lock: ProjectLock,
        run_lock: RunLock,
        pgid: int,
    ) -> None:
        self.project_root = project_root
        self.run_state = run_state
        self.project_lock = project_lock
        self.run_lock = run_lock
        self.pgid = pgid
        self._prev_sigint: Any = None
        self._prev_sigterm: Any = None
        self._cleaning = False
        self._released = False

    def install(self) -> None:
        self._prev_sigint = signal.signal(signal.SIGINT, self._on_signal)
        self._prev_sigterm = signal.signal(signal.SIGTERM, self._on_signal)
        atexit.register(self.release_locks)

    def _on_signal(self, signum: int, _frame: Any) -> None:
        exit_code = 130 if signum == signal.SIGINT else 143
        self.shutdown_for_signal(exit_code=exit_code)

    def shutdown_for_signal(self, *, exit_code: int) -> None:
        if self._cleaning:
            return
        self._cleaning = True
        # Ignore further signals while we clean up (SIGKILL still wins).
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        log.warning(
            "signal received — cancelling agent and terminating children pgid=%s",
            self.pgid,
        )
        try:
            cancel_active_agent()
        except Exception:  # noqa: BLE001 — best-effort
            pass
        try:
            if self.pgid > 0:
                kill_process_group(self.pgid, term_timeout_s=5.0)
        except Exception as err:  # noqa: BLE001
            log.warning("child cleanup during signal failed: %s", err)
        try:
            if self.run_state.status == "running":
                pause_run(
                    self.project_root,
                    self.run_state,
                    reason=PAUSE_SIGNAL,
                    detail="interrupted",
                )
        except Exception as err:  # noqa: BLE001
            log.warning("pause_run during signal failed: %s", err)
        self.release_locks()
        os._exit(exit_code)

    def release_locks(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            self.run_lock.release()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.project_lock.release()
        except Exception:  # noqa: BLE001
            pass

    def restore_signals(self) -> None:
        if self._prev_sigint is not None:
            signal.signal(signal.SIGINT, self._prev_sigint)
        if self._prev_sigterm is not None:
            signal.signal(signal.SIGTERM, self._prev_sigterm)


def _acquire_session(project_root: Path, run_state: RunState) -> _RunSession:
    pgid = ensure_process_group()
    project_lock = ProjectLock(project_root)
    run_lock = RunLock(project_root, run_state.run_id)
    project_lock.acquire(run_id=run_state.run_id)
    try:
        run_lock.acquire()
    except Exception:
        project_lock.release()
        raise
    session = _RunSession(
        project_root,
        run_state,
        project_lock=project_lock,
        run_lock=run_lock,
        pgid=pgid,
    )
    session.install()
    return session


def _ensure_paused_on_halt(
    project_root: Path, run_state: RunState, halt: FactoryHalt
) -> None:
    if run_state.status == "running":
        pause_run(
            project_root,
            run_state,
            reason=halt.shutdown,
            detail=halt.detail,
            ticket=run_state.pause_ticket
            or (run_state.current_unit.ref if run_state.current_unit else None),
        )


def _continue_run(
    *,
    project_root: Path,
    report: RunReport,
    policy: Any,
    run_state: RunState,
    cli_label: str,
) -> None:
    mode = run_state.mode
    if (
        run_state.current_unit
        and run_state.current_unit.ref
        and run_state.current_unit.phase not in {"pending", "setup", "", None, "done"}
    ):
        ref = run_state.current_unit.ref
        process_ticket(
            project_root=project_root,
            ref=ref,
            report=report,
            model=run_state.model,
            dry_run=run_state.dry_run,
            no_push=run_state.no_push,
            policy=policy,
            run_state=run_state,
        )
        if run_state.status == "paused":
            return
        _record_phase(run_state, ref, Phase.DONE)
        if mode == "ticket":
            report.shutdown = SHUTDOWN_COMPLETED
            run_state.status = "completed"
            save_run(project_root, run_state)
            return

    _execute_pick_loop(
        project_root=project_root,
        report=report,
        policy=policy,
        run_state=run_state,
        model=run_state.model,
        dry_run=run_state.dry_run,
        no_push=run_state.no_push,
        ticket=run_state.ticket if mode == "ticket" else None,
        epic=run_state.epic if mode == "epic" else None,
        backlog=mode == "backlog",
        cli_label=cli_label,
    )


def _prepare_resumed_state(
    project_root: Path,
    run_state: RunState,
    args: argparse.Namespace,
    policy: Any,
) -> RunState:
    if is_run_alive(project_root, run_state.run_id):
        pid = lock_holder_pid(project_root, run_state.run_id)
        raise FactoryHalt(
            "error",
            f"run still live (pid={pid or '?'}); use --stop first",
        )
    classified = classify_run(project_root, run_state)
    if classified not in {"paused", "stale"}:
        raise FactoryHalt(
            "error",
            f"run {run_state.run_id} is not resumable (classified={classified})",
        )
    _apply_reinvoke_acks(
        run_state, yes=args.yes, project_root=project_root, policy=policy
    )
    run_state.yes = bool(args.yes or run_state.yes)
    run_state.no_push = bool(args.no_push or run_state.no_push)
    run_state.dry_run = bool(args.dry_run or run_state.dry_run)
    if args.model and args.model != DEFAULT_MODEL_ID:
        run_state.model = args.model
    clear_pause(project_root, run_state)
    return run_state


def _run_with_session(
    *,
    project_root: Path,
    run_state: RunState,
    report: RunReport,
    args: argparse.Namespace,
    body: Callable[[], None],
    cli_label: str,
) -> int:
    try:
        session = _acquire_session(project_root, run_state)
    except FactoryHalt as halt:
        # Lock failure after create/load must not leave status=running.
        report.shutdown = halt.shutdown
        report.shutdown_detail = halt.detail
        report.next_steps = format_halt_reinvoke_steps(
            detail=halt.detail or halt.shutdown,
            cli_args=cli_label,
            model=run_state.model,
            run_id=run_state.run_id,
        )
        _ensure_paused_on_halt(project_root, run_state, halt)
        run_state.report = report.to_dict()
        save_run(project_root, run_state)
        print(f"run_id: {run_state.run_id}", file=sys.stderr)
        return _finish_report(report, as_json=args.json)

    try:
        try:
            body()
        except FactoryHalt as halt:
            report.shutdown = halt.shutdown
            report.shutdown_detail = halt.detail
            if not report.next_steps:
                report.next_steps = format_halt_reinvoke_steps(
                    detail=halt.detail or halt.shutdown,
                    cli_args=cli_label,
                    model=run_state.model,
                    run_id=run_state.run_id,
                )
            _ensure_paused_on_halt(project_root, run_state, halt)
            run_state.report = report.to_dict()
            save_run(project_root, run_state)
        except KeyboardInterrupt:
            session.shutdown_for_signal(exit_code=130)
        run_state.report = report.to_dict()
        save_run(project_root, run_state)
        print(f"run_id: {run_state.run_id}", file=sys.stderr)
        return _finish_report(report, as_json=args.json)
    finally:
        session.restore_signals()
        session.release_locks()


def cmd_build(args: argparse.Namespace) -> int:
    project_root = resolve_project_root(args.project_root)
    policy = load_policy(project_root)
    report = RunReport()
    if args.ticket:
        mode = "ticket"
    elif args.epic:
        mode = "epic"
    else:
        mode = "backlog"

    existing = find_resumable_run(
        project_root, mode=mode, ticket=args.ticket, epic=args.epic
    )
    if existing is not None:
        log.info(
            "re-invoking paused/stale run_id=%s reason=%s classified=%s",
            existing.run_id,
            existing.pause_reason,
            classify_run(project_root, existing),
        )
        run_state = _prepare_resumed_state(project_root, existing, args, policy)
    else:
        run_state = create_run(
            project_root,
            mode=mode,
            model=args.model,
            dry_run=args.dry_run,
            yes=args.yes,
            no_push=args.no_push,
            ticket=args.ticket,
            epic=args.epic,
            target_branch=policy.scm.target_branch,
        )

    cli_label = _cli_args_label(args, run_state)
    log.info(
        "factory start mode=%s run_id=%s root=%s model=%s",
        mode,
        run_state.run_id,
        project_root,
        run_state.model,
    )

    def body() -> None:
        _continue_run(
            project_root=project_root,
            report=report,
            policy=policy,
            run_state=run_state,
            cli_label=cli_label,
        )

    return _run_with_session(
        project_root=project_root,
        run_state=run_state,
        report=report,
        args=args,
        body=body,
        cli_label=cli_label,
    )


def cmd_deferred(args: argparse.Namespace) -> int:
    project_root = resolve_project_root(args.project_root)
    policy = load_policy(project_root)
    report = RunReport()

    existing = find_resumable_run(project_root, mode="deferred")
    if existing is not None:
        log.info(
            "re-invoking deferred run_id=%s classified=%s",
            existing.run_id,
            classify_run(project_root, existing),
        )
        run_state = _prepare_resumed_state(project_root, existing, args, policy)
    else:
        run_state = create_run(
            project_root,
            mode="deferred",
            model=args.model,
            dry_run=args.dry_run,
            yes=args.yes,
            no_push=args.no_push,
        )

    cli_label = _cli_args_label(args, run_state)

    def body() -> None:
        continue_deferred(
            project_root=project_root,
            report=report,
            policy=policy,
            run_state=run_state,
            model=run_state.model,
            dry_run=run_state.dry_run,
            no_prompt=args.no_prompt,
            no_push=run_state.no_push,
            only=getattr(args, "only", None),
        )
        if run_state.status != "paused":
            report.shutdown = SHUTDOWN_COMPLETED

    return _run_with_session(
        project_root=project_root,
        run_state=run_state,
        report=report,
        args=args,
        body=body,
        cli_label=cli_label,
    )


def cmd_resume(args: argparse.Namespace) -> int:
    project_root = resolve_project_root(args.project_root)
    policy = load_policy(project_root)
    report = RunReport()
    run_state = load_run(project_root, args.resume)
    run_state = _prepare_resumed_state(project_root, run_state, args, policy)
    cli_label = _cli_args_label(args, run_state)
    log.info(
        "factory resume run_id=%s mode=%s model=%s",
        run_state.run_id,
        run_state.mode,
        run_state.model,
    )

    def body() -> None:
        if run_state.mode == "deferred":
            continue_deferred(
                project_root=project_root,
                report=report,
                policy=policy,
                run_state=run_state,
                model=run_state.model,
                dry_run=run_state.dry_run,
                no_prompt=args.no_prompt,
                no_push=run_state.no_push,
                only=getattr(args, "only", None),
            )
            if run_state.status != "paused":
                report.shutdown = SHUTDOWN_COMPLETED
        else:
            _continue_run(
                project_root=project_root,
                report=report,
                policy=policy,
                run_state=run_state,
                cli_label=cli_label,
            )

    return _run_with_session(
        project_root=project_root,
        run_state=run_state,
        report=report,
        args=args,
        body=body,
        cli_label=cli_label,
    )


def cmd_stop(args: argparse.Namespace) -> int:
    project_root = resolve_project_root(args.project_root)
    run_id = args.stop
    run_state = load_run(project_root, run_id)
    result = stop_run_process(project_root, run_id, term_timeout_s=10.0)
    log.info("stop_run_process run_id=%s result=%s", run_id, result)
    # Reload in case the dying process wrote state; then force pause if needed.
    try:
        run_state = load_run(project_root, run_id)
    except FactoryHalt:
        pass
    if run_state.status == "running":
        pause_run(
            project_root,
            run_state,
            reason=PAUSE_STOPPED,
            detail="stopped by --stop",
        )
    print(
        f"run_id: {run_id}  status={run_state.status}  stop={result}",
        file=sys.stderr,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "status": run_state.status,
                    "pause_reason": run_state.pause_reason,
                    "stop": result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_from_args(args)

    if args.status is not None:
        project_root = resolve_project_root(args.project_root)
        run_id = args.status or None
        return cmd_status(project_root, run_id=run_id, as_json=args.json)

    if args.stop:
        return cmd_stop(args)

    if args.resume:
        return cmd_resume(args)

    if args.deferred:
        return cmd_deferred(args)

    return cmd_build(args)
