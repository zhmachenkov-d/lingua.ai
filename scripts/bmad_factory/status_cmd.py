"""Rich status: factory runs + tickets board + open deferred entries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .deferred import list_open_deferred
from .policy import Policy, load_policy
from .run_state import RunState, format_run_brief, list_runs, load_run
from .tickets_io import tickets_status


def _board_section(project_root: Path, policy: Policy) -> dict[str, Any]:
    try:
        payload = tickets_status(project_root, policy=policy)
    except Exception as err:  # noqa: BLE001 — status should still print runs/deferred
        return {"error": str(err)}

    counts = payload.get("counts") or {}
    epics = payload.get("epics") or []
    tickets = payload.get("tickets") or []
    blocked = [
        {
            "ref": t.get("ref") or t.get("file"),
            "reason": t.get("blocked_reason") or "",
        }
        for t in tickets
        if t.get("status") == "blocked" or t.get("blocked_at")
    ]
    backlog = payload.get("backlog")
    backlog_counts: dict[str, Any] | None = None
    backlog_error = None
    if isinstance(backlog, dict):
        if backlog.get("error"):
            backlog_error = backlog.get("error")
        else:
            backlog_counts = backlog.get("counts") or {}

    return {
        "folder": payload.get("folder"),
        "counts": counts,
        "epics": [
            {
                "slug": e.get("slug"),
                "status": e.get("status"),
                "folder": e.get("folder"),
            }
            for e in epics
            if isinstance(e, dict)
        ],
        "blocked": blocked,
        "backlog_counts": backlog_counts,
        "backlog_error": backlog_error,
        "problems": payload.get("problems") or [],
    }


def _deferred_section(project_root: Path, policy: Policy) -> dict[str, Any]:
    open_entries = list_open_deferred(
        project_root, ledger_name=policy.sweep.ledger_name
    )
    items = [
        {
            "key": entry.key,
            "severity": entry.severity,
            "summary": entry.summary,
            "ledger": str(ledger),
        }
        for ledger, entry in open_entries
    ]
    by_sev: dict[str, int] = {}
    for item in items:
        sev = (item.get("severity") or "unset").lower()
        by_sev[sev] = by_sev.get(sev, 0) + 1
    return {"count": len(items), "by_severity": by_sev, "entries": items}


def _runs_section(
    project_root: Path, run_id: str | None
) -> list[dict[str, Any]] | dict[str, Any]:
    if run_id:
        state = load_run(project_root, run_id)
        return _run_dict(state)
    return [_run_dict(s) for s in list_runs(project_root)[:20]]


def _run_dict(state: RunState) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "status": state.status,
        "mode": state.mode,
        "pause_reason": state.pause_reason,
        "pause_detail": state.pause_detail,
        "pause_ticket": state.pause_ticket,
        "completed_refs": list(state.completed_refs),
        "ticket": state.ticket,
        "epic": state.epic,
        "model": state.model,
    }


def collect_status(project_root: Path, *, run_id: str | None = None) -> dict[str, Any]:
    policy = load_policy(project_root, create_if_missing=True)
    return {
        "runs": _runs_section(project_root, run_id),
        "board": _board_section(project_root, policy),
        "deferred": _deferred_section(project_root, policy),
    }


def format_status_human(data: dict[str, Any]) -> str:
    lines: list[str] = ["=== BMAD factory status ===", "", "## Runs"]
    runs = data.get("runs")
    if isinstance(runs, dict):
        lines.append(
            f"{runs.get('run_id')}  {runs.get('status')}  mode={runs.get('mode')}"
        )
        if runs.get("pause_reason"):
            lines.append(f"  pause_reason: {runs['pause_reason']}")
        if runs.get("pause_detail"):
            lines.append(f"  pause_detail: {runs['pause_detail']}")
        if runs.get("pause_ticket"):
            lines.append(f"  pause_ticket: {runs['pause_ticket']}")
        if runs.get("completed_refs"):
            lines.append(f"  completed: {', '.join(runs['completed_refs'])}")
    elif not runs:
        lines.append("(none)")
    else:
        for r in runs:
            brief = RunState(
                run_id=str(r.get("run_id") or ""),
                status=str(r.get("status") or ""),
                mode=str(r.get("mode") or ""),
                pause_reason=r.get("pause_reason"),
                pause_ticket=r.get("pause_ticket"),
                completed_refs=list(r.get("completed_refs") or []),
            )
            lines.append(format_run_brief(brief))

    lines.extend(["", "## Board"])
    board = data.get("board") or {}
    if board.get("error"):
        lines.append(f"error: {board['error']}")
    else:
        lines.append(f"folder: {board.get('folder') or '(unknown)'}")
        counts = board.get("counts") or {}
        if counts:
            bits = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            lines.append(f"counts: {bits}")
        epics = board.get("epics") or []
        if epics:
            lines.append("epics:")
            for e in epics:
                folder = e.get("folder")
                folder_bit = " (no folder)" if folder is None else ""
                lines.append(
                    f"  {e.get('slug')}  status={e.get('status') or ''}{folder_bit}"
                )
        blocked = board.get("blocked") or []
        if blocked:
            lines.append("blocked:")
            for b in blocked:
                reason = b.get("reason") or ""
                suffix = f" — {reason}" if reason else ""
                lines.append(f"  {b.get('ref')}{suffix}")
        bc = board.get("backlog_counts")
        if bc:
            bits = ", ".join(f"{k}={v}" for k, v in sorted(bc.items()))
            lines.append(f"backlog counts: {bits}")
        if board.get("backlog_error"):
            lines.append(f"backlog error: {board['backlog_error']}")
        problems = board.get("problems") or []
        if problems:
            lines.append("problems:")
            for p in problems:
                lines.append(f"  - {p}")

    lines.extend(["", "## Deferred"])
    deferred = data.get("deferred") or {}
    lines.append(f"open: {deferred.get('count', 0)}")
    by_sev = deferred.get("by_severity") or {}
    if by_sev:
        bits = ", ".join(f"{k}={v}" for k, v in sorted(by_sev.items()))
        lines.append(f"by severity: {bits}")
    for item in deferred.get("entries") or []:
        sev = item.get("severity") or "unset"
        lines.append(f"  [{sev}] {item.get('summary')}  key={item.get('key')}")

    return "\n".join(lines) + "\n"


def cmd_status(
    project_root: Path, *, run_id: str | None = None, as_json: bool = False
) -> int:
    data = collect_status(project_root, run_id=run_id)
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_status_human(data), end="", file=sys.stdout)
    return 0
