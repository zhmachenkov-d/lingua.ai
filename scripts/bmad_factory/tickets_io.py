"""tickets.py wrappers and mark-done (repo + tracker stores via BMAD write)."""

from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from .agent import agent_call_limits, run_cursor_agent
from .constants import (
    DEFAULT_MODEL_ID,
    SHUTDOWN_ERROR,
    STORE_NAME_RE,
    STORE_PROJECT_FILE,
    STORE_STARTERS,
    FactoryHalt,
    log,
)
from .plan_io import set_plan_status
from .policy import Policy
from .ticketmodel import (
    FindResult,
    NextView,
    StatusView,
    TicketsSchemaError,
    parse_find,
    parse_next,
    parse_status,
)


def _tickets_bin(project_root: Path, policy: Policy | None = None) -> list[str]:
    script_rel = policy.tickets.script if policy else "_bmad/method/scripts/tickets.py"
    script = project_root / script_rel
    if not script.is_file():
        raise FactoryHalt(SHUTDOWN_ERROR, f"missing {script}")
    return ["uv", "run", str(script), "--project-root", str(project_root)]


def tickets_cmd(
    project_root: Path, *args: str, policy: Policy | None = None
) -> dict[str, Any]:
    cmd = [*_tickets_bin(project_root, policy), *args]
    log.debug("tickets cmd: %s", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
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
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            err or raw_err or raw_out or f"tickets.py exited {proc.returncode}",
        )
    if not isinstance(payload, dict):
        raise FactoryHalt(
            SHUTDOWN_ERROR, f"tickets.py returned non-JSON: {raw_out[:200]}"
        )
    return payload


def tickets_next(
    project_root: Path, folder: str | None = None, *, policy: Policy | None = None
) -> dict[str, Any]:
    args = ["next"]
    if folder:
        args.append(folder)
    args.append("--synced")
    return tickets_cmd(project_root, *args, policy=policy)


def tickets_find(
    project_root: Path,
    ref: str,
    folder: str | None = None,
    *,
    policy: Policy | None = None,
) -> dict[str, Any]:
    args = ["find"]
    if folder:
        args.extend([folder, ref])
    else:
        args.append(ref)
    return tickets_cmd(project_root, *args, policy=policy)


def tickets_status(
    project_root: Path, folder: str | None = None, *, policy: Policy | None = None
) -> dict[str, Any]:
    args = ["status"]
    if folder:
        args.append(folder)
    return tickets_cmd(project_root, *args, policy=policy)


def _schema_halt(err: TicketsSchemaError) -> FactoryHalt:
    return FactoryHalt(
        SHUTDOWN_ERROR, f"tickets.py schema: {err.command}.{err.field}: {err.detail}"
    )


def load_next_view(
    project_root: Path, folder: str | None = None, *, policy: Policy | None = None
) -> NextView:
    try:
        return parse_next(tickets_next(project_root, folder, policy=policy))
    except TicketsSchemaError as err:
        raise _schema_halt(err) from err


def load_status_view(
    project_root: Path, folder: str | None = None, *, policy: Policy | None = None
) -> StatusView:
    try:
        return parse_status(tickets_status(project_root, folder, policy=policy))
    except TicketsSchemaError as err:
        raise _schema_halt(err) from err


def load_find_result(
    project_root: Path,
    ref: str,
    folder: str | None = None,
    *,
    policy: Policy | None = None,
) -> FindResult:
    try:
        return parse_find(tickets_find(project_root, ref, folder, policy=policy))
    except TicketsSchemaError as err:
        raise _schema_halt(err) from err


def tickets_mirror(
    project_root: Path,
    items: list[dict[str, Any]],
    folder: str | None = None,
    *,
    policy: Policy | None = None,
) -> dict[str, Any]:
    args = ["mirror"]
    if folder:
        args.append(folder)
    cmd = [*_tickets_bin(project_root, policy), *args]
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
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            err or raw_err or raw_out or f"tickets.py mirror exited {proc.returncode}",
        )
    if not isinstance(payload, dict):
        raise FactoryHalt(
            SHUTDOWN_ERROR, f"tickets.py mirror returned non-JSON: {raw_out[:200]}"
        )
    return payload


