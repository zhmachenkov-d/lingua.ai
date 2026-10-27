"""Load and validate ``.bmad-orchestrate/policy.toml``."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_AGENT_MAX_TOKENS,
    DEFAULT_AGENT_TIMEOUT_S,
    POLICY_DIRNAME,
    POLICY_FILENAME,
    OrchestratorHalt,
    SHUTDOWN_ERROR,
)


@dataclass
class GatesPolicy:
    plan_checkpoint: bool = True
    done_checkpoint: bool = True
    unrefined_bugs: bool = True
    epic_boundary_pause: bool = True


@dataclass
class ReviewPolicy:
    trigger: str = "recommended"  # recommended | always | never
    max_followup_reviews: int = 1


@dataclass
class VerifyPolicy:
    commands: list[str] = field(default_factory=list)
    require_diff: bool = True


@dataclass
class ScmPolicy:
    isolation: str = "worktree"  # worktree | inplace
    merge_strategy: str = "squash"
    branch_per: str = "story"
    remote: str = "none"  # none | pr
    target_branch: str | None = None


@dataclass
class LimitsPolicy:
    max_dev_attempts: int = 2
    max_review_cycles: int = 3
    max_followup_reviews: int = 1
    # 0 disables the limit.
    agent_timeout_s: int = DEFAULT_AGENT_TIMEOUT_S
    agent_max_tokens: int = DEFAULT_AGENT_MAX_TOKENS


@dataclass
class SweepPolicy:
    ledger_name: str = "deferred-work.md"
    attended_prompt: bool = True


@dataclass
class TicketsPolicy:
    script: str = "_bmad/method/scripts/tickets.py"


@dataclass
class Policy:
    gates: GatesPolicy = field(default_factory=GatesPolicy)
    review: ReviewPolicy = field(default_factory=ReviewPolicy)
    verify: VerifyPolicy = field(default_factory=VerifyPolicy)
    scm: ScmPolicy = field(default_factory=ScmPolicy)
    limits: LimitsPolicy = field(default_factory=LimitsPolicy)
    sweep: SweepPolicy = field(default_factory=SweepPolicy)
    tickets: TicketsPolicy = field(default_factory=TicketsPolicy)

    @property
    def effective_max_followup_reviews(self) -> int:
        return min(self.review.max_followup_reviews, self.limits.max_followup_reviews)


DEFAULT_POLICY_TOML = """\
# BMAD orchestrate policy (Cursor SDK ticket-tree loop).
# Copy to .bmad-orchestrate/policy.toml and adjust.

[gates]
plan_checkpoint = true
done_checkpoint = true
unrefined_bugs = true
epic_boundary_pause = true

[review]
# recommended | always | never
trigger = "recommended"
max_followup_reviews = 1

[verify]
commands = []
require_diff = true

[scm]
# worktree | inplace
isolation = "worktree"
merge_strategy = "squash"
branch_per = "story"
# none | pr  (pr enables push/PR/merge landing)
remote = "none"

[limits]
max_dev_attempts = 2
max_review_cycles = 3
max_followup_reviews = 1
# 0 disables either limit
agent_timeout_s = 600
agent_max_tokens = 2000000

[sweep]
ledger_name = "deferred-work.md"
attended_prompt = true

