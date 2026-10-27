"""External tracker store adapters (GitHub/Jira/Linear/Notion/Trello)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .constants import (
    SHUTDOWN_ERROR,
    STORE_NAME_RE,
    STORE_PROJECT_FILE,
    STORE_STARTERS,
    OrchestratorHalt,
    log,
)

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


def tracker_comment_github(
    project_root: Path, *, tracker_id: str, body: str, cfg: dict[str, Any]
) -> None:
    tickets = _tickets_table(cfg)
    repo = str(tickets.get("repo") or "").strip()
    r_args = ["-R", repo] if repo else []
    log.info("github comment issue=%s repo=%s", tracker_id, repo or "(default)")
    _run_checked(
        ["gh", "issue", "comment", tracker_id, *r_args, "--body", body],
        cwd=project_root,
    )


def tracker_comment_jira(
    project_root: Path, *, tracker_id: str, body: str, cfg: dict[str, Any]
) -> None:
    del cfg
    log.info("jira comment key=%s", tracker_id)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".txt", delete=False
    ) as tmp:
        tmp.write(body)
        tmp_path = tmp.name
    try:
        _run_checked(
            [
                "acli",
                "jira",
                "workitem",
                "comment",
                "create",
                "--key",
                tracker_id,
                "--body-file",
                tmp_path,
            ],
            cwd=project_root,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def tracker_comment_linear(
    project_root: Path, *, tracker_id: str, body: str, cfg: dict[str, Any]
) -> None:
    del project_root, cfg
    api_key = _require_env("LINEAR_API_KEY")
    log.info("linear comment issue=%s", tracker_id)
    payload = _http_json(
        "POST",
        "https://api.linear.app/graphql",
        headers={"Authorization": api_key},
        body={
            "query": (
                "mutation($issueId: String!, $body: String!) {"
                "  commentCreate(input: { issueId: $issueId, body: $body }) {"
                "    success"
                "  }"
                "}"
            ),
            "variables": {"issueId": tracker_id, "body": body},
        },
    )
    success = (((payload or {}).get("data") or {}).get("commentCreate") or {}).get(
        "success"
    )
    if not success:
        raise OrchestratorHalt(
            SHUTDOWN_ERROR, f"linear commentCreate failed: {payload}"
        )


def tracker_comment_notion(
    project_root: Path, *, tracker_id: str, body: str, cfg: dict[str, Any]
) -> None:
    del project_root, cfg
    token = _require_env("NOTION_TOKEN")
    page_id = _notion_page_id(tracker_id)
    # Notion rich_text items are capped at 2000 characters each.
    chunks = [body[i : i + 2000] for i in range(0, max(len(body), 1), 2000)] or [""]
    rich_text = [{"type": "text", "text": {"content": chunk}} for chunk in chunks[:100]]
    log.info("notion comment page=%s chunks=%s", page_id, len(rich_text))
    _http_json(
        "POST",
        "https://api.notion.com/v1/comments",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
        },
        body={"parent": {"page_id": page_id}, "rich_text": rich_text},
    )


def tracker_comment_trello(
    project_root: Path, *, tracker_id: str, body: str, cfg: dict[str, Any]
) -> None:
    del project_root, cfg
    key = _require_env("TRELLO_API_KEY")
    token = _require_env("TRELLO_TOKEN")
    auth = {"key": key, "token": token, "text": body}
    url = (
        f"https://api.trello.com/1/cards/{urllib.parse.quote(tracker_id)}/actions/comments?"
        + urllib.parse.urlencode(auth)
    )
    log.info("trello comment card=%s", tracker_id)
    _http_json("POST", url)


TrackerCommentFn = Callable[..., None]

TRACKER_COMMENT: dict[str, TrackerCommentFn] = {
    "github": tracker_comment_github,
    "jira": tracker_comment_jira,
    "linear": tracker_comment_linear,
    "notion": tracker_comment_notion,
    "trello": tracker_comment_trello,
}


def tracker_post_report(
    project_root: Path,
    *,
    tracker_id: str,
    body: str,
) -> None:
    """Post a human RunReport comment to the ticket's tracker. Non-fatal on error."""
    tid = tracker_id.strip()
    if not tid:
        return
    try:
        cfg = load_store_config(project_root)
        store = str(_tickets_table(cfg).get("store") or "repo")
        handler = TRACKER_COMMENT.get(store)
        if handler is None:
            log.warning(
                "tracker comment skipped store=%s tracker_id=%s (no adapter)",
                store,
                tid,
            )
            return
        log.info("tracker comment store=%s tracker_id=%s", store, tid)
        handler(project_root, tracker_id=tid, body=body, cfg=cfg)
    except Exception as err:  # noqa: BLE001 — comment must not halt orchestration
        log.warning(
            "tracker comment failed tracker_id=%s: %s",
            tid,
            getattr(err, "detail", None) or err,
        )
