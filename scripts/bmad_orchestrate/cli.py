"""CLI: run / resume / resolve / confirm / sweep / status."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .constants import (
    DEFAULT_MODEL_ID,
    SHUTDOWN_COMPLETED,
    OrchestratorHalt,
    configure_logging,
    log,
)
from .pipeline import (
    maybe_retro_after,
    process_ticket,
)
from .policy import load_policy
from .report import RunReport, format_token_cost_from_report
from .run_state import (
    confirm_parked,
    create_run,
    format_status,
    list_runs,
    load_run,
    pause_run,
    resolve_blocked,
    resume_armed,
    save_run,
)
from .sweep import run_sweep
from .tickets_io import load_next_view, load_status_view
from .tickets_source import (
    Dispatch,
    Halt,
    Phase,
    PickScope,
    Skip,
    decide_pick,
)


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


def _add_common_run_flags(p: argparse.ArgumentParser) -> None:
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
        help="skip git push / PR path even when policy scm.remote=pr",
    )
    p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="non-interactive: auto-confirm where policy allows",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="write the final run report JSON to stdout",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="log orchestration steps at INFO",
    )
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="logging level (overrides --verbose; default WARNING)",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "BMAD Cursor build orchestrator (ticket-tree loop). "
            "Python owns queueing, gates, verify, commit, retries; "
            "Cursor agents run bmad-build-auto / review / retrospective / sweep triage."
        )
    )
    sub = p.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="start a new orchestration run")
    g = run_p.add_mutually_exclusive_group()
    g.add_argument("--ticket", metavar="REF", help="orchestrate a single ticket")
    g.add_argument(
        "--epic", metavar="REF", help="orchestrate all ready tickets in an epic"
    )
    _add_common_run_flags(run_p)

    resume_p = sub.add_parser("resume", help="resume a paused run")
    resume_p.add_argument("run_id", help="run id under .bmad-orchestrate/runs/")
    _add_common_run_flags(resume_p)

    resolve_p = sub.add_parser(
        "resolve", help="re-arm a blocked/plateau/escalation unit and resume"
    )
    resolve_p.add_argument("run_id")
    resolve_p.add_argument("--ticket", metavar="REF", default=None)
    _add_common_run_flags(resolve_p)

    confirm_p = sub.add_parser(
        "confirm", help="confirm a checkpoint / epic-boundary / refine pause and resume"
    )
    confirm_p.add_argument("run_id")
    confirm_p.add_argument("--ticket", metavar="REF", default=None)
    _add_common_run_flags(confirm_p)

    sweep_p = sub.add_parser("sweep", help="triage and build deferred-work bundles")
    sweep_p.add_argument(
        "--no-prompt",
        action="store_true",
        help="build only decision-free bundles (no TTY prompts)",
    )
    sweep_p.add_argument(
        "--only",
        metavar="KEY",
        action="append",
        default=None,
        help="only process deferred entries whose key contains KEY (repeatable)",
    )
    _add_common_run_flags(sweep_p)

    status_p = sub.add_parser("status", help="show run status")
    status_p.add_argument("run_id", nargs="?", default=None)
    status_p.add_argument("--project-root", default=None)
    status_p.add_argument("-v", "--verbose", action="store_true")
    status_p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
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
        "orchestrate finish shutdown=%s %s",
        report.shutdown,
        format_token_cost_from_report(report),
    )
    report.print_human(sys.stderr)
    if as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if report.shutdown == SHUTDOWN_COMPLETED:
        return 0
    return 1


def _pick_scope(*, ticket: str | None, epic: str | None) -> PickScope:
    if ticket:
        return PickScope(ref=ticket)
    if epic:
        return PickScope(epic=epic)
    return PickScope()


def _task_phases(run_state) -> dict[str, Phase]:
    out: dict[str, Phase] = {}
    for ref, raw in (run_state.task_phases or {}).items():
        try:
            out[ref] = Phase(raw)
        except ValueError:
            out[ref] = Phase.PENDING
    # Deferred / completed refs also count as touched.
    for ref in run_state.completed_refs:
        out.setdefault(ref, Phase.DONE)
    for ref in run_state.deferred_refs:
        out.setdefault(ref, Phase.DEFERRED)
    return out


def _record_phase(run_state, ref: str, phase: Phase) -> None:
    run_state.task_phases[ref] = str(phase)


def _execute_run_loop(
    *,
    project_root: Path,
    report: RunReport,
    policy,
    run_state,
    model: str,
    dry_run: bool,
    no_push: bool,
    yes: bool,
    ticket: str | None,
    epic: str | None,
) -> None:
    """Drive the ticket-tree pick loop via :func:`decide_pick`."""
    del yes  # refine/hitl now halt via decide_pick; no interactive refine gate
    retros_done = set(run_state.retros_done)
    scope = _pick_scope(ticket=ticket, epic=epic)

    while True:
        if run_state.status == "paused":
            return

        next_view = load_next_view(project_root)
        status_view = load_status_view(project_root)
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
            save_run(project_root, run_state)
            raise OrchestratorHalt(decision.cause, decision.detail)

        assert isinstance(decision, Dispatch)
        ref = decision.ref
        log.info("pick dispatch ref=%s notes=%s", ref, len(decision.notes))
        if ref in run_state.seen_refs and ref not in run_state.deferred_refs:
            raise OrchestratorHalt(
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
            # Mid-pipeline pause (plan/done checkpoint, blocked, plateau).
            if run_state.pause_reason in {"blocked", "escalation", "error"}:
                _record_phase(run_state, ref, Phase.ESCALATED)
            elif run_state.pause_reason == "plateau_deferred":
                _record_phase(run_state, ref, Phase.DEFERRED)
            save_run(project_root, run_state)
            return

        _record_phase(run_state, ref, Phase.DONE)
        if done_epic and done_epic not in run_state.committed_epics:
            run_state.committed_epics.append(done_epic)
        save_run(project_root, run_state)

        maybe_retro_after(
            done_epic,
            project_root=project_root,
            report=report,
            model=model,
            dry_run=False,
            no_push=no_push,
            retros_done=retros_done,
            policy=policy,
            run_state=run_state,
        )
        run_state.retros_done = list(retros_done)
        save_run(project_root, run_state)
        if run_state.status == "paused":
            return

        # Single-ticket mode finishes after one successful dispatch.
        if ticket:
            report.shutdown = SHUTDOWN_COMPLETED
            run_state.status = "completed"
            save_run(project_root, run_state)
            return


def cmd_run(args: argparse.Namespace) -> int:
    project_root = resolve_project_root(args.project_root)
    policy = load_policy(project_root)
    report = RunReport()
    if args.ticket:
        mode = "ticket"
    elif args.epic:
        mode = "epic"
    else:
        mode = "all"
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
    log.info(
        "orchestrate start mode=%s run_id=%s root=%s model=%s",
        mode,
        run_state.run_id,
        project_root,
        args.model,
    )
    try:
        _execute_run_loop(
            project_root=project_root,
            report=report,
            policy=policy,
            run_state=run_state,
            model=args.model,
            dry_run=args.dry_run,
            no_push=args.no_push,
            yes=args.yes,
            ticket=args.ticket,
            epic=args.epic,
        )
    except OrchestratorHalt as halt:
        report.shutdown = halt.shutdown
        report.shutdown_detail = halt.detail
        if run_state.status != "paused":
            log.warning(
                "orchestrate halt shutdown=%s detail=%s", halt.shutdown, halt.detail
            )
        run_state.report = report.to_dict()
        save_run(project_root, run_state)
    run_state.report = report.to_dict()
    save_run(project_root, run_state)
    print(f"run_id: {run_state.run_id}", file=sys.stderr)
    return _finish_report(report, as_json=args.json)


def cmd_resume(args: argparse.Namespace, *, after_resolve: bool = False) -> int:
    project_root = resolve_project_root(args.project_root)
    policy = load_policy(project_root)
    report = RunReport()
    run_state = load_run(project_root, args.run_id)
    if not after_resolve:
        resume_armed(project_root, run_state)
    model = getattr(args, "model", None) or run_state.model
    dry_run = bool(getattr(args, "dry_run", False) or run_state.dry_run)
    no_push = bool(getattr(args, "no_push", False) or run_state.no_push)
    yes = bool(getattr(args, "yes", False) or run_state.yes)
    ticket = run_state.ticket
    epic = run_state.epic
    mode = run_state.mode
    # Mid-pipeline unit resume: continue the in-flight ticket first.
    if (
        run_state.current_unit
        and run_state.current_unit.ref
        and mode != "sweep"
        and run_state.current_unit.phase
        not in {"pending", "setup", "", None}
    ):
        ticket = run_state.current_unit.ref
        try:
            process_ticket(
                project_root=project_root,
                ref=ticket,
                report=report,
                model=model,
                dry_run=dry_run,
                no_push=no_push,
                policy=policy,
                run_state=run_state,
            )
            if run_state.status == "paused":
                run_state.report = report.to_dict()
                save_run(project_root, run_state)
                return _finish_report(report, as_json=bool(getattr(args, "json", False)))
            _record_phase(run_state, ticket, Phase.DONE)
            # Fall through into pick loop for remaining work (unless ticket mode).
            if mode == "ticket":
                report.shutdown = SHUTDOWN_COMPLETED
                run_state.status = "completed"
                save_run(project_root, run_state)
                return _finish_report(
                    report, as_json=bool(getattr(args, "json", False))
                )
            ticket = None
        except OrchestratorHalt as halt:
            report.shutdown = halt.shutdown
            report.shutdown_detail = halt.detail
            run_state.report = report.to_dict()
            save_run(project_root, run_state)
            return _finish_report(report, as_json=bool(getattr(args, "json", False)))
    try:
        _execute_run_loop(
            project_root=project_root,
            report=report,
            policy=policy,
            run_state=run_state,
            model=model,
            dry_run=dry_run,
            no_push=no_push,
            yes=yes,
            ticket=ticket if mode == "ticket" else None,
            epic=epic if mode == "epic" else None,
        )
    except OrchestratorHalt as halt:
        report.shutdown = halt.shutdown
        report.shutdown_detail = halt.detail
        run_state.report = report.to_dict()
        save_run(project_root, run_state)
    run_state.report = report.to_dict()
    save_run(project_root, run_state)
    return _finish_report(report, as_json=bool(getattr(args, "json", False)))


def cmd_resolve(args: argparse.Namespace) -> int:
    project_root = resolve_project_root(args.project_root)
    run_state = load_run(project_root, args.run_id)
    resolve_blocked(project_root, run_state, ticket=args.ticket)
    return cmd_resume(args, after_resolve=True)


def cmd_confirm(args: argparse.Namespace) -> int:
    project_root = resolve_project_root(args.project_root)
    run_state = load_run(project_root, args.run_id)
    confirm_parked(project_root, run_state, ticket=args.ticket)
    return cmd_resume(args, after_resolve=True)


def cmd_sweep(args: argparse.Namespace) -> int:
    project_root = resolve_project_root(args.project_root)
    policy = load_policy(project_root)
    report = RunReport()
    try:
        run_state = run_sweep(
            project_root=project_root,
            report=report,
            policy=policy,
            model=args.model,
            dry_run=args.dry_run,
            no_prompt=args.no_prompt,
            no_push=args.no_push,
            yes=args.yes,
            only=getattr(args, "only", None),
        )
        report.shutdown = SHUTDOWN_COMPLETED
        print(f"run_id: {run_state.run_id}", file=sys.stderr)
    except OrchestratorHalt as halt:
        report.shutdown = halt.shutdown
        report.shutdown_detail = halt.detail
    return _finish_report(report, as_json=args.json)


def cmd_status(args: argparse.Namespace) -> int:
    project_root = resolve_project_root(args.project_root)
    if args.run_id:
        state = load_run(project_root, args.run_id)
        print(format_status(state), end="")
        return 0
    runs = list_runs(project_root)
    if not runs:
        print("no runs", file=sys.stderr)
        return 0
    for state in runs[:20]:
        pause = f" pause={state.pause_reason}" if state.pause_reason else ""
        print(f"{state.run_id}  {state.status}  mode={state.mode}{pause}")
    return 0


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    subcommands = {"run", "resume", "resolve", "confirm", "sweep", "status"}
    # Compat: bare invocation without subcommand keeps today's `run` semantics.
    # Keep explicit top-level --help/-h on the root parser (lists subcommands).
    if raw in (["-h"], ["--help"]):
        build_parser().print_help()
        return 0
    if not raw or raw[0] not in subcommands:
        raw = ["run", *raw]

    parser = build_parser()
    args = parser.parse_args(raw)
    _configure_from_args(args)
    command = args.command or "run"

    if command == "run":
        return cmd_run(args)
    if command == "resume":
        return cmd_resume(args)
    if command == "resolve":
        return cmd_resolve(args)
    if command == "confirm":
        return cmd_confirm(args)
    if command == "sweep":
        return cmd_sweep(args)
    if command == "status":
        return cmd_status(args)
    parser.error(f"unknown command {command}")
    return 2
