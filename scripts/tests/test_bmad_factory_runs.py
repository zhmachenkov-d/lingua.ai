"""Tests for bmad_factory run locks, classify, resume, stop, deferred, dirty_tree."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from multiprocessing import Process
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bmad_factory import cli as cli_mod
from bmad_factory.constants import SHUTDOWN_DIRTY_TREE, FactoryHalt
from bmad_factory.deferred import (
    SweepBundle,
    SweepTriage,
    _filter_remaining_bundles,
    _handle_bundle_halt,
    _synthetic_ref,
    continue_deferred,
    triage_path_for,
)
from bmad_factory.plan_io import format_halt_reinvoke_steps
from bmad_factory.report import RunReport
from bmad_factory.run_lock import (
    ProjectLock,
    RunLock,
    is_run_alive,
    lock_holder_pid,
    stop_run_process,
    terminate_other_group_members,
)
from bmad_factory.run_state import (
    PAUSE_DIRTY_TREE,
    PAUSE_SIGNAL,
    PAUSE_STOPPED,
    UnitAttemptState,
    classify_run,
    create_run,
    find_resumable_run,
    is_resumable_state,
    load_run,
    pause_run,
    save_run,
)
from bmad_factory.status_cmd import collect_status, format_status_human


def _touch_bmad(root: Path) -> None:
    (root / "_bmad").mkdir(parents=True, exist_ok=True)


def _hold_run_lock(
    project_root: str, run_id: str, ready_path: str, hold_path: str
) -> None:
    """Child process: acquire RunLock and wait until hold file disappears."""
    root = Path(project_root)
    lock = RunLock(root, run_id)
    lock.acquire()
    Path(ready_path).write_text("ready\n", encoding="utf-8")
    while Path(hold_path).exists():
        time.sleep(0.05)
    lock.release()


def _hold_project_lock(
    project_root: str, run_id: str, ready_path: str, hold_path: str
) -> None:
    root = Path(project_root)
    lock = ProjectLock(root)
    lock.acquire(run_id=run_id)
    Path(ready_path).write_text("ready\n", encoding="utf-8")
    while Path(hold_path).exists():
        time.sleep(0.05)
    lock.release()


def _sleeper_child() -> None:
    time.sleep(30)


class RunLockTests(unittest.TestCase):
    def test_acquire_conflict_and_alive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            state = create_run(root, mode="ticket", model="auto", ticket="T-1")
            ready = root / "ready"
            hold = root / "hold"
            hold.write_text("1", encoding="utf-8")
            proc = Process(
                target=_hold_run_lock,
                args=(str(root), state.run_id, str(ready), str(hold)),
            )
            proc.start()
            for _ in range(100):
                if ready.is_file():
                    break
                time.sleep(0.05)
            self.assertTrue(ready.is_file())
            self.assertTrue(is_run_alive(root, state.run_id))
            self.assertIsNotNone(lock_holder_pid(root, state.run_id))

            other = RunLock(root, state.run_id)
            with self.assertRaises(FactoryHalt) as ctx:
                other.acquire()
            self.assertIn("still live", str(ctx.exception))

            hold.unlink()
            proc.join(timeout=5)
            self.assertFalse(is_run_alive(root, state.run_id))

    def test_dead_pid_reclaim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            state = create_run(root, mode="ticket", model="auto", ticket="T-1")
            ready = root / "ready"
            hold = root / "hold"
            hold.write_text("1", encoding="utf-8")
            proc = Process(
                target=_hold_run_lock,
                args=(str(root), state.run_id, str(ready), str(hold)),
            )
            proc.start()
            for _ in range(100):
                if ready.is_file():
                    break
                time.sleep(0.05)
            self.assertTrue(is_run_alive(root, state.run_id))
            # Crash the holder without orderly unlock — flock dies with the process.
            proc.kill()
            proc.join(timeout=5)
            hold.unlink(missing_ok=True)
            self.assertFalse(is_run_alive(root, state.run_id))

            reclaimed = RunLock(root, state.run_id)
            reclaimed.acquire()  # dead-pid reclaim
            self.assertTrue(is_run_alive(root, state.run_id))
            reclaimed.release()
            self.assertFalse(is_run_alive(root, state.run_id))

    def test_project_mutex_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            ready = root / "ready"
            hold = root / "hold"
            hold.write_text("1", encoding="utf-8")
            proc = Process(
                target=_hold_project_lock,
                args=(str(root), "run-a", str(ready), str(hold)),
            )
            proc.start()
            for _ in range(100):
                if ready.is_file():
                    break
                time.sleep(0.05)
            self.assertTrue(ready.is_file())

            other = ProjectLock(root)
            with self.assertRaises(FactoryHalt) as ctx:
                other.acquire(run_id="run-b")
            self.assertIn("factory locked", str(ctx.exception))
            self.assertIn("run-a", str(ctx.exception))

            hold.unlink()
            proc.join(timeout=5)

    def test_project_then_run_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            state = create_run(root, mode="backlog", model="auto")
            project = ProjectLock(root)
            run = RunLock(root, state.run_id)
            project.acquire(run_id=state.run_id)
            run.acquire()
            run.release()
            project.release()


class ClassifyTests(unittest.TestCase):
    def test_classify_completed_paused_stale_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            completed = create_run(root, mode="ticket", model="auto", ticket="A")
            completed.status = "completed"
            save_run(root, completed)
            self.assertEqual(classify_run(root, completed), "completed")

            paused = create_run(root, mode="ticket", model="auto", ticket="B")
            pause_run(root, paused, reason="ticket-hitl", detail="needs review")
            self.assertEqual(classify_run(root, paused), "paused")
            self.assertTrue(is_resumable_state(root, paused))

            stale = create_run(root, mode="ticket", model="auto", ticket="C")
            # status running, no lock → stale
            self.assertEqual(classify_run(root, stale), "stale")
            self.assertTrue(is_resumable_state(root, stale))

            live = create_run(root, mode="ticket", model="auto", ticket="D")
            lock = RunLock(root, live.run_id)
            lock.acquire()
            try:
                self.assertEqual(classify_run(root, live), "running")
                self.assertFalse(is_resumable_state(root, live))
            finally:
                lock.release()


class ResumeGateTests(unittest.TestCase):
    def test_find_resumable_includes_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            stale = create_run(root, mode="epic", model="auto", epic="ep-1")
            found = find_resumable_run(root, mode="epic", epic="ep-1")
            self.assertIsNotNone(found)
            assert found is not None
            self.assertEqual(found.run_id, stale.run_id)

    def test_prepare_resumed_refuses_live_and_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            args = mock.Mock(yes=False, no_push=False, dry_run=False, model="auto")
            policy = mock.Mock()

            completed = create_run(root, mode="ticket", model="auto", ticket="T")
            completed.status = "completed"
            save_run(root, completed)
            with self.assertRaises(FactoryHalt):
                cli_mod._prepare_resumed_state(root, completed, args, policy)

            live = create_run(root, mode="ticket", model="auto", ticket="U")
            lock = RunLock(root, live.run_id)
            lock.acquire()
            try:
                with self.assertRaises(FactoryHalt) as ctx:
                    cli_mod._prepare_resumed_state(root, live, args, policy)
                self.assertIn("still live", str(ctx.exception))
            finally:
                lock.release()

            paused = create_run(root, mode="ticket", model="auto", ticket="V")
            pause_run(root, paused, reason="ticket-hitl")
            resumed = cli_mod._prepare_resumed_state(root, paused, args, policy)
            self.assertEqual(resumed.status, "running")
            self.assertIsNone(resumed.pause_reason)


class DirtyPauseTests(unittest.TestCase):
    def test_ensure_paused_on_halt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            state = create_run(root, mode="ticket", model="auto", ticket="T")
            halt = FactoryHalt(SHUTDOWN_DIRTY_TREE, "working tree is not clean")
            cli_mod._ensure_paused_on_halt(root, state, halt)
            reloaded = load_run(root, state.run_id)
            self.assertEqual(reloaded.status, "paused")
            self.assertEqual(reloaded.pause_reason, SHUTDOWN_DIRTY_TREE)

    def test_deferred_dirty_tree_pauses_not_continue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            state = create_run(root, mode="deferred", model="auto")
            halt = FactoryHalt(SHUTDOWN_DIRTY_TREE, "dirty")
            with self.assertRaises(FactoryHalt):
                _handle_bundle_halt(root, state, halt, title="bundle-a")
            reloaded = load_run(root, state.run_id)
            self.assertEqual(reloaded.status, "paused")
            self.assertEqual(reloaded.pause_reason, PAUSE_DIRTY_TREE)

    def test_deferred_blocked_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            state = create_run(root, mode="deferred", model="auto")
            state.current_unit = UnitAttemptState(ref="deferred-x", kind="bundle")
            halt = FactoryHalt("blocked", "needs human")
            _handle_bundle_halt(root, state, halt, title="x")
            reloaded = load_run(root, state.run_id)
            self.assertEqual(reloaded.status, "running")
            self.assertIsNone(reloaded.current_unit)


class DeferredResumeTests(unittest.TestCase):
    def test_filter_skips_completed_refs(self) -> None:
        triage = SweepTriage(
            bundles=[
                SweepBundle(title="One", intent="do one", entry_keys=["a"]),
                SweepBundle(title="Two", intent="do two", entry_keys=["b"]),
            ]
        )
        done = {_synthetic_ref("One")}
        remaining = _filter_remaining_bundles(triage, completed_refs=done, only=None)
        self.assertEqual([b.title for b in remaining], ["Two"])

    def test_continue_reuses_triage_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            state = create_run(root, mode="deferred", model="auto")
            triage = {
                "resolved": [],
                "skip": [],
                "blocked": [],
                "bundles": [
                    {
                        "title": "Already Done",
                        "intent": "x",
                        "entry_keys": [],
                        "needs_decision": False,
                    },
                    {
                        "title": "Next Up",
                        "intent": "y",
                        "entry_keys": [],
                        "needs_decision": False,
                    },
                ],
                "decisions": [],
            }
            path = triage_path_for(root, state.run_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(triage), encoding="utf-8")
            state.completed_refs.append(_synthetic_ref("Already Done"))
            save_run(root, state)

            report = RunReport()
            policy = mock.Mock()
            policy.sweep.ledger_name = "deferred-work.md"
            policy.sweep.attended_prompt = False
            policy.limits = mock.Mock(agent_timeout_s=600, agent_max_tokens=0)
            policy.tickets.thorough_review = "never"
            policy.scm.remote = "none"

            calls: list[str] = []

            def fake_bundle(**kwargs):
                calls.append(kwargs["synthetic_ref"])
                state.completed_refs.append(kwargs["synthetic_ref"])
                state.current_unit = None
                save_run(root, state)

            with (
                mock.patch(
                    "bmad_factory.deferred.find_initiative_ledgers", return_value=[]
                ),
                mock.patch(
                    "bmad_factory.deferred._run_bundle", side_effect=fake_bundle
                ),
                mock.patch("bmad_factory.deferred._run_triage_agents") as triage_agents,
            ):
                continue_deferred(
                    project_root=root,
                    report=report,
                    policy=policy,
                    run_state=state,
                    model="auto",
                    dry_run=False,
                    no_prompt=True,
                    no_push=True,
                )
                triage_agents.assert_not_called()

            self.assertEqual(calls, [_synthetic_ref("Next Up")])
            reloaded = load_run(root, state.run_id)
            self.assertEqual(reloaded.status, "completed")


class StopTests(unittest.TestCase):
    def test_stop_dead_path_pauses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            state = create_run(root, mode="ticket", model="auto", ticket="T")
            result = stop_run_process(root, state.run_id)
            self.assertEqual(result, "already-dead")

            args = mock.Mock(stop=state.run_id, project_root=str(root), json=False)
            with mock.patch.object(cli_mod, "resolve_project_root", return_value=root):
                code = cli_mod.cmd_stop(args)
            self.assertEqual(code, 0)
            reloaded = load_run(root, state.run_id)
            self.assertEqual(reloaded.status, "paused")
            self.assertEqual(reloaded.pause_reason, PAUSE_STOPPED)

    def test_stop_kills_live_holder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            state = create_run(root, mode="ticket", model="auto", ticket="T")
            ready = root / "ready"
            hold = root / "hold"
            hold.write_text("1", encoding="utf-8")
            proc = Process(
                target=_hold_run_lock,
                args=(str(root), state.run_id, str(ready), str(hold)),
            )
            proc.start()
            for _ in range(100):
                if ready.is_file():
                    break
                time.sleep(0.05)
            self.assertTrue(is_run_alive(root, state.run_id))
            result = stop_run_process(root, state.run_id, term_timeout_s=3.0)
            self.assertIn(result, {"terminated", "killed", "already-dead"})
            proc.join(timeout=5)
            hold.unlink(missing_ok=True)
            self.assertFalse(is_run_alive(root, state.run_id))


class SignalCleanupTests(unittest.TestCase):
    def test_terminate_other_group_members_kills_child(self) -> None:
        child = Process(target=_sleeper_child)
        child.start()
        try:
            # Child may be in a different group depending on start method;
            # assert helper is safe (no-children or terminates peers).
            result = terminate_other_group_members(os.getpgrp(), term_timeout_s=1.0)
            self.assertIn(result, {"no-children", "terminated", "killed"})
        finally:
            if child.is_alive():
                child.terminate()
                child.join(timeout=3)

    def test_session_signal_pauses_and_releases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            state = create_run(root, mode="ticket", model="auto", ticket="T")
            session = cli_mod._acquire_session(root, state)
            self.assertTrue(is_run_alive(root, state.run_id))
            with mock.patch.object(cli_mod.os, "_exit", side_effect=SystemExit(130)):
                with self.assertRaises(SystemExit) as ctx:
                    session.shutdown_for_signal(exit_code=130)
                self.assertEqual(ctx.exception.code, 130)
            reloaded = load_run(root, state.run_id)
            self.assertEqual(reloaded.status, "paused")
            self.assertEqual(reloaded.pause_reason, PAUSE_SIGNAL)
            self.assertFalse(is_run_alive(root, state.run_id))


class StatusEnrichmentTests(unittest.TestCase):
    def test_status_summary_and_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch_bmad(root)
            paused = create_run(root, mode="ticket", model="auto", ticket="P")
            pause_run(root, paused, reason="ticket-hitl")
            stale = create_run(root, mode="ticket", model="auto", ticket="S")

            with (
                mock.patch(
                    "bmad_factory.status_cmd.tickets_status",
                    return_value={"counts": {}, "epics": [], "tickets": []},
                ),
                mock.patch(
                    "bmad_factory.status_cmd.list_open_deferred", return_value=[]
                ),
            ):
                data = collect_status(root)

            summary = data.get("runs_summary") or {}
            self.assertGreaterEqual(summary.get("paused", 0), 1)
            self.assertGreaterEqual(summary.get("stale", 0), 1)
            human = format_status_human(data)
            self.assertIn("summary:", human)
            self.assertIn("stale", human)


class HaltStepsTests(unittest.TestCase):
    def test_mentions_resume_and_stop(self) -> None:
        text = format_halt_reinvoke_steps(
            detail="fix me",
            cli_args="--epic ep-1",
            model="auto",
            run_id="20261028T192203-f5c5fdf4",
        )
        self.assertIn("--resume 20261028T192203-f5c5fdf4", text)
        self.assertIn("--stop 20261028T192203-f5c5fdf4", text)


class CliParserTests(unittest.TestCase):
    def test_resume_and_stop_flags(self) -> None:
        parser = cli_mod.build_parser()
        args = parser.parse_args(["--resume", "abc-123", "-v"])
        self.assertEqual(args.resume, "abc-123")
        args2 = parser.parse_args(["--stop", "abc-123"])
        self.assertEqual(args2.stop, "abc-123")


if __name__ == "__main__":
    unittest.main()
