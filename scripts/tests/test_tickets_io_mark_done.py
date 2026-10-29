"""Tests for tracker mark-done: BMAD write-verb publish and GitHub close fast-path."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bmad_factory.agent import AgentRunResult
from bmad_factory.constants import SHUTDOWN_ERROR, FactoryHalt
from bmad_factory.policy import Policy
from bmad_factory.tickets_io import (
    _tracker_mark_done,
    build_tracker_write_prompt,
    tickets_mark_done,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _leaf(root: Path, name: str = "bug-demo.md") -> Path:
    return _write(
        root / "_bmad-output" / "backlog" / name,
        "---\ntype: bug\ntitle: Demo bug\nrisk: medium\n---\n\n# Demo\n",
    )


def _plan(root: Path, name: str = "bug-demo-plan.md") -> Path:
    return _write(
        root / "_bmad-output" / "backlog" / name,
        "---\ntype: 'bugfix'\nticket: 'bug-demo'\nstatus: 'built'\n---\n",
    )


def _agent_ok() -> AgentRunResult:
    return AgentRunResult(
        status="finished", usage=None, agent_id="a1", run_id="r1", error=None
    )


class BuildTrackerWritePromptTests(unittest.TestCase):
    def test_publish_vs_done_only_wording(self) -> None:
        base = dict(
            store="github",
            write_verb="Create with gh issue create.",
            tickets={"store": "github", "repo": "org/repo"},
            ref="bug-demo.md",
            story_file="/tmp/bug-demo.md",
            title="Demo",
            ticket_type="bug",
            folder="backlog",
            project_root=Path("/proj"),
            policy=None,
        )
        publish = build_tracker_write_prompt(**base, tracker_id=None)
        self.assertIn("Publish the leaf if unpublished", publish)
        self.assertIn("Write verb (follow exactly):", publish)
        self.assertIn("Create with gh issue create.", publish)
        self.assertIn("org/repo", publish)

        done_only = build_tracker_write_prompt(**base, tracker_id="42")
        self.assertIn("Already published as tracker_id=42", done_only)
        self.assertNotIn("Publish the leaf if unpublished", done_only)


class TrackerMarkDoneTests(unittest.TestCase):
    def test_empty_tracker_id_invokes_write_verb_agent_github(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = _leaf(root)
            plan = _plan(root)
            find_before = {
                "ref": "bug-demo.md",
                "story_file": str(leaf),
                "title": "Demo bug",
                "type": "bug",
                "tracker_id": "",
            }
            find_after = {**find_before, "tracker_id": "99"}
            cfg = {
                "tickets": {"store": "github", "repo": "org/repo"},
                "verbs": {"write": "gh issue create --title <t>"},
            }
            with (
                mock.patch(
                    "bmad_factory.tickets_io._load_store_config", return_value=cfg
                ),
                mock.patch(
                    "bmad_factory.tickets_io.tickets_find",
                    side_effect=[find_before, find_after],
                ) as find,
                mock.patch(
                    "bmad_factory.tickets_io.run_cursor_agent",
                    return_value=_agent_ok(),
                ) as agent,
                mock.patch("bmad_factory.tickets_io._github_mark_done") as gh,
                mock.patch("bmad_factory.tickets_io.tickets_mirror") as mirror,
                mock.patch("bmad_factory.tickets_io.set_plan_status") as set_status,
            ):
                _tracker_mark_done(
                    root,
                    ref="bug-demo.md",
                    tracker_id=None,
                    plan_path=plan,
                    folder="backlog",
                    policy=Policy(),
                    model="auto",
                    dry_run=False,
                )
            agent.assert_called_once()
            prompt = agent.call_args.kwargs["prompt"]
            self.assertIn("Publish the leaf if unpublished", prompt)
            self.assertIn("gh issue create", prompt)
            gh.assert_called_once_with(root, "99", cfg)
            self.assertEqual(find.call_count, 2)
            mirror.assert_called_once()
            set_status.assert_called_once_with(plan, "done")

    def test_empty_tracker_id_invokes_write_verb_agent_jira(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = _leaf(root)
            plan = _plan(root)
            find_before = {
                "ref": "bug-demo.md",
                "story_file": str(leaf),
                "title": "Demo bug",
                "type": "bug",
                "tracker_id": "",
            }
            find_after = {**find_before, "tracker_id": "SHOP-12"}
            cfg = {
                "tickets": {
                    "store": "jira",
                    "key": "SHOP",
                    "site": "https://example.atlassian.net",
                },
                "verbs": {"write": "acli jira workitem create ..."},
            }
            with (
                mock.patch(
                    "bmad_factory.tickets_io._load_store_config", return_value=cfg
                ),
                mock.patch(
                    "bmad_factory.tickets_io.tickets_find",
                    side_effect=[find_before, find_after],
                ),
                mock.patch(
                    "bmad_factory.tickets_io.run_cursor_agent",
                    return_value=_agent_ok(),
                ) as agent,
                mock.patch("bmad_factory.tickets_io.tickets_mirror"),
                mock.patch("bmad_factory.tickets_io.set_plan_status"),
            ):
                _tracker_mark_done(
                    root,
                    ref="bug-demo.md",
                    tracker_id="",
                    plan_path=plan,
                    folder=None,
                    policy=Policy(),
                )
            prompt = agent.call_args.kwargs["prompt"]
            self.assertIn("store 'jira'", prompt)
            self.assertIn("acli jira workitem create", prompt)
            self.assertIn("SHOP", prompt)

    def test_publish_agent_remote_close_failure_skips_mirror_and_plan_done(
        self,
    ) -> None:
        """Write-verb success + tracker_id must not mark done if remote close fails."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = _leaf(root)
            plan = _plan(root)
            find_before = {
                "ref": "bug-demo.md",
                "story_file": str(leaf),
                "title": "Demo bug",
                "type": "bug",
                "tracker_id": "",
            }
            find_after = {**find_before, "tracker_id": "99"}
            cfg = {
                "tickets": {"store": "github", "repo": "org/repo"},
                "verbs": {"write": "gh issue create --title <t>"},
            }
            with (
                mock.patch(
                    "bmad_factory.tickets_io._load_store_config", return_value=cfg
                ),
                mock.patch(
                    "bmad_factory.tickets_io.tickets_find",
                    side_effect=[find_before, find_after],
                ),
                mock.patch(
                    "bmad_factory.tickets_io.run_cursor_agent",
                    return_value=_agent_ok(),
                ),
                mock.patch(
                    "bmad_factory.tickets_io._github_mark_done",
                    side_effect=FactoryHalt(SHUTDOWN_ERROR, "gh issue close failed"),
                ),
                mock.patch("bmad_factory.tickets_io.tickets_mirror") as mirror,
                mock.patch("bmad_factory.tickets_io.set_plan_status") as set_status,
                self.assertRaises(FactoryHalt) as ctx,
            ):
                _tracker_mark_done(
                    root,
                    ref="bug-demo.md",
                    tracker_id=None,
                    plan_path=plan,
                    folder="backlog",
                    policy=Policy(),
                    model="auto",
                    dry_run=False,
                )
            self.assertIn("gh issue close failed", str(ctx.exception))
            mirror.assert_not_called()
            set_status.assert_not_called()

    def test_empty_tracker_id_agent_leaves_id_empty_halts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = _leaf(root)
            plan = _plan(root)
            found = {
                "ref": "bug-demo.md",
                "story_file": str(leaf),
                "title": "Demo bug",
                "type": "bug",
                "tracker_id": "",
            }
            cfg = {
                "tickets": {"store": "github", "repo": "org/repo"},
                "verbs": {"write": "create"},
            }
            with (
                mock.patch(
                    "bmad_factory.tickets_io._load_store_config", return_value=cfg
                ),
                mock.patch("bmad_factory.tickets_io.tickets_find", return_value=found),
                mock.patch(
                    "bmad_factory.tickets_io.run_cursor_agent",
                    return_value=_agent_ok(),
                ),
                mock.patch("bmad_factory.tickets_io.tickets_mirror") as mirror,
                self.assertRaises(FactoryHalt) as ctx,
            ):
                _tracker_mark_done(
                    root,
                    ref="bug-demo.md",
                    tracker_id=None,
                    plan_path=plan,
                    folder=None,
                    policy=Policy(),
                )
            self.assertIn("cannot mark done without tracker_id", str(ctx.exception))
            mirror.assert_not_called()

    def test_existing_github_tracker_id_closes_without_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _plan(root)
            cfg = {"tickets": {"store": "github", "repo": "org/repo"}, "verbs": {}}
            with (
                mock.patch(
                    "bmad_factory.tickets_io._load_store_config", return_value=cfg
                ),
                mock.patch("bmad_factory.tickets_io._github_mark_done") as gh,
                mock.patch("bmad_factory.tickets_io.run_cursor_agent") as agent,
                mock.patch("bmad_factory.tickets_io.tickets_mirror") as mirror,
                mock.patch("bmad_factory.tickets_io.set_plan_status") as set_status,
            ):
                _tracker_mark_done(
                    root,
                    ref="bug-demo.md",
                    tracker_id="42",
                    plan_path=plan,
                    folder="backlog",
                    policy=Policy(),
                )
            gh.assert_called_once()
            agent.assert_not_called()
            mirror.assert_called_once()
            set_status.assert_called_once_with(plan, "done")

    def test_existing_non_github_tracker_id_uses_write_verb_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = _leaf(root)
            plan = _plan(root)
            found = {
                "ref": "bug-demo.md",
                "story_file": str(leaf),
                "title": "Demo bug",
                "type": "bug",
                "tracker_id": "SHOP-12",
            }
            cfg = {
                "tickets": {"store": "jira", "key": "SHOP"},
                "verbs": {"write": "acli transition done"},
            }
            with (
                mock.patch(
                    "bmad_factory.tickets_io._load_store_config", return_value=cfg
                ),
                mock.patch("bmad_factory.tickets_io.tickets_find", return_value=found),
                mock.patch(
                    "bmad_factory.tickets_io.run_cursor_agent",
                    return_value=_agent_ok(),
                ) as agent,
                mock.patch("bmad_factory.tickets_io._github_mark_done") as gh,
                mock.patch("bmad_factory.tickets_io.tickets_mirror"),
                mock.patch("bmad_factory.tickets_io.set_plan_status"),
            ):
                _tracker_mark_done(
                    root,
                    ref="bug-demo.md",
                    tracker_id="SHOP-12",
                    plan_path=plan,
                    folder=None,
                    policy=Policy(),
                )
            agent.assert_called_once()
            self.assertIn(
                "Already published as tracker_id=SHOP-12",
                agent.call_args.kwargs["prompt"],
            )
            gh.assert_not_called()


class TicketsMarkDoneDispatchTests(unittest.TestCase):
    def test_store_refusal_dispatches_tracker_mark_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = _plan(root)
            refused = mock.Mock(
                returncode=2,
                stdout='{"error":"store is github: change status through the store\'s write verb, not this script"}',
                stderr="",
            )
            with (
                mock.patch(
                    "bmad_factory.tickets_io.subprocess.run", return_value=refused
                ),
                mock.patch(
                    "bmad_factory.tickets_io._tickets_bin",
                    return_value=["uv", "run", "tickets.py"],
                ),
                mock.patch("bmad_factory.tickets_io._tracker_mark_done") as tracker,
            ):
                tickets_mark_done(
                    root,
                    "bug-demo.md",
                    plan,
                    tracker_id=None,
                    policy=Policy(),
                    model="auto",
                    dry_run=False,
                )
            tracker.assert_called_once()
            self.assertIsNone(tracker.call_args.kwargs["tracker_id"])
            self.assertEqual(tracker.call_args.kwargs["model"], "auto")


if __name__ == "__main__":
    unittest.main()
