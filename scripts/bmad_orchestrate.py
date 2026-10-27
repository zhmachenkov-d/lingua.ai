#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "cursor-sdk",
#   "pyyaml",
# ]
# ///
"""BMAD Cursor build orchestrator.

Python owns queueing, checkpoints, deferred append, mark-done, git push/PR, and
reporting. Cursor agents run only for ``bmad-build-auto`` and ``bmad-retrospective``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

TICKETS_SCRIPT = Path("_bmad/method/scripts/tickets.py")
STORE_PROJECT_FILE = Path("_bmad/custom/ticketing-store-config.toml")
STORE_STARTERS = Path(".agents/skills/bmad-agent-po/config")
STORE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PROTECTED_BRANCHES = frozenset({"main", "master"})
SHUTDOWN_COMPLETED = "completed"
SHUTDOWN_BLOCKED = "blocked"
SHUTDOWN_PLAN_CHECKPOINT = "plan_checkpoint"
SHUTDOWN_DONE_CHECKPOINT = "done_checkpoint"
SHUTDOWN_DIRTY_TREE = "dirty_tree"
SHUTDOWN_ERROR = "error"
SHUTDOWN_TICKET_NOT_RESOLVED = "ticket_not_resolved"
SHUTDOWN_UNREFINED_BUGS = "unrefined_bugs"

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


# --------------------------------------------------------------------------- report


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: TokenUsage | None) -> None:
        if other is None:
            return
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens


@dataclass
class UnitReport:
    ref: str
    kind: str  # ticket | retrospective
    plan_status: str | None = None
    outcome: str = "error"
    deferred_count: int = 0
    tokens: dict[str, int] | None = None
    agent_id: str | None = None
    run_id: str | None = None
    pr_url: str | None = None
    reason: str | None = None
    epic: str | None = None


@dataclass
class RunReport:
    units: list[UnitReport] = field(default_factory=list)
    shutdown: str = SHUTDOWN_COMPLETED
    shutdown_detail: str | None = None
    totals: dict[str, Any] = field(default_factory=dict)
    unrefined_bugs: list[dict[str, str]] = field(default_factory=list)

    def add(self, unit: UnitReport) -> None:
        self.units.append(unit)

    def finalize_totals(self) -> None:
        usage = TokenUsage()
        marked_done = 0
        deferred = 0
        retros = 0
        prs: set[str] = set()
        tickets = 0
        for u in self.units:
            if u.kind == "ticket":
                tickets += 1
                if u.outcome == "done":
                    marked_done += 1
            elif u.kind == "retrospective":
                retros += 1
            deferred += u.deferred_count
            if u.tokens:
                usage.add(
                    TokenUsage(
                        input_tokens=u.tokens.get("input_tokens", 0),
                        output_tokens=u.tokens.get("output_tokens", 0),
                        total_tokens=u.tokens.get("total_tokens", 0),
                    )
                )
            if u.pr_url:
                prs.add(u.pr_url)
        self.totals = {
            "tickets": tickets,
            "marked_done": marked_done,
            "deferred_items": deferred,
            "retrospectives": retros,
            "prs": len(prs),
            "tokens": {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        self.finalize_totals()
        return {
            "shutdown": self.shutdown,
            "shutdown_detail": self.shutdown_detail,
            "units": [asdict(u) for u in self.units],
            "unrefined_bugs": list(self.unrefined_bugs),
            "totals": self.totals,
        }

    def print_human(self, stream=sys.stderr) -> None:
        self.finalize_totals()
        detail = f" — {self.shutdown_detail}" if self.shutdown_detail else ""
        print("=== BMAD orchestrate report ===", file=stream)
        print(f"Shutdown: {self.shutdown}{detail}", file=stream)
        tickets = [u for u in self.units if u.kind == "ticket"]
        retros = [u for u in self.units if u.kind == "retrospective"]
        print("Tickets:", file=stream)
        if not tickets:
            print("  (none)", file=stream)
        for u in tickets:
            tok = u.tokens["total_tokens"] if u.tokens else "null"
            extra = ""
            if u.outcome == "blocked" and u.reason:
                extra = f"  reason={u.reason}"
            elif u.pr_url:
                extra = f"  pr={u.pr_url}"
            elif u.reason:
                extra = f"  reason={u.reason}"
            print(
                f"  {u.ref:<40} {u.outcome:<12} tokens={tok}  deferred={u.deferred_count}{extra}",
                file=stream,
            )
        print("Unrefined bugs:", file=stream)
        if not self.unrefined_bugs:
            print("  none", file=stream)
        else:
            for bug in self.unrefined_bugs:
                title = bug.get("title") or ""
                suffix = f"  {title}" if title else ""
                print(f"  {bug.get('ref', '?')}{suffix}", file=stream)
        print("Retrospectives:", file=stream)
        if not retros:
            print("  none", file=stream)
        else:
            for u in retros:
                tok = u.tokens["total_tokens"] if u.tokens else "null"
                extra = f"  pr={u.pr_url}" if u.pr_url else ""
                print(f"  {u.ref:<40} {u.outcome:<12} tokens={tok}{extra}", file=stream)
        t = self.totals
        tok = t["tokens"]
        print(
            f"Totals: tickets={t['tickets']}  done={t['marked_done']}  "
            f"tokens={tok['total_tokens']}  (in={tok['input_tokens']} out={tok['output_tokens']})  "
            f"deferred={t['deferred_items']}  retros={t['retrospectives']}  prs={t['prs']}  "
            f"unrefined_bugs={len(self.unrefined_bugs)}",
            file=stream,
        )


def format_token_cost(usage: TokenUsage | None) -> str:
    if usage is None:
        return "tokens=null"
    return (
        f"tokens in={usage.input_tokens} out={usage.output_tokens} "
        f"total={usage.total_tokens}"
    )


def format_token_cost_from_report(report: RunReport) -> str:
    report.finalize_totals()
    tok = report.totals.get("tokens") or {}
    return (
        f"tokens in={tok.get('input_tokens', 0)} out={tok.get('output_tokens', 0)} "
        f"total={tok.get('total_tokens', 0)}"
    )


def log_cumulative_tokens(report: RunReport) -> None:
    log.info("token cost cumulative %s", format_token_cost_from_report(report))


class OrchestratorHalt(Exception):
    """Stop the loop with a shutdown reason (non-zero unless completed)."""

    def __init__(self, shutdown: str, detail: str | None = None):
        self.shutdown = shutdown
        self.detail = detail
        super().__init__(detail or shutdown)


# --------------------------------------------------------------------------- tickets.py


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


# --------------------------------------------------------------------------- store config / tracker mark-done


def _merge_toml(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_toml(out[key], value)
        else:
            out[key] = value
    return out


def load_store_config(project_root: Path) -> dict[str, Any]:
    path = project_root / STORE_PROJECT_FILE
    project = (
        tomllib.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    )
    tickets = project.get("tickets")
    store = tickets.get("store") if isinstance(tickets, dict) else None
    if not isinstance(store, str) or not store:
        store = "repo"
    starter = project_root / STORE_STARTERS / f"{store}-ticketing.toml"
    if STORE_NAME_RE.match(store) and starter.is_file():
        config = _merge_toml(
            tomllib.loads(starter.read_text(encoding="utf-8-sig")), project
        )
    else:
        config = project
    if isinstance(config.get("tickets"), dict):
        config["tickets"]["store"] = store
    return config


def _tickets_table(cfg: dict[str, Any]) -> dict[str, Any]:
    tickets = cfg.get("tickets")
    return tickets if isinstance(tickets, dict) else {}


def _status_map(cfg: dict[str, Any]) -> dict[str, str]:
    status = _tickets_table(cfg).get("status")
    if not isinstance(status, dict):
        return {}
    return {str(k): str(v) for k, v in status.items() if v is not None}


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"{name} is not set")
    return value


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"HTTP {err.code} {method} {url}: {detail[:500]}"
        ) from err
    except urllib.error.URLError as err:
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"HTTP {method} {url}: {err}") from err
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"non-JSON response from {url}: {raw[:200]}"
        ) from err


def _run_checked(
    cmd: list[str], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    log.debug("run: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            proc.stderr.strip() or proc.stdout.strip() or f"{' '.join(cmd)} failed",
        )
    return proc


def tracker_done_github(
    project_root: Path, *, tracker_id: str, cfg: dict[str, Any]
) -> None:
    tickets = _tickets_table(cfg)
    repo = str(tickets.get("repo") or "").strip()
    status_labels = {
        v
        for k, v in _status_map(cfg).items()
        if k in ("backlog", "in-progress", "review") and v
    }
    base = ["gh", "issue"]
    r_args = ["-R", repo] if repo else []
    view = _run_checked(
        [*base, "view", tracker_id, *r_args, "--json", "labels"], cwd=project_root
    )
    try:
        labels = {
            str(item.get("name") or "")
            for item in (json.loads(view.stdout).get("labels") or [])
        }
    except json.JSONDecodeError as err:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"gh issue view non-JSON: {view.stdout[:200]}"
        ) from err
    for label in sorted(labels & status_labels):
        log.info("github remove status label=%s issue=%s", label, tracker_id)
        edit = subprocess.run(
            [*base, "edit", tracker_id, *r_args, "--remove-label", label],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        if edit.returncode != 0:
            log.warning(
                "github remove-label %s failed (ignored): %s",
                label,
                (edit.stderr or edit.stdout or "").strip(),
            )
    log.info("github close issue=%s repo=%s", tracker_id, repo or "(default)")
    _run_checked([*base, "close", tracker_id, *r_args], cwd=project_root)


def tracker_done_jira(
    project_root: Path, *, tracker_id: str, cfg: dict[str, Any]
) -> None:
    done_status = _status_map(cfg).get("done") or "Done"
    log.info("jira transition key=%s status=%s", tracker_id, done_status)
    _run_checked(
        [
            "acli",
            "jira",
            "workitem",
            "transition",
            tracker_id,
            "--status",
            done_status,
        ],
        cwd=project_root,
    )


def tracker_done_linear(
    project_root: Path, *, tracker_id: str, cfg: dict[str, Any]
) -> None:
    del project_root  # HTTP API; cwd unused
    api_key = _require_env("LINEAR_API_KEY")
    done_name = _status_map(cfg).get("done") or "Done"
    headers = {"Authorization": api_key}

    issue_payload = _http_json(
        "POST",
        "https://api.linear.app/graphql",
        headers=headers,
        body={
            "query": ("query($id: String!) { issue(id: $id) { id team { id } } }"),
            "variables": {"id": tracker_id},
        },
    )
    issue = ((issue_payload or {}).get("data") or {}).get("issue")
    if not issue:
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"linear issue not found: {tracker_id}")
    team_id = (issue.get("team") or {}).get("id")
    if not team_id:
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"linear issue {tracker_id} has no team")

    states_payload = _http_json(
        "POST",
        "https://api.linear.app/graphql",
        headers=headers,
        body={
            "query": (
                "query($teamId: String!) {"
                "  team(id: $teamId) { states { nodes { id name } } }"
                "}"
            ),
            "variables": {"teamId": team_id},
        },
    )
    nodes = (
        (((states_payload or {}).get("data") or {}).get("team") or {}).get("states")
        or {}
    ).get("nodes") or []
    state_id = next(
        (
            str(n["id"])
            for n in nodes
            if str(n.get("name") or "").lower() == done_name.lower()
        ),
        None,
    )
    if not state_id:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            f"linear status {done_name!r} not found for team of {tracker_id}",
        )

    log.info("linear issueUpdate id=%s state=%s", tracker_id, done_name)
    update = _http_json(
        "POST",
        "https://api.linear.app/graphql",
        headers=headers,
        body={
            "query": (
                "mutation($id: String!, $stateId: String!) {"
                "  issueUpdate(id: $id, input: { stateId: $stateId }) {"
                "    success"
                "  }"
                "}"
            ),
            "variables": {"id": issue["id"], "stateId": state_id},
        },
    )
    success = (((update or {}).get("data") or {}).get("issueUpdate") or {}).get(
        "success"
    )
    if not success:
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"linear issueUpdate failed: {update}")


def _notion_page_id(tracker_id: str) -> str:
    """Notion page ids may be dashed or undashed UUIDs, or already a URL fragment."""
    tid = tracker_id.strip()
    if "notion.so" in tid or "www.notion.so" in tid:
        fragment = tid.rstrip("/").split("/")[-1].split("?")[0]
        tid = fragment.split("-")[-1] if "-" in fragment else fragment
    hex_only = re.sub(r"[^0-9a-fA-F]", "", tid)
    if len(hex_only) == 32:
        return (
            f"{hex_only[0:8]}-{hex_only[8:12]}-{hex_only[12:16]}-"
            f"{hex_only[16:20]}-{hex_only[20:32]}"
        )
    return tid


def tracker_done_notion(
    project_root: Path, *, tracker_id: str, cfg: dict[str, Any]
) -> None:
    del project_root
    token = _require_env("NOTION_TOKEN")
    done_name = _status_map(cfg).get("done") or "Done"
    page_id = _notion_page_id(tracker_id)
    log.info("notion update page=%s status=%s", page_id, done_name)
    _http_json(
        "PATCH",
        f"https://api.notion.com/v1/pages/{page_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
        },
        body={"properties": {"Status": {"status": {"name": done_name}}}},
    )


def _trello_board_id(board: str) -> str:
    board = board.strip()
    if not board:
        raise OrchestratorHalt(SHUTDOWN_ERROR, "trello board is not configured")
    if re.fullmatch(r"[a-f0-9]{24}", board):
        return board
    # URL like https://trello.com/b/<short>/<name>
    parts = board.rstrip("/").split("/")
    if "b" in parts:
        idx = parts.index("b")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return board


def tracker_done_trello(
    project_root: Path, *, tracker_id: str, cfg: dict[str, Any]
) -> None:
    del project_root
    key = _require_env("TRELLO_API_KEY")
    token = _require_env("TRELLO_TOKEN")
    done_name = _status_map(cfg).get("done") or "Done"
    board = str(_tickets_table(cfg).get("board") or "").strip()
    board_id = _trello_board_id(board)
    auth = {"key": key, "token": token}

    lists_url = (
        f"https://api.trello.com/1/boards/{urllib.parse.quote(board_id)}/lists?"
        + urllib.parse.urlencode(auth)
    )
    lists = _http_json("GET", lists_url)
    if not isinstance(lists, list):
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"trello lists failed: {lists}")
    list_id = next(
        (
            str(item["id"])
            for item in lists
            if str(item.get("name") or "").lower() == done_name.lower()
        ),
        None,
    )
    if not list_id:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"trello list {done_name!r} not found on board {board_id}"
        )

    card_url = (
        f"https://api.trello.com/1/cards/{urllib.parse.quote(tracker_id)}?"
        + urllib.parse.urlencode({**auth, "idList": list_id})
    )
    log.info("trello move card=%s list=%s", tracker_id, done_name)
    _http_json("PUT", card_url)


TrackerDoneFn = Callable[..., None]

TRACKER_DONE: dict[str, TrackerDoneFn] = {
    "github": tracker_done_github,
    "jira": tracker_done_jira,
    "linear": tracker_done_linear,
    "notion": tracker_done_notion,
    "trello": tracker_done_trello,
}


def tracker_mark_done(
    project_root: Path,
    *,
    ref: str,
    tracker_id: str | None,
    plan_path: Path,
    folder: str | None = None,
) -> None:
    cfg = load_store_config(project_root)
    store = str(_tickets_table(cfg).get("store") or "repo")
    tid = (tracker_id or "").strip()
    if not tid:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            f"store is {store}: cannot mark done without tracker_id for {ref}",
        )
    handler = TRACKER_DONE.get(store)
    if handler is None:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            f"no mark-done handler for store {store!r}; supported: "
            + ", ".join(sorted(TRACKER_DONE)),
        )
    log.info("tracker mark-done store=%s ref=%s tracker_id=%s", store, ref, tid)
    handler(project_root, tracker_id=tid, cfg=cfg)
    tickets_mirror(
        project_root,
        [{"ref": ref, "tracker_id": tid, "tracker_status": "done"}],
        folder=folder,
    )
    log.info("set plan status done path=%s", plan_path)
    set_plan_status(plan_path, "done")


# --------------------------------------------------------------------------- plan / deferred IO


def read_frontmatter(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip("\n")
    data = yaml.safe_load(block) or {}
    return data if isinstance(data, dict) else {}


def set_plan_status(path: Path, status: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"plan has no frontmatter: {path}")
    end = text.find("\n---", 3)
    if end < 0:
        raise OrchestratorHalt(SHUTDOWN_ERROR, f"plan frontmatter not closed: {path}")
    block = text[3:end].strip("\n")
    data = yaml.safe_load(block) or {}
    if not isinstance(data, dict):
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"plan frontmatter is not a mapping: {path}"
        )
    data["status"] = status
    new_block = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).rstrip()
    path.write_text(f"---\n{new_block}\n---{text[end + 4 :]}", encoding="utf-8")


def initiative_dir_for(plan_path: Path, project_root: Path) -> Path:
    """Locate the initiative folder that owns deferred-work.md."""
    root = project_root.resolve()
    for parent in [plan_path.resolve().parent, *plan_path.resolve().parents]:
        if parent == root or root not in parent.parents:
            break
        if (parent / "deferred-work.md").is_file():
            return parent
        if (parent / "tickets").is_dir() and (
            (parent / f"{parent.name}.md").is_file()
            or parent.name.startswith("initiative")
        ):
            return parent
    for parent in plan_path.resolve().parents:
        if parent.name.startswith("initiative") and (parent / "tickets").is_dir():
            return parent
    raise OrchestratorHalt(
        SHUTDOWN_ERROR, f"cannot locate initiative for plan {plan_path}"
    )


def append_deferred(plan_path: Path, project_root: Path, items: list[Any]) -> int:
    if not items:
        return 0
    initiative = initiative_dir_for(plan_path, project_root)
    dest = initiative / "deferred-work.md"
    try:
        rel_plan = str(plan_path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        rel_plan = str(plan_path)
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary", "")).strip() or "(no summary)"
        evidence = str(item.get("evidence", "")).strip() or "(no evidence)"
        chunk = [
            f"- source_plan: `{rel_plan}`",
            f"  summary: {summary}",
            f"  evidence: {evidence}",
        ]
        for key in ("location", "severity"):
            if item.get(key):
                chunk.append(f"  {key}: {item[key]}")
        lines.append("\n".join(chunk))
    if not lines:
        return 0
    existing = (
        dest.read_text(encoding="utf-8") if dest.is_file() else "# Deferred work\n"
    )
    if not existing.endswith("\n"):
        existing += "\n"
    if not existing.endswith("\n\n"):
        existing += "\n"
    dest.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


# --------------------------------------------------------------------------- git / gh


def run_git(
    project_root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args], cwd=project_root, capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            proc.stderr.strip()
            or proc.stdout.strip()
            or f"git {' '.join(args)} failed",
        )
    return proc


def require_clean_tree(project_root: Path) -> None:
    log.info("checking clean working tree")
    proc = run_git(project_root, "status", "--porcelain")
    if proc.stdout.strip():
        raise OrchestratorHalt(SHUTDOWN_DIRTY_TREE, "working tree is not clean")


def current_branch(project_root: Path) -> str:
    return run_git(project_root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def has_unpushed_or_new_commits(project_root: Path) -> bool:
    """True when HEAD has commits not on origin for this branch (or no upstream)."""
    branch = current_branch(project_root)
    if branch in PROTECTED_BRANCHES:
        return False
    # Always attempt push after successful work; caller decides --no-push.
    return True


def ensure_push_and_pr(
    project_root: Path,
    *,
    epic: str | None,
    refs: list[str],
    no_push: bool,
    dry_run: bool,
) -> str | None:
    if dry_run or no_push:
        log.info("skip push/PR dry_run=%s no_push=%s refs=%s", dry_run, no_push, refs)
        return None
    branch = current_branch(project_root)
    if branch in PROTECTED_BRANCHES:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"refusing to push protected branch {branch}"
        )
    log.info("git push -u origin HEAD branch=%s", branch)
    push = subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if push.returncode != 0:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            push.stderr.strip() or push.stdout.strip() or "git push failed",
        )

    view = subprocess.run(
        ["gh", "pr", "view", "--json", "url"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if view.returncode == 0:
        try:
            url = json.loads(view.stdout).get("url")
            log.info("existing PR url=%s", url)
            return url
        except json.JSONDecodeError:
            return None

    epic_slug = epic or "build"
    title = f"feat({epic_slug}): orchestrated build for {', '.join(refs)}"
    if len(title) > 72:
        title = f"feat({epic_slug}): orchestrated build"
    body = "\n".join(
        [
            "## Summary",
            *(f"- Orchestrated BMAD build for `{r}`" for r in refs),
            "",
            "## Test plan",
            "- [ ] Review agent-produced commits and plan status",
            "- [ ] Confirm CI on this PR",
        ]
    )
    log.info("gh pr create title=%s", title)
    create = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if create.returncode != 0:
        # Race: PR may exist now
        view2 = subprocess.run(
            ["gh", "pr", "view", "--json", "url"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )
        if view2.returncode == 0:
            try:
                url = json.loads(view2.stdout).get("url")
                log.info("PR appeared after create race url=%s", url)
                return url
            except json.JSONDecodeError:
                pass
        raise OrchestratorHalt(
            SHUTDOWN_ERROR,
            create.stderr.strip() or create.stdout.strip() or "gh pr create failed",
        )
    url_lines = (create.stdout or "").strip().splitlines()
    url = url_lines[-1] if url_lines else None
    log.info("created PR url=%s", url)
    return url


# --------------------------------------------------------------------------- Cursor agent

# API id for Cursor Auto; "auto-smart" is not a valid models.list() id on current keys.
DEFAULT_MODEL_ID = "auto"
AGENT_START_MAX_ATTEMPTS = 3
_AGENT_TEXT_CAP = 200

_ANSI = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "white": "\033[97m",
    "cyan": "\033[36m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "red": "\033[31m",
    "blue": "\033[34m",
}


@dataclass
class AgentRunResult:
    status: str
    usage: TokenUsage | None
    agent_id: str | None
    run_id: str | None
    error: str | None = None


def resolve_agent_model(model: str) -> Any:
    from cursor_sdk import ModelParameterValue, ModelSelection

    # Accept legacy/alias "auto-smart" as the Auto + balanced selection.
    if model in {DEFAULT_MODEL_ID, "auto-smart"}:
        return ModelSelection(
            id="auto",
            params=[ModelParameterValue(id="optimize_for", value="balanced")],
        )
    return model


def _agent_color_enabled() -> bool:
    return sys.stderr.isatty() and not os.environ.get("NO_COLOR")


def _paint(style: str, text: str) -> str:
    if not _agent_color_enabled():
        return text
    code = _ANSI.get(style, "")
    if not code:
        return text
    return f"{code}{text}{_ANSI['reset']}"


def _truncate(text: str, cap: int = _AGENT_TEXT_CAP) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "…"


def _short_payload(value: Any, cap: int = _AGENT_TEXT_CAP) -> str:
    if value is None:
        return ""
    try:
        raw = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        raw = str(value)
    return _truncate(raw, cap)


def _emit_agent_line(kind: str, text: str) -> None:
    style = {
        "assistant": "white",
        "thinking": "cyan",
        "tool_running": "yellow",
        "tool_completed": "green",
        "tool_error": "red",
        "status": "blue",
        "task": "blue",
    }.get(kind, "")
    prefix = _paint("dim", "agent |")
    body = _paint(style, text) if style else text
    print(f"{prefix} {body}", file=sys.stderr, flush=True)


def _emit_agent_message(message: Any) -> None:
    msg_type = getattr(message, "type", None)
    if msg_type == "assistant":
        content = getattr(getattr(message, "message", None), "content", None) or ()
        for block in content:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "") or ""
                if text:
                    _emit_agent_line("assistant", text)
        return
    if msg_type == "thinking":
        text = getattr(message, "text", "") or ""
        if text:
            _emit_agent_line("thinking", f"thinking: {_truncate(text)}")
        return
    if msg_type == "tool_call":
        name = getattr(message, "name", "") or "tool"
        status = str(getattr(message, "status", "") or "")
        kind = {
            "running": "tool_running",
            "completed": "tool_completed",
            "error": "tool_error",
        }.get(status, "tool_running")
        parts = [f"tool {name}"]
        if status:
            parts.append(f"[{status}]")
        args = _short_payload(getattr(message, "args", None))
        if args:
            parts.append(f"args={args}")
        if status in {"completed", "error"}:
            result = _short_payload(getattr(message, "result", None))
            if result:
                parts.append(f"result={result}")
        _emit_agent_line(kind, " ".join(parts))
        return
    if msg_type == "status":
        status = getattr(message, "status", "") or ""
        detail = getattr(message, "message", "") or ""
        line = f"status: {status}"
        if detail:
            line = f"{line} {detail}"
        _emit_agent_line("status", line.strip())
        return
    if msg_type == "task":
        status = getattr(message, "status", "") or ""
        text = getattr(message, "text", "") or ""
        line = f"task: {status}"
        if text:
            line = f"{line} {text}"
        _emit_agent_line("task", line.strip())


def _soft_close_agent(agent: Any, err_type: type[BaseException]) -> None:
    if agent is None:
        return
    try:
        agent.close()
    except err_type as close_err:
        log.warning(
            "agent close failed: %s",
            getattr(close_err, "message", None) or close_err,
        )
    except Exception as close_err:  # noqa: BLE001 — never mask primary halt
        log.warning("agent close failed: %s", close_err)


def _retry_delay(err: Any, attempt: int) -> float:
    raw = getattr(err, "retry_after", None)
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    return float(min(2 ** (attempt - 1), 2))


def run_cursor_agent(
    *,
    project_root: Path,
    model: str,
    prompt: str,
    dry_run: bool,
) -> AgentRunResult:
    if dry_run:
        log.info("[dry-run] agent prompt:\n%s", prompt)
        return AgentRunResult(status="dry_run", usage=None, agent_id=None, run_id=None)

    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        raise OrchestratorHalt(SHUTDOWN_ERROR, "CURSOR_API_KEY is not set")

    from cursor_sdk import Agent, CursorAgentError, LocalAgentOptions

    resolved_model = resolve_agent_model(model)
    log.info("agent start model=%s", model)

    for attempt in range(1, AGENT_START_MAX_ATTEMPTS + 1):
        agent: Any = None
        phase = "create"
        try:
            agent = Agent.create(
                model=resolved_model,
                api_key=api_key,
                local=LocalAgentOptions(
                    cwd=str(project_root), setting_sources=["project"]
                ),
            )
            agent_id = getattr(agent, "agent_id", None) or getattr(
                agent, "agentId", None
            )
            log.info("agent created agent_id=%s", agent_id)

            phase = "send"
            run = agent.send(prompt)
            run_id = getattr(run, "run_id", None) or getattr(run, "id", None)
            log.info("agent sent agent_id=%s run_id=%s", agent_id, run_id)

            phase = "stream"
            for message in run.messages():
                _emit_agent_message(message)

            phase = "wait"
            result = run.wait()
            usage = None
            raw_usage = getattr(result, "usage", None) or getattr(run, "usage", None)
            if raw_usage is not None:
                usage = TokenUsage(
                    input_tokens=int(getattr(raw_usage, "input_tokens", 0) or 0),
                    output_tokens=int(getattr(raw_usage, "output_tokens", 0) or 0),
                    total_tokens=int(getattr(raw_usage, "total_tokens", 0) or 0),
                )
            status = getattr(result, "status", None) or "unknown"
            err = None
            if status == "error":
                err = f"agent run failed: {run_id}"
                log.error("agent error run_id=%s %s", run_id, format_token_cost(usage))
            else:
                log.info(
                    "agent finished status=%s agent_id=%s run_id=%s %s",
                    status,
                    agent_id,
                    run_id,
                    format_token_cost(usage),
                )
            return AgentRunResult(
                status=str(status),
                usage=usage,
                agent_id=str(agent_id) if agent_id else None,
                run_id=str(run_id) if run_id else None,
                error=err,
            )
        except KeyboardInterrupt as err:
            _soft_close_agent(agent, CursorAgentError)
            agent = None
            raise OrchestratorHalt(
                SHUTDOWN_ERROR, f"interrupted during agent {phase}"
            ) from err
        except CursorAgentError as err:
            _soft_close_agent(agent, CursorAgentError)
            agent = None
            if (
                phase in {"create", "send"}
                and err.is_retryable
                and attempt < AGENT_START_MAX_ATTEMPTS
            ):
                delay = _retry_delay(err, attempt)
                log.warning(
                    "agent retry attempt=%s/%s phase=%s after=%ss detail=%s",
                    attempt + 1,
                    AGENT_START_MAX_ATTEMPTS,
                    phase,
                    delay,
                    err.message,
                )
                time.sleep(delay)
                continue
            raise OrchestratorHalt(
                SHUTDOWN_ERROR,
                f"Cursor agent {phase} failed: {err.message} "
                f"(retryable={err.is_retryable})",
            ) from err
        finally:
            _soft_close_agent(agent, CursorAgentError)

    raise OrchestratorHalt(SHUTDOWN_ERROR, "Cursor agent create/send retries exhausted")


def usage_dict(usage: TokenUsage | None) -> dict[str, int] | None:
    if usage is None:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


# --------------------------------------------------------------------------- orchestration


def first_ready(next_payload: dict[str, Any]) -> dict[str, Any] | None:
    ready = next_payload.get("ready_to_start") or []
    if ready:
        return ready[0]
    backlog = next_payload.get("backlog")
    if isinstance(backlog, dict):
        ready = backlog.get("ready_to_start") or []
        if ready:
            return ready[0]
    return None


def _is_bug_row(row: dict[str, Any]) -> bool:
    if str(row.get("type") or "").lower() == "bug":
        return True
    name = str(row.get("ref") or row.get("file") or "")
    return name.startswith("bug-")


def _refine_rows(next_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in next_payload.get("ready_to_refine") or []:
        if isinstance(item, dict):
            rows.append(item)
    backlog = next_payload.get("backlog")
    if isinstance(backlog, dict):
        for item in backlog.get("ready_to_refine") or []:
            if isinstance(item, dict):
                rows.append(item)
    return rows


def collect_unrefined_bugs(next_payload: dict[str, Any]) -> list[dict[str, str]]:
    """Bug rows in ready_to_refine (initiative + nested backlog)."""
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in _refine_rows(next_payload):
        if not _is_bug_row(row):
            continue
        ref = str(row.get("ref") or row.get("file") or row.get("id") or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        entry: dict[str, str] = {"ref": ref}
        title = str(row.get("title") or "").strip()
        if title:
            entry["title"] = title
        out.append(entry)
    return out


def explain_unrefined_bugs(bugs: list[dict[str, str]], stream=sys.stderr) -> None:
    print("=== Unrefined bugs (not buildable yet) ===", file=stream)
    for bug in bugs:
        title = bug.get("title") or ""
        suffix = f" — {title}" if title else ""
        print(f"  {bug['ref']}{suffix}", file=stream)
    print(
        "These bugs sit in ready_to_refine until refined: true.\n"
        "This orchestrator only runs bmad-build-auto; it does not refine.\n"
        "Ask Sofia (skill bmad-agent-po) to refine each ticket, then re-run.",
        file=stream,
    )


def prompt_unrefined_bugs_action() -> str:
    """Interactive choice: continue | abort. Loops until a valid answer."""
    while True:
        try:
            answer = (
                input(
                    "Unrefined bugs waiting. [c]ontinue with ready_to_start only, "
                    "[a]bort so you can refine first? "
                )
                .strip()
                .lower()
            )
        except EOFError:
            return "abort"
        if answer in ("c", "continue"):
            return "continue"
        if answer in ("a", "abort"):
            return "abort"
        print("Please enter c or a.", file=sys.stderr)


def gate_unrefined_bugs(
    report: RunReport,
    next_payload: dict[str, Any],
    *,
    yes: bool,
    ready_exists: bool,
) -> None:
    """Explain unrefined bugs; optionally ask; halt when abort or only-bugs queue."""
    bugs = collect_unrefined_bugs(next_payload)
    report.unrefined_bugs = bugs
    if not bugs:
        return
    explain_unrefined_bugs(bugs)
    log.warning("unrefined bugs count=%s", len(bugs))
    interactive = sys.stdin.isatty() and not yes
    if interactive:
        action = prompt_unrefined_bugs_action()
        log.info("unrefined bugs user action=%s", action)
        if action == "abort":
            refs = ", ".join(b["ref"] for b in bugs)
            raise OrchestratorHalt(
                SHUTDOWN_UNREFINED_BUGS,
                f"aborted with unrefined bugs: {refs}",
            )
    if not ready_exists:
        refs = ", ".join(b["ref"] for b in bugs)
        raise OrchestratorHalt(
            SHUTDOWN_UNREFINED_BUGS,
            f"no ready_to_start work; refine first: {refs}",
        )


def epic_fully_done(project_root: Path, epic: str) -> bool:
    if not epic or epic == "backlog":
        return False
    try:
        status = tickets_status(project_root, epic)
    except OrchestratorHalt:
        return False
    tickets = status.get("tickets") or []
    if not tickets:
        return False
    return all(t.get("state") == "done" or t.get("status") == "done" for t in tickets)


def build_prompt(ref: str, *, halt_after_planning: bool = False) -> str:
    base = f"Run skill bmad-build-auto for ticket {ref}. Do not start any other ticket."
    if halt_after_planning:
        return base + " Halt after planning."
    return base


def retro_prompt(epic_ref: str) -> str:
    return f"Run skill bmad-retrospective -H {epic_ref}. Headless."


def process_ticket(
    *,
    project_root: Path,
    ref: str,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
    followup_used: bool = False,
) -> str | None:
    """Process one ticket. Returns epic slug if that epic just became fully done."""
    try:
        found = tickets_find(project_root, ref)
    except OrchestratorHalt as e:
        if e.shutdown == SHUTDOWN_ERROR and "no ticket matches" in (e.detail or ""):
            raise OrchestratorHalt(SHUTDOWN_TICKET_NOT_RESOLVED, e.detail) from e
        raise

    ticket_ref = str(found.get("ref") or ref)
    epic = found.get("epic")
    plan_path = Path(found["plan"]) if found.get("plan") else None
    plan_fm = read_frontmatter(plan_path) if plan_path else {}
    plan_status = str(plan_fm.get("status") or "")
    tracker_id = str(found.get("tracker_id") or "").strip() or None

    plan_checkpoint = bool(found.get("plan_checkpoint"))
    done_checkpoint = bool(found.get("done_checkpoint"))

    # plan_checkpoint: halt-after-planning when plan is missing/draft (or not yet ready-for-dev).
    # If already ready-for-dev+, dispatch a normal implement resume.
    post_plan_statuses = (
        "ready-for-dev",
        "in-progress",
        "in-review",
        "built",
        "done",
        "blocked",
    )
    halt_after_planning = bool(
        plan_checkpoint and plan_status not in post_plan_statuses
    )

    log.info(
        "ticket start ref=%s epic=%s plan_status=%s tracker_id=%s "
        "plan_checkpoint=%s done_checkpoint=%s halt_after_planning=%s followup_used=%s",
        ticket_ref,
        epic,
        plan_status or "(none)",
        tracker_id,
        plan_checkpoint,
        done_checkpoint,
        halt_after_planning,
        followup_used,
    )

    if not dry_run:
        require_clean_tree(project_root)

    prompt = build_prompt(ticket_ref, halt_after_planning=halt_after_planning)
    agent = run_cursor_agent(
        project_root=project_root, model=model, prompt=prompt, dry_run=dry_run
    )

    unit = UnitReport(
        ref=ticket_ref,
        kind="ticket",
        epic=str(epic) if epic else None,
        tokens=usage_dict(agent.usage),
        agent_id=agent.agent_id,
        run_id=agent.run_id,
    )

    if dry_run:
        unit.outcome = "dry_run"
        unit.plan_status = plan_status or None
        report.add(unit)
        log_cumulative_tokens(report)
        return None

    if agent.error:
        unit.outcome = "error"
        unit.reason = agent.error
        report.add(unit)
        log_cumulative_tokens(report)
        raise OrchestratorHalt(SHUTDOWN_ERROR, agent.error)

    # Re-read plan after agent
    try:
        found = tickets_find(project_root, ticket_ref)
        tracker_id = str(found.get("tracker_id") or "").strip() or tracker_id
    except OrchestratorHalt:
        pass
    plan_path = Path(found["plan"]) if found.get("plan") else plan_path
    plan_fm = read_frontmatter(plan_path) if plan_path else {}
    plan_status = str(plan_fm.get("status") or "")
    unit.plan_status = plan_status or None
    done_checkpoint = bool(found.get("done_checkpoint")) or done_checkpoint
    log.info(
        "ticket post-agent ref=%s plan_status=%s %s",
        ticket_ref,
        plan_status or "(none)",
        format_token_cost(agent.usage),
    )

    if halt_after_planning:
        unit.outcome = "checkpoint"
        unit.reason = "plan_checkpoint: waiting for human plan approval"
        report.add(unit)
        log_cumulative_tokens(report)
        raise OrchestratorHalt(
            SHUTDOWN_PLAN_CHECKPOINT, f"ticket {ticket_ref}: plan checkpoint"
        )

    if plan_status == "blocked":
        reason = str(
            plan_fm.get("blocked_reason") or found.get("blocked_reason") or "blocked"
        )
        unit.outcome = "blocked"
        unit.reason = reason
        report.add(unit)
        log_cumulative_tokens(report)
        raise OrchestratorHalt(SHUTDOWN_BLOCKED, f"ticket {ticket_ref}: {reason}")

    if plan_status not in ("built", "done"):
        unit.outcome = "error"
        unit.reason = (
            f"unexpected plan status after agent: {plan_status or '(missing)'}"
        )
        report.add(unit)
        log_cumulative_tokens(report)
        raise OrchestratorHalt(SHUTDOWN_ERROR, unit.reason)

    deferred_items = plan_fm.get("deferred") or []
    if not isinstance(deferred_items, list):
        deferred_items = []
    if plan_path and deferred_items:
        unit.deferred_count = append_deferred(plan_path, project_root, deferred_items)
        log.info("deferred appended count=%s ref=%s", unit.deferred_count, ticket_ref)

    if done_checkpoint:
        unit.outcome = "checkpoint"
        unit.reason = "done_checkpoint: waiting for human continue"
        report.add(unit)
        log_cumulative_tokens(report)
        raise OrchestratorHalt(
            SHUTDOWN_DONE_CHECKPOINT, f"ticket {ticket_ref}: done checkpoint"
        )

    followup = bool(plan_fm.get("followup_review_recommended"))
    if followup and not followup_used:
        unit.outcome = "followup"
        report.add(unit)
        log_cumulative_tokens(report)
        log.info("followup re-dispatch ref=%s", ticket_ref)
        # One extra re-dispatch, then continue to mark policy on the second result.
        return process_ticket(
            project_root=project_root,
            ref=ticket_ref,
            report=report,
            model=model,
            dry_run=dry_run,
            no_push=no_push,
            followup_used=True,
        )

    if plan_path:
        tickets_mark_done(
            project_root,
            ticket_ref,
            plan_path,
            tracker_id=tracker_id,
        )
    unit.outcome = "done"
    log.info("ticket marked done ref=%s", ticket_ref)

    pr_url = None
    if has_unpushed_or_new_commits(project_root):
        pr_url = ensure_push_and_pr(
            project_root,
            epic=str(epic) if epic else None,
            refs=[ticket_ref],
            no_push=no_push,
            dry_run=dry_run,
        )
        unit.pr_url = pr_url
    report.add(unit)
    log_cumulative_tokens(report)

    if epic and epic_fully_done(project_root, str(epic)):
        log.info("epic fully done epic=%s", epic)
        return str(epic)
    return None


def run_retrospective(
    *,
    project_root: Path,
    epic: str,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
) -> None:
    log.info("retrospective start epic=%s", epic)
    if not dry_run:
        require_clean_tree(project_root)
    agent = run_cursor_agent(
        project_root=project_root,
        model=model,
        prompt=retro_prompt(epic),
        dry_run=dry_run,
    )
    unit = UnitReport(
        ref=epic,
        kind="retrospective",
        epic=epic,
        tokens=usage_dict(agent.usage),
        agent_id=agent.agent_id,
        run_id=agent.run_id,
    )
    if dry_run:
        unit.outcome = "dry_run"
        report.add(unit)
        log_cumulative_tokens(report)
        return
    if agent.error:
        unit.outcome = "error"
        unit.reason = agent.error
        report.add(unit)
        log_cumulative_tokens(report)
        raise OrchestratorHalt(SHUTDOWN_ERROR, agent.error)
    unit.outcome = "done"
    log.info(
        "retrospective agent finished epic=%s %s",
        epic,
        format_token_cost(agent.usage),
    )
    pr_url = ensure_push_and_pr(
        project_root,
        epic=epic,
        refs=[f"retrospective:{epic}"],
        no_push=no_push,
        dry_run=dry_run,
    )
    unit.pr_url = pr_url
    report.add(unit)
    log_cumulative_tokens(report)


def maybe_retro_after(
    epic: str | None,
    *,
    project_root: Path,
    report: RunReport,
    model: str,
    dry_run: bool,
    no_push: bool,
    retros_done: set[str],
) -> None:
    if not epic or epic in retros_done or epic == "backlog":
        log.info("retrospective skip epic=%s reason=ineligible", epic)
        return
    if not epic_fully_done(project_root, epic):
        log.info("retrospective skip epic=%s reason=not_fully_done", epic)
        return
    run_retrospective(
        project_root=project_root,
        epic=epic,
        report=report,
        model=model,
        dry_run=dry_run,
        no_push=no_push,
    )
    retros_done.add(epic)


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--ticket", metavar="REF", help="orchestrate a single ticket")
    g.add_argument(
        "--epic", metavar="REF", help="orchestrate all ready tickets in an epic"
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
        "--no-push", action="store_true", help="skip git push and gh pr create"
    )
    p.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="non-interactive: skip unrefined-bugs prompt (still explains; continues if ready work exists)",
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
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.log_level:
        log_level = args.log_level
    elif args.verbose:
        log_level = "INFO"
    else:
        log_level = "WARNING"
    configure_logging(log_level)

    report = RunReport()
    project_root = resolve_project_root(args.project_root)
    retros_done: set[str] = set()

    if args.ticket:
        mode = f"ticket:{args.ticket}"
    elif args.epic:
        mode = f"epic:{args.epic}"
    else:
        mode = "all"
    log.info(
        "orchestrate start mode=%s root=%s model=%s dry_run=%s no_push=%s yes=%s json=%s",
        mode,
        project_root,
        args.model,
        args.dry_run,
        args.no_push,
        args.yes,
        args.json,
    )

    try:
        if args.ticket:
            epic = process_ticket(
                project_root=project_root,
                ref=args.ticket,
                report=report,
                model=args.model,
                dry_run=args.dry_run,
                no_push=args.no_push,
            )
            maybe_retro_after(
                epic,
                project_root=project_root,
                report=report,
                model=args.model,
                dry_run=args.dry_run,
                no_push=args.no_push,
                retros_done=retros_done,
            )
            report.shutdown = SHUTDOWN_COMPLETED

        elif args.epic:
            nxt = tickets_next(project_root, args.epic)
            ready = nxt.get("ready_to_start") or []
            gate_unrefined_bugs(
                report,
                nxt,
                yes=args.yes,
                ready_exists=bool(ready),
            )
            while True:
                if not ready:
                    log.info("epic queue empty epic=%s", args.epic)
                    break
                ref = str(ready[0].get("ref") or ready[0].get("id"))
                log.info("epic queue next ref=%s", ref)
                epic = process_ticket(
                    project_root=project_root,
                    ref=ref,
                    report=report,
                    model=args.model,
                    dry_run=args.dry_run,
                    no_push=args.no_push,
                )
                # In dry-run, avoid infinite loop on the same ready ticket.
                if args.dry_run:
                    break
                maybe_retro_after(
                    epic or args.epic,
                    project_root=project_root,
                    report=report,
                    model=args.model,
                    dry_run=args.dry_run,
                    no_push=args.no_push,
                    retros_done=retros_done,
                )
                nxt = tickets_next(project_root, args.epic)
                ready = nxt.get("ready_to_start") or []
            if not args.dry_run and epic_fully_done(project_root, args.epic):
                maybe_retro_after(
                    args.epic,
                    project_root=project_root,
                    report=report,
                    model=args.model,
                    dry_run=args.dry_run,
                    no_push=args.no_push,
                    retros_done=retros_done,
                )
            report.shutdown = SHUTDOWN_COMPLETED

        else:
            # All mode: walk ready tickets/bugs across active initiative (+ backlog).
            seen: set[str] = set()
            nxt = tickets_next(project_root)
            gate_unrefined_bugs(
                report,
                nxt,
                yes=args.yes,
                ready_exists=first_ready(nxt) is not None,
            )
            while True:
                item = first_ready(nxt)
                if not item:
                    log.info("all-mode queue empty")
                    break
                ref = str(item.get("ref") or item.get("id"))
                if ref in seen:
                    raise OrchestratorHalt(
                        SHUTDOWN_ERROR,
                        f"ready ticket {ref} did not leave ready_to_start; refusing to loop",
                    )
                seen.add(ref)
                log.info("all-mode next ref=%s", ref)
                if args.dry_run:
                    process_ticket(
                        project_root=project_root,
                        ref=ref,
                        report=report,
                        model=args.model,
                        dry_run=True,
                        no_push=args.no_push,
                    )
                    break
                epic = process_ticket(
                    project_root=project_root,
                    ref=ref,
                    report=report,
                    model=args.model,
                    dry_run=False,
                    no_push=args.no_push,
                )
                maybe_retro_after(
                    epic,
                    project_root=project_root,
                    report=report,
                    model=args.model,
                    dry_run=False,
                    no_push=args.no_push,
                    retros_done=retros_done,
                )
                nxt = tickets_next(project_root)
            report.shutdown = SHUTDOWN_COMPLETED

    except OrchestratorHalt as halt:
        report.shutdown = halt.shutdown
        report.shutdown_detail = halt.detail
        log.warning(
            "orchestrate halt shutdown=%s detail=%s", halt.shutdown, halt.detail
        )

    log.info(
        "orchestrate finish shutdown=%s %s",
        report.shutdown,
        format_token_cost_from_report(report),
    )
    report.print_human(sys.stderr)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    if report.shutdown == SHUTDOWN_COMPLETED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
