"""Load and validate ``.bmad-factory/policy.toml``."""

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
    SHUTDOWN_ERROR,
    FactoryHalt,
)


@dataclass
class GatesPolicy:
    plan_checkpoint: bool = True
    done_checkpoint: bool = True


@dataclass
class VerifyPolicy:
    commands: list[str] = field(default_factory=list)
    require_diff: bool = True


@dataclass
class ScmPolicy:
    isolation: str = "inplace"
    merge_strategy: str = "squash"
    remote: str = "pr-merge"  # none | pr-merge
    target_branch: str | None = None


@dataclass
class LimitsPolicy:
    agent_timeout_s: int = DEFAULT_AGENT_TIMEOUT_S
    agent_max_tokens: int = DEFAULT_AGENT_MAX_TOKENS


@dataclass
class SweepPolicy:
    ledger_name: str = "deferred-work.md"
    attended_prompt: bool = True


@dataclass
class TicketsPolicy:
    script: str = "_bmad/method/scripts/tickets.py"
    mark_done: str = "auto"  # auto | never
    thorough_review: str = "high-risk"  # never | high-risk | always


@dataclass
class Policy:
    gates: GatesPolicy = field(default_factory=GatesPolicy)
    verify: VerifyPolicy = field(default_factory=VerifyPolicy)
    scm: ScmPolicy = field(default_factory=ScmPolicy)
    limits: LimitsPolicy = field(default_factory=LimitsPolicy)
    sweep: SweepPolicy = field(default_factory=SweepPolicy)
    tickets: TicketsPolicy = field(default_factory=TicketsPolicy)


DEFAULT_POLICY_TOML = """\
# BMAD factory policy (lean Cursor SDK ticket loop).
# Copy to .bmad-factory/policy.toml and adjust.

[gates]
plan_checkpoint = true
done_checkpoint = true

[verify]
commands = []
require_diff = true

[scm]
isolation = "inplace"
merge_strategy = "squash"
# none | pr-merge
remote = "pr-merge"

[limits]
# 0 disables either limit
agent_timeout_s = 600
agent_max_tokens = 2000000

[sweep]
ledger_name = "deferred-work.md"
attended_prompt = true

[tickets]
script = "_bmad/method/scripts/tickets.py"
# auto | never
mark_done = "auto"
# never | high-risk | always — auto-escalate thorough review
thorough_review = "high-risk"
"""


def policy_dir(project_root: Path) -> Path:
    return project_root / POLICY_DIRNAME


def policy_path(project_root: Path) -> Path:
    return policy_dir(project_root) / POLICY_FILENAME


def ensure_policy_template(project_root: Path) -> Path:
    path = policy_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(DEFAULT_POLICY_TOML, encoding="utf-8")
    return path


def _require_choice(section: str, key: str, value: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            f"policy [{section}].{key}={value!r} invalid; expected one of {sorted(allowed)}",
        )
    return value


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    raw = data.get(name) or {}
    if not isinstance(raw, dict):
        raise FactoryHalt(SHUTDOWN_ERROR, f"policy [{name}] must be a table")
    return raw


def _bool(section: dict[str, Any], key: str, default: bool) -> bool:
    if key not in section:
        return default
    val = section[key]
    if not isinstance(val, bool):
        raise FactoryHalt(SHUTDOWN_ERROR, f"policy key {key!r} must be bool")
    return val


def _int(section: dict[str, Any], key: str, default: int, *, min_value: int = 0) -> int:
    if key not in section:
        return default
    val = section[key]
    if not isinstance(val, int) or isinstance(val, bool):
        raise FactoryHalt(SHUTDOWN_ERROR, f"policy key {key!r} must be int")
    if val < min_value:
        raise FactoryHalt(
            SHUTDOWN_ERROR, f"policy key {key!r} must be >= {min_value}"
        )
    return val


def _str_list(section: dict[str, Any], key: str) -> list[str]:
    if key not in section:
        return []
    val = section[key]
    if not isinstance(val, list) or any(not isinstance(x, str) for x in val):
        raise FactoryHalt(
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
        raise FactoryHalt(SHUTDOWN_ERROR, f"invalid policy.toml: {err}") from err
    if not isinstance(data, dict):
        raise FactoryHalt(SHUTDOWN_ERROR, "policy.toml root must be a table")

    gates_raw = _section(data, "gates")
    verify_raw = _section(data, "verify")
    scm_raw = _section(data, "scm")
    limits_raw = _section(data, "limits")
    sweep_raw = _section(data, "sweep")
    tickets_raw = _section(data, "tickets")

    isolation = str(scm_raw.get("isolation", "inplace"))
    _require_choice("scm", "isolation", isolation, {"inplace"})
    merge_strategy = str(scm_raw.get("merge_strategy", "squash"))
    _require_choice("scm", "merge_strategy", merge_strategy, {"squash"})
    remote = str(scm_raw.get("remote", "pr-merge"))
    # Accept legacy "pr" as alias for pr-merge.
    if remote == "pr":
        remote = "pr-merge"
    _require_choice("scm", "remote", remote, {"none", "pr-merge"})
    target_branch = scm_raw.get("target_branch")
    if target_branch is not None and not isinstance(target_branch, str):
        raise FactoryHalt(
            SHUTDOWN_ERROR, "policy [scm].target_branch must be a string"
        )

    script = str(tickets_raw.get("script", "_bmad/method/scripts/tickets.py"))
    mark_done = str(tickets_raw.get("mark_done", "auto"))
    _require_choice("tickets", "mark_done", mark_done, {"auto", "never"})
    thorough_review = str(tickets_raw.get("thorough_review", "high-risk"))
    _require_choice(
        "tickets",
        "thorough_review",
        thorough_review,
        {"never", "high-risk", "always"},
    )
    ledger_name = str(sweep_raw.get("ledger_name", "deferred-work.md"))

    return Policy(
        gates=GatesPolicy(
            plan_checkpoint=_bool(gates_raw, "plan_checkpoint", True),
            done_checkpoint=_bool(gates_raw, "done_checkpoint", True),
        ),
        verify=VerifyPolicy(
            commands=_str_list(verify_raw, "commands"),
            require_diff=_bool(verify_raw, "require_diff", True),
        ),
        scm=ScmPolicy(
            isolation=isolation,
            merge_strategy=merge_strategy,
            remote=remote,
            target_branch=target_branch,
        ),
        limits=LimitsPolicy(
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
        tickets=TicketsPolicy(
            script=script,
            mark_done=mark_done,
            thorough_review=thorough_review,
        ),
    )
