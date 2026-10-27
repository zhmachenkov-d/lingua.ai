"""tickets.py wrappers and store-aware mark-done."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .constants import (
    SHUTDOWN_ERROR,
    TICKETS_SCRIPT,
    OrchestratorHalt,
    log,
)
from .tracker import tracker_mark_done


def _tickets_bin(project_root: Path) -> list[str]:
    script = project_root / TICKETS_SCRIPT
    if not script.is_file():
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"missing {script}")
    return ["uv", "run", str(script), "--project-root", str(project_root)]


def tickets_cmd(project_root: Path, *args: str) -> dict[str, Any]:
    cmd = [*_tickets_bin(project_root), *args]
    log.debug("tickets cmd: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
    raw_out = (proc.stdout or "").strip()
    raw_err = (proc.stderr or "").strip()
    log.debug("tickets returncode=%s", proc.returncode)
    payload: dict[str, Any] | None = None
    for blob in (raw_out, raw_err):
        if not blob:
            continue
        try:
            payload = json.loads(blob)
            break
        except json.JSONDecodeError:
            continue
    if proc.returncode != 0:
        err = None
        if isinstance(payload, dict):
            err = payload.get("error")
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            err or raw_err or raw_out or f"tickets.py exited {proc.returncode}",
        )
    if not isinstance(payload, dict):
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"tickets.py returned non-JSON: {raw_out[:200]}"
        )
    return payload


def tickets_next(project_root: Path, folder: str | None = None) -> dict[str, Any]:
    args = ["next"]
    if folder:
        args.append(folder)
    args.append("--synced")
    return tickets_cmd(project_root, *args)


def tickets_find(
    project_root: Path, ref: str, folder: str | None = None
) -> dict[str, Any]:
    args = ["find"]
    if folder:
        args.extend([folder, ref])
    else:
        args.append(ref)
    return tickets_cmd(project_root, *args)


def tickets_status(project_root: Path, folder: str | None = None) -> dict[str, Any]:
    args = ["status"]
    if folder:
        args.append(folder)
    return tickets_cmd(project_root, *args)


def tickets_mirror(
    project_root: Path,
    items: list[dict[str, Any]],
    folder: str | None = None,
) -> dict[str, Any]:
    args = ["mirror"]
    if folder:
        args.append(folder)
    cmd = [*_tickets_bin(project_root), *args]
    log.info("tickets mirror folder=%s items=%s", folder, len(items))
    proc = subprocess.run(
        cmd,
        cwd=project_root,
        input=json.dumps(items),
        capture_output=True,
        text=True,
    )
    raw_out = (proc.stdout or "").strip()
    raw_err = (proc.stderr or "").strip()
    payload: dict[str, Any] | None = None
    for blob in (raw_out, raw_err):
        if not blob:
            continue
        try:
            payload = json.loads(blob)
            break
        except json.JSONDecodeError:
            continue
    if proc.returncode != 0:
        err = None
        if isinstance(payload, dict):
            err = payload.get("error")
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            err or raw_err or raw_out or f"tickets.py mirror exited {proc.returncode}",
        )
    if not isinstance(payload, dict):
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"tickets.py mirror returned non-JSON: {raw_out[:200]}"
        )
    return payload


def tickets_mark_done(
    project_root: Path,
    ref: str,
    plan_path: Path | None,
    *,
    tracker_id: str | None = None,
    folder: str | None = None,
) -> None:
    """Mark ticket done via tickets.py mark, or tracker write + mirror on store refusal."""
    args = ["mark"]
    if folder:
        args.extend([folder, ref, "done"])
    else:
        args.extend([ref, "done"])
    cmd = [*_tickets_bin(project_root), *args]
    log.info("mark done via tickets.py ref=%s", ref)
    proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
    if proc.returncode == 0:
        log.info("mark done succeeded via tickets.py ref=%s", ref)
        return
    err_blob = (proc.stderr or proc.stdout or "").strip()
    err_msg = err_blob
    try:
        err_msg = json.loads(err_blob).get("error", err_blob)
    except json.JSONDecodeError:
        pass
    if (
        plan_path
        and plan_path.is_file()
        and "change status through the store" in str(err_msg)
    ):
        log.info("mark refused by store; dispatching tracker write ref=%s", ref)
        tracker_mark_done(
            project_root,
            ref=ref,
            tracker_id=tracker_id,
            plan_path=plan_path,
            folder=folder,
        )
        return
    raise OrchestratorHalt(SHUTDOWN_ERROR, f"mark done failed: {err_msg}")
