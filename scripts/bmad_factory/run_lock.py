"""Project-wide and per-run flock locks with PID/PGID liveness."""

from __future__ import annotations

import fcntl
import os
import signal
import time
from pathlib import Path
from typing import TextIO

from .constants import POLICY_DIRNAME, RUNS_DIRNAME, SHUTDOWN_ERROR, FactoryHalt, log

FACTORY_LOCK_NAME = "factory.lock"
RUN_LOCK_NAME = "run.lock"


def factory_lock_path(project_root: Path) -> Path:
    return project_root / POLICY_DIRNAME / FACTORY_LOCK_NAME


def run_lock_path(project_root: Path, run_id: str) -> Path:
    return project_root / POLICY_DIRNAME / RUNS_DIRNAME / run_id / RUN_LOCK_NAME


def _read_lock_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _parse_pid(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        pid = int(raw)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def project_holder(project_root: Path) -> tuple[int, str] | None:
    """Return ``(pid, run_id)`` from ``factory.lock`` if present (may be stale)."""
    lines = _read_lock_lines(factory_lock_path(project_root))
    if not lines:
        return None
    pid = _parse_pid(lines[0])
    if pid is None:
        return None
    run_id = ""
    if len(lines) >= 3:
        run_id = lines[2]
    elif len(lines) >= 2 and not lines[1].isdigit():
        run_id = lines[1]
    return pid, run_id


def lock_holder_pid(project_root: Path, run_id: str) -> int | None:
    lines = _read_lock_lines(run_lock_path(project_root, run_id))
    return _parse_pid(lines[0]) if lines else None


def lock_holder_pgid(project_root: Path, run_id: str) -> int | None:
    lines = _read_lock_lines(run_lock_path(project_root, run_id))
    if len(lines) >= 2:
        return _parse_pid(lines[1])
    return lock_holder_pid(project_root, run_id)


def _try_probe_alive(path: Path) -> bool:
    """True if another process holds an exclusive flock on ``path``."""
    if not path.is_file():
        return False
    try:
        fh = open(path, "a+", encoding="utf-8")
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return False
    finally:
        fh.close()


def is_run_alive(project_root: Path, run_id: str) -> bool:
    return _try_probe_alive(run_lock_path(project_root, run_id))


def is_project_locked(project_root: Path) -> bool:
    return _try_probe_alive(factory_lock_path(project_root))


def ensure_process_group() -> int:
    """Become process-group leader when safe; return current pgid."""
    try:
        if os.getpgrp() != os.getpid():
            os.setpgrp()
    except OSError as err:
        log.warning("setpgrp failed: %s", err)
    return os.getpgrp()


def _pids_in_group(pgid: int, *, exclude: int | None = None) -> list[int]:
    members: list[int] = []
    proc = Path("/proc")
    if not proc.is_dir():
        return members
    for child in proc.iterdir():
        if not child.name.isdigit():
            continue
        pid = int(child.name)
        if exclude is not None and pid == exclude:
            continue
        try:
            if os.getpgid(pid) == pgid:
                members.append(pid)
        except (ProcessLookupError, PermissionError, OSError):
            continue
    return members


def terminate_other_group_members(pgid: int, *, term_timeout_s: float = 5.0) -> str:
    """SIGTERM/SIGKILL other members of ``pgid``, sparing the calling process."""
    if pgid <= 0:
        return "invalid-pgid"
    me = os.getpid()
    members = _pids_in_group(pgid, exclude=me)
    if not members:
        return "no-children"
    for pid in members:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + max(0.0, term_timeout_s)
    while time.monotonic() < deadline:
        alive = []
        for pid in members:
            try:
                os.kill(pid, 0)
                alive.append(pid)
            except ProcessLookupError:
                pass
        if not alive:
            return "terminated"
        time.sleep(0.1)
        members = alive
    for pid in members:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return "killed"


def kill_process_group(pgid: int, *, term_timeout_s: float = 10.0) -> str:
    """SIGTERM the group, wait, then SIGKILL stragglers. Returns a short status.

    When called from inside the target group, only other members are signalled
    (so the caller can finish pause/lock cleanup before exiting).
    """
    if pgid <= 0:
        return "invalid-pgid"
    if os.getpgrp() == pgid:
        return terminate_other_group_members(pgid, term_timeout_s=term_timeout_s)
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return "already-dead"
    except PermissionError:
        try:
            os.kill(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return "already-dead"
        time.sleep(min(term_timeout_s, 1.0))
        try:
            os.kill(pgid, 0)
            os.kill(pgid, signal.SIGKILL)
            return "killed"
        except ProcessLookupError:
            return "terminated"

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return "already-dead"

    deadline = time.monotonic() + max(0.0, term_timeout_s)
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return "terminated"
        time.sleep(0.2)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return "terminated"
    return "killed"


def stop_run_process(
    project_root: Path, run_id: str, *, term_timeout_s: float = 10.0
) -> str:
    """Terminate the process group owning ``run.lock``. No-op if already dead."""
    if not is_run_alive(project_root, run_id):
        return "already-dead"
    pgid = lock_holder_pgid(project_root, run_id)
    pid = lock_holder_pid(project_root, run_id)
    target = pgid or pid
    if target is None:
        return "no-pid"
    # Prefer killpg when lock recorded a pgid; otherwise kill the pid.
    if pgid is not None and pgid == pid:
        return kill_process_group(pgid, term_timeout_s=term_timeout_s)
    if pgid is not None:
        result = kill_process_group(pgid, term_timeout_s=term_timeout_s)
        if result != "already-dead":
            return result
    if pid is None:
        return "no-pid"
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return "already-dead"
    deadline = time.monotonic() + max(0.0, term_timeout_s)
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "terminated"
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return "terminated"
    return "killed"


class ProjectLock:
    """Exclusive project-wide mutex: ``.bmad-factory/factory.lock``."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.path = factory_lock_path(project_root)
        self._fh: TextIO | None = None
        self._run_id: str | None = None

    def acquire(self, *, run_id: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = project_holder(self.project_root)
            fh.close()
            if holder:
                h_pid, h_run = holder
                detail = (
                    f"factory locked by pid={h_pid} run_id={h_run or '(unknown)'}; "
                    f"use --stop {h_run or '<run_id>'} or wait for it to finish"
                )
            else:
                detail = (
                    "factory.lock is held by another process; "
                    "use --status / --stop or wait for it to finish"
                )
            raise FactoryHalt(SHUTDOWN_ERROR, detail) from None
        pid = os.getpid()
        pgid = os.getpgrp()
        fh.seek(0)
        fh.truncate()
        fh.write(f"{pid}\n{pgid}\n{run_id}\n")
        fh.flush()
        self._fh = fh
        self._run_id = run_id
        log.info("project lock acquired pid=%s pgid=%s run_id=%s", pid, pgid, run_id)

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        self._fh = None
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            fh.close()
        except OSError:
            pass
        # Leave the file in place with stale metadata; reclaim on next acquire.
        log.info("project lock released run_id=%s", self._run_id)


class RunLock:
    """Per-run liveness lock: ``runs/<id>/run.lock``."""

    def __init__(self, project_root: Path, run_id: str) -> None:
        self.project_root = project_root
        self.run_id = run_id
        self.path = run_lock_path(project_root, run_id)
        self._fh: TextIO | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pid = lock_holder_pid(self.project_root, self.run_id)
            fh.close()
            detail = (
                f"run {self.run_id} still live (pid={pid or '?'}); use --stop first"
            )
            raise FactoryHalt(SHUTDOWN_ERROR, detail) from None
        pid = os.getpid()
        pgid = os.getpgrp()
        fh.seek(0)
        fh.truncate()
        fh.write(f"{pid}\n{pgid}\n")
        fh.flush()
        self._fh = fh
        log.info("run lock acquired run_id=%s pid=%s pgid=%s", self.run_id, pid, pgid)

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        self._fh = None
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            fh.close()
        except OSError:
            pass
        log.info("run lock released run_id=%s", self.run_id)
