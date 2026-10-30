from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

TICKETS_SCRIPT = Path("_bmad/method/scripts/tickets.py")
STORE_PROJECT_FILE = Path("_bmad/custom/ticketing-store-config.toml")
STORE_STARTERS = Path(".agents/skills/bmad-agent-po/config")
STORE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PROTECTED_BRANCHES = frozenset({"main", "master"})
BRANCH_SLUG_RE = re.compile(r"[^a-z0-9._-]+")
MERGE_POLL_INTERVAL_S = 30
MERGE_TIMEOUT_S = 30 * 60

SHUTDOWN_COMPLETED = "completed"
SHUTDOWN_BLOCKED = "blocked"
SHUTDOWN_PLAN_CHECKPOINT = "plan_checkpoint"
SHUTDOWN_DONE_CHECKPOINT = "done_checkpoint"
SHUTDOWN_DIRTY_TREE = "dirty_tree"
SHUTDOWN_ERROR = "error"
SHUTDOWN_TICKET_NOT_RESOLVED = "ticket_not_resolved"
SHUTDOWN_PAUSED = "paused"

POLICY_DIRNAME = ".bmad-factory"
POLICY_FILENAME = "policy.toml"
RUNS_DIRNAME = "runs"

DEFAULT_MODEL_ID = "auto"
AGENT_START_MAX_ATTEMPTS = 3
DEFAULT_AGENT_TIMEOUT_S = 600
DEFAULT_AGENT_MAX_TOKENS = 2_000_000

BRANCH_PREFIX = "factory"

log = logging.getLogger("bmad_factory")

_LOG_FORMAT = "%(asctime)s %(levelname)-5s %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
_RUN_LOG_HANDLER_NAME = "bmad_factory_run_log"
_run_log_handler: logging.FileHandler | None = None


def _log_formatter() -> logging.Formatter:
    return logging.Formatter(_LOG_FORMAT, _LOG_DATEFMT)


def configure_logging(level: str) -> None:
    detach_run_log()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_log_formatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def attach_run_log(path: Path) -> None:
    """Append factory ``logging`` output to ``path`` (idempotent)."""
    global _run_log_handler
    root = logging.getLogger()
    if _run_log_handler is not None:
        if Path(getattr(_run_log_handler, "baseFilename", "")) == path.resolve():
            return
        detach_run_log()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, mode="a", encoding="utf-8")
    handler.set_name(_RUN_LOG_HANDLER_NAME)
    handler.setFormatter(_log_formatter())
    root.addHandler(handler)
    _run_log_handler = handler


def detach_run_log() -> None:
    """Remove the run FileHandler if attached."""
    global _run_log_handler
    root = logging.getLogger()
    if _run_log_handler is not None:
        root.removeHandler(_run_log_handler)
        _run_log_handler.close()
        _run_log_handler = None
        return
    for handler in list(root.handlers):
        if getattr(handler, "name", None) == _RUN_LOG_HANDLER_NAME:
            root.removeHandler(handler)
            handler.close()


class FactoryHalt(Exception):
    """Stop the loop with a shutdown reason (non-zero unless completed)."""

    def __init__(self, shutdown: str, detail: str | None = None):
        self.shutdown = shutdown
        self.detail = detail
        super().__init__(detail or shutdown)