def _merge_toml(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_toml(out[key], value)
        else:
            out[key] = value
    return out


def _load_store_config(project_root: Path) -> dict[str, Any]:
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


def _github_mark_done(project_root: Path, tracker_id: str, cfg: dict[str, Any]) -> None:
    tickets = cfg.get("tickets") if isinstance(cfg.get("tickets"), dict) else {}
    repo = str((tickets or {}).get("repo") or "").strip()
    r_args = ["-R", repo] if repo else []
    log.info("github close issue=%s repo=%s", tracker_id, repo or "(default)")
    proc = subprocess.run(
        ["gh", "issue", "close", tracker_id, *r_args, "--reason", "completed"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "gh issue close failed"
        # Already closed is fine.
        if "already closed" not in err.lower():
            raise FactoryHalt(SHUTDOWN_ERROR, err)


def _store_address_lines(tickets: dict[str, Any]) -> str:
    """Non-empty ticket address fields for the write-verb agent prompt."""
    skip = {"store", "access"}
    lines: list[str] = []
    for key, value in tickets.items():
        if key in skip or isinstance(value, (dict, list)):
            continue
        text = str(value or "").strip()
        if text:
            lines.append(f"- {key}: {text}")
    access = str(tickets.get("access") or "").strip()
    if access:
        lines.append(f"- access: {access}")
    return "\n".join(lines) if lines else "- (none)"


def build_tracker_write_prompt(
    *,
    store: str,
    write_verb: str,
    tickets: dict[str, Any],
    ref: str,
    story_file: str,
    title: str,
    ticket_type: str,
    tracker_id: str | None,
    folder: str | None,
    project_root: Path,
    policy: Policy | None,
) -> str:
    """Prompt for a short agent that follows BMAD store verbs.write."""
    script_rel = policy.tickets.script if policy else "_bmad/method/scripts/tickets.py"
    mirror_args = f"mirror {folder}" if folder else "mirror"
    mirror_cmd = f"uv run {script_rel} --project-root {project_root} {mirror_args}"
    tid = (tracker_id or "").strip()
    if tid:
        publish_lines = (
            f"Already published as tracker_id={tid}. Do not create a duplicate. "
            "Transition the remote item to done only."
        )
    else:
        publish_lines = (
            "Publish the leaf if unpublished (create the remote item). "
            "Then transition it to done."
        )
    mirror_example = json.dumps(
        [
            {
                "ref": ref,
                "tracker_id": "<id>",
                "remote": "<url>",
                "tracker_status": "done",
            }
        ]
    )
    return (
        f"Mark ticket {ref} done on BMAD tracker store {store!r}.\n"
        f"{publish_lines}\n"
        f"Title: {title or '(none)'}\n"
        f"Type: {ticket_type or '(none)'}\n"
        f"Leaf file: {story_file}\n"
        "When sending body content, omit frontmatter keys tracker_id, remote, "
        "tracker_status, status, and assignee.\n"
        f"Store address fields:\n{_store_address_lines(tickets)}\n"
        f"Write verb (follow exactly):\n{write_verb.strip()}\n"
        "After the remote write, mirror into the leaf with stdin JSON, e.g.\n"
        f"  printf '%s' '{mirror_example}' | {mirror_cmd}\n"
        "Do not start any other ticket or skill."
    )


def _tracker_publish_and_done(
    project_root: Path,
    *,
    ref: str,
    tracker_id: str | None,
    plan_path: Path,
    folder: str | None,
    policy: Policy | None,
    cfg: dict[str, Any],
    model: str,
    dry_run: bool,
) -> None:
    """Publish (if needed) and mark done via BMAD store verbs.write agent."""
    tickets = cfg.get("tickets") if isinstance(cfg.get("tickets"), dict) else {}
    store = str((tickets or {}).get("store") or "repo")
    if store == "repo":
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            f"store is repo: tracker write path should not run for {ref}",
        )
    verbs = cfg.get("verbs") if isinstance(cfg.get("verbs"), dict) else {}
    write_verb = str((verbs or {}).get("write") or "").strip()
    if not write_verb:
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            f"store {store!r}: missing verbs.write; cannot publish/mark done for {ref}",
        )

    found = tickets_find(project_root, ref, folder, policy=policy)
    story = found.get("story_file")
    if not story:
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            f"store {store!r}: no leaf file to publish for {ref}",
        )
    story_path = Path(str(story))
    if not story_path.is_file():
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            f"store {store!r}: leaf file missing for {ref}: {story_path}",
        )

    prompt = build_tracker_write_prompt(
        store=store,
        write_verb=write_verb,
        tickets=dict(tickets or {}),
        ref=ref,
        story_file=str(story_path),
        title=str(found.get("title") or "").strip(),
        ticket_type=str(found.get("type") or "").strip(),
        tracker_id=tracker_id,
        folder=folder,
        project_root=project_root,
        policy=policy,
    )
    log.info(
        "tracker write via BMAD verbs.write store=%s ref=%s publish=%s",
        store,
        ref,
        not bool((tracker_id or "").strip()),
    )
    limits = policy.limits if policy else None
    agent = run_cursor_agent(
        project_root=project_root,
        model=model or DEFAULT_MODEL_ID,
        prompt=prompt,
        dry_run=dry_run,
        **agent_call_limits(limits),
    )
    if dry_run:
        log.info("[dry-run] tracker write skipped verification ref=%s", ref)
        return
    if agent.error:
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            f"store {store!r}: tracker write agent failed for {ref}: {agent.error}",
        )

    found_after = tickets_find(project_root, ref, folder, policy=policy)
    tid = str(found_after.get("tracker_id") or "").strip()
    if not tid:
        raise FactoryHalt(
            SHUTDOWN_ERROR,
            f"store is {store}: cannot mark done without tracker_id for {ref}",
        )
    tickets_mirror(
        project_root,
        [{"ref": ref, "tracker_id": tid, "tracker_status": "done"}],
        folder=folder,
        policy=policy,
    )
    set_plan_status(plan_path, "done")