[tickets]
script = "_bmad/method/scripts/tickets.py"
"""


def policy_dir(project_root: Path) -> Path:
    return project_root / POLICY_DIRNAME


def policy_path(project_root: Path) -> Path:
    return policy_dir(project_root) / POLICY_FILENAME


def ensure_policy_template(project_root: Path) -> Path:
    """Create policy dir + default policy.toml when missing. Returns path."""
    path = policy_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(DEFAULT_POLICY_TOML, encoding="utf-8")
    return path


def _require_choice(section: str, key: str, value: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            f"policy [{section}].{key}={value!r} invalid; expected one of {sorted(allowed)}",
        )
    return value


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    raw = data.get(name) or {}
    if not isinstance(raw, dict):
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"policy [{name}] must be a table"
        )
    return raw


def _bool(section: dict[str, Any], key: str, default: bool) -> bool:
    if key not in section:
        return default
    val = section[key]
    if not isinstance(val, bool):
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"policy key {key!r} must be bool"
        )
    return val


def _int(section: dict[str, Any], key: str, default: int, *, min_value: int = 0) -> int:
    if key not in section:
        return default
    val = section[key]
    if not isinstance(val, int) or isinstance(val, bool):
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"policy key {key!r} must be int"
        )
    if val < min_value:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"policy key {key!r} must be >= {min_value}"
        )
    return val


def _str_list(section: dict[str, Any], key: str) -> list[str]:
    if key not in section:
        return []
    val = section[key]
    if not isinstance(val, list) or any(not isinstance(x, str) for x in val):
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"policy key {key!r} must be a list of strings"
        )
    return list(val)


def load_policy(project_root: Path, *, create_if_missing: bool = True) -> Policy:
    path = (
        ensure_policy_template(project_root)
        if create_if_missing
        else policy_path(project_root)
    )
    if not path.is_file():
        return Policy()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as err:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"invalid policy.toml: {err}"
        ) from err
    if not isinstance(data, dict):
        raise OrchestratorHalt(SHUTDOWN_ERROR, "policy.toml root must be a table")

    gates_raw = _section(data, "gates")
    review_raw = _section(data, "review")
    verify_raw = _section(data, "verify")
    scm_raw = _section(data, "scm")
    limits_raw = _section(data, "limits")
    sweep_raw = _section(data, "sweep")
    tickets_raw = _section(data, "tickets")

    trigger = str(review_raw.get("trigger", "recommended"))
    _require_choice("review", "trigger", trigger, {"recommended", "always", "never"})

    isolation = str(scm_raw.get("isolation", "worktree"))
    _require_choice("scm", "isolation", isolation, {"worktree", "inplace"})
    merge_strategy = str(scm_raw.get("merge_strategy", "squash"))
    _require_choice("scm", "merge_strategy", merge_strategy, {"squash"})
    branch_per = str(scm_raw.get("branch_per", "story"))
    _require_choice("scm", "branch_per", branch_per, {"story", "epic", "run"})
    remote = str(scm_raw.get("remote", "none"))
    _require_choice("scm", "remote", remote, {"none", "pr"})
    target_branch = scm_raw.get("target_branch")
    if target_branch is not None and not isinstance(target_branch, str):
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, "policy [scm].target_branch must be a string"
        )

    script = str(tickets_raw.get("script", "_bmad/method/scripts/tickets.py"))
    ledger_name = str(sweep_raw.get("ledger_name", "deferred-work.md"))

    return Policy(
        gates=GatesPolicy(
            plan_checkpoint=_bool(gates_raw, "plan_checkpoint", True),
            done_checkpoint=_bool(gates_raw, "done_checkpoint", True),
            unrefined_bugs=_bool(gates_raw, "unrefined_bugs", True),
            epic_boundary_pause=_bool(gates_raw, "epic_boundary_pause", True),
        ),
        review=ReviewPolicy(
            trigger=trigger,
            max_followup_reviews=_int(
                review_raw, "max_followup_reviews", 1, min_value=0
            ),
        ),
        verify=VerifyPolicy(
            commands=_str_list(verify_raw, "commands"),
            require_diff=_bool(verify_raw, "require_diff", True),
        ),
        scm=ScmPolicy(
            isolation=isolation,
            merge_strategy=merge_strategy,
            branch_per=branch_per,
            remote=remote,
            target_branch=target_branch,
        ),
        limits=LimitsPolicy(
            max_dev_attempts=_int(limits_raw, "max_dev_attempts", 2, min_value=1),
            max_review_cycles=_int(limits_raw, "max_review_cycles", 3, min_value=0),
            max_followup_reviews=_int(
                limits_raw, "max_followup_reviews", 1, min_value=0
            ),
            agent_timeout_s=_int(
                limits_raw, "agent_timeout_s", DEFAULT_AGENT_TIMEOUT_S, min_value=0
            ),
            agent_max_tokens=_int(
                limits_raw, "agent_max_tokens", DEFAULT_AGENT_MAX_TOKENS, min_value=0
            ),
        ),
        sweep=SweepPolicy(
            ledger_name=ledger_name,
            attended_prompt=_bool(sweep_raw, "attended_prompt", True),
        ),
        tickets=TicketsPolicy(script=script),
    )
