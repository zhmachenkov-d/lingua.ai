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
SHUTDOWN_UNREFINED_BUGS = "unrefined_bugs"
SHUTDOWN_PAUSED = "paused"
SHUTDOWN_PLATEAU = "plateau_deferred"

POLICY_DIRNAME = ".bmad-orchestrate"
POLICY_FILENAME = "policy.toml"
RUNS_DIRNAME = "runs"

DEFAULT_MODEL_ID = "auto"
AGENT_START_MAX_ATTEMPTS = 3
# Per-call agent limits (0 disables). Kept in sync with LimitsPolicy defaults.
DEFAULT_AGENT_TIMEOUT_S = 600
DEFAULT_AGENT_MAX_TOKENS = 2_000_000

log = logging.getLogger("bmad_orchestrate")


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-5s %(message)s", "%Y-%m-%d %H:%M:%S"
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


class OrchestratorHalt(Exception):
    """Stop the loop with a shutdown reason (non-zero unless completed)."""

    def __init__(self, shutdown: str, detail: str | None = None):
        self.shutdown = shutdown
        self.detail = detail
        super().__init__(detail or shutdown)