def _tracker_mark_done(
    project_root: Path,
    *,
    ref: str,
    tracker_id: str | None,
    plan_path: Path,
    folder: str | None,
    policy: Policy | None,
    model: str = DEFAULT_MODEL_ID,
    dry_run: bool = False,
) -> None:
    cfg = _load_store_config(project_root)
    tickets = cfg.get("tickets") if isinstance(cfg.get("tickets"), dict) else {}
    store = str((tickets or {}).get("store") or "repo")
    tid = (tracker_id or "").strip()
    if not tid:
        _tracker_publish_and_done(
            project_root,
            ref=ref,
            tracker_id=None,
            plan_path=plan_path,
            folder=folder,
            policy=policy,
            cfg=cfg,
            model=model,
            dry_run=dry_run,
        )
        return
    if store == "github":
        _github_mark_done(project_root, tid, cfg)
        tickets_mirror(
            project_root,
            [{"ref": ref, "tracker_id": tid, "tracker_status": "done"}],
            folder=folder,
            policy=policy,
        )
        set_plan_status(plan_path, "done")
        return
    _tracker_publish_and_done(
        project_root,
        ref=ref,
        tracker_id=tid,
        plan_path=plan_path,
        folder=folder,
        policy=policy,
        cfg=cfg,
        model=model,
        dry_run=dry_run,
    )


def tickets_mark_done(
    project_root: Path,
    ref: str,
    plan_path: Path | None,
    *,
    tracker_id: str | None = None,
    folder: str | None = None,
    policy: Policy | None = None,
    model: str = DEFAULT_MODEL_ID,
    dry_run: bool = False,
) -> None:
    """Mark ticket done via tickets.py mark, or BMAD tracker write on store refusal."""
    args = ["mark"]
    if folder:
        args.extend([folder, ref, "done"])
    else:
        args.extend([ref, "done"])
    cmd = [*_tickets_bin(project_root, policy), *args]
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
        _tracker_mark_done(
            project_root,
            ref=ref,
            tracker_id=tracker_id,
            plan_path=plan_path,
            folder=folder,
            policy=policy,
            model=model,
            dry_run=dry_run,
        )
        return
    raise FactoryHalt(SHUTDOWN_ERROR, f"mark done failed: {err_msg}")
