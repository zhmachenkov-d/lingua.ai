"""Unit tests for scripts/bmad_orchestrate package."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import bmad_orchestrate as orch  # noqa: E402
from bmad_orchestrate import pipeline as pipe  # noqa: E402
from bmad_orchestrate import scm as scm_mod  # noqa: E402


class TicketSlugTests(unittest.TestCase):
    def test_strips_md_and_dirname(self) -> None:
        self.assertEqual(
            orch.ticket_slug_from_ref("backlog/bug-session-mirror.md"),
            "bug-session-mirror",
        )
        self.assertEqual(orch.ticket_slug_from_ref("bug-x"), "bug-x")


class FindResultTests(unittest.TestCase):
    def test_finds_nested_result_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = (
                root
                / "_bmad-output"
                / "initiative-mvp"
                / "bmad-build-auto-result-bug-x.md"
            )
            path.parent.mkdir(parents=True)
            path.write_text("---\nstatus: blocked\n---\n", encoding="utf-8")
            found = orch.find_build_auto_result(root, "bug-x")
            self.assertEqual(found, path)

    def test_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_bmad-output").mkdir()
            self.assertIsNone(orch.find_build_auto_result(root, "nope"))


class BlockedReasonTests(unittest.TestCase):
    def test_frontmatter_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.md"
            path.write_text(
                "---\nstatus: blocked\nblocked_reason: from-fm\n---\n"
                "Blocking condition: from-body\n",
                encoding="utf-8",
            )
            self.assertEqual(
                orch.blocked_reason_from_artifact(path, {"blocked_reason": "from-fm"}),
                "from-fm",
            )

    def test_body_blocking_condition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.md"
            path.write_text(
                "---\nstatus: blocked\n---\n\nBlocking condition: intent gap\n",
                encoding="utf-8",
            )
            self.assertEqual(
                orch.blocked_reason_from_artifact(path, {}),
                "intent gap",
            )


class FormatNextStepsTests(unittest.TestCase):
    def test_blocked_report_includes_redispatch(self) -> None:
        text = orch.format_blocked_redispatch_steps(
            ticket_ref="bug-x.md",
            reason="intent gap",
            artifact_path=Path("/tmp/result.md"),
            plan_path=Path("/tmp/bug-x-plan.md"),
            status_from_result_only=True,
            model="auto",
        )
        self.assertIn("Next steps to re-dispatch:", text)
        self.assertIn("bug-x.md", text)
        self.assertIn("intent gap", text)
        self.assertIn("store=github", text)
        self.assertIn(
            "uv run scripts/bmad_orchestrate.py --verbose --model=auto --ticket bug-x.md",
            text,
        )

    def test_missing_status_mentions_result_glob(self) -> None:
        text = orch.format_missing_status_next_steps(
            ticket_ref="bug-x.md",
            plan_path=Path("/tmp/bug-x-plan.md"),
            model="auto",
        )
        self.assertIn("bmad-build-auto-result-bug-x.md", text)
        self.assertIn("--ticket bug-x.md", text)


class RunReportNextStepsTests(unittest.TestCase):
    def test_format_human_appends_next_steps(self) -> None:
        report = orch.RunReport(
            shutdown=orch.SHUTDOWN_BLOCKED,
            shutdown_detail="ticket bug-x.md: intent gap",
            next_steps="Next steps to re-dispatch:\n1. What blocked it",
        )
        report.add(
            orch.UnitReport(
                ref="bug-x.md",
                kind="ticket",
                outcome="blocked",
                reason="intent gap",
            )
        )
        human = report.format_human()
        self.assertIn("Shutdown: blocked", human)
        self.assertIn("Next steps to re-dispatch:", human)
        data = report.to_dict()
        self.assertEqual(data["next_steps"], report.next_steps)


class ProcessTicketResultFallbackTests(unittest.TestCase):
    def _write_result(self, root: Path, slug: str, body: str) -> Path:
        path = (
            root
            / "_bmad-output"
            / "initiative-mvp"
            / f"bmad-build-auto-result-{slug}.md"
        )
        path.parent.mkdir(parents=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_missing_plan_result_blocked_raises_shutdown_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slug = "bug-session-mirror-never-written-on-turn-path"
            ref = f"{slug}.md"
            plan_path = root / "_bmad-output" / "backlog" / f"{slug}-plan.md"
            plan_path.parent.mkdir(parents=True)
            # Plan path known to find, but file absent → missing status.
            self._write_result(
                root,
                slug,
                "---\nstatus: blocked\n---\n\nBlocking condition: intent gap\n",
            )
            report = orch.RunReport()
            agent = mock.Mock(
                error=None,
                usage=None,
                agent_id="agent-1",
                run_id="run-1",
            )
            found = {
                "ref": ref,
                "plan": str(plan_path),
                "tracker_id": "72",
                "type": "bug",
                "title": "Session mirror",
                "plan_checkpoint": False,
                "done_checkpoint": False,
            }
            with (
                mock.patch.object(pipe, "tickets_find", return_value=found),
                mock.patch.object(pipe, "require_clean_tree"),
                mock.patch.object(pipe, "checkout_work_branch"),
                mock.patch.object(pipe, "run_cursor_agent", return_value=agent),
                mock.patch.object(pipe, "tracker_post_report"),
            ):
                with self.assertRaises(orch.OrchestratorHalt) as ctx:
                    orch.process_ticket(
                        project_root=root,
                        ref=ref,
                        report=report,
                        model="auto",
                        dry_run=False,
                        no_push=True,
                    )
            self.assertEqual(ctx.exception.shutdown, orch.SHUTDOWN_BLOCKED)
            self.assertIn("intent gap", ctx.exception.detail or "")
            self.assertEqual(report.shutdown, orch.SHUTDOWN_BLOCKED)
            self.assertIsNotNone(report.next_steps)
            assert report.next_steps is not None
            self.assertIn("Next steps to re-dispatch:", report.next_steps)
            self.assertIn("--ticket ", report.next_steps)
            self.assertIn("store=github", report.next_steps)
            human = report.format_human()
            self.assertIn("Next steps to re-dispatch:", human)
            unit = report.units[-1]
            self.assertEqual(unit.outcome, "blocked")
            self.assertEqual(unit.plan_status, "blocked")

    def test_plan_built_ignores_stale_result_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slug = "bug-x"
            ref = f"{slug}.md"
            plan_path = root / "_bmad-output" / "backlog" / f"{slug}-plan.md"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(
                "---\nstatus: built\nfollowup_review_recommended: false\ndeferred: []\n---\n",
                encoding="utf-8",
            )
            self._write_result(
                root,
                slug,
                "---\nstatus: blocked\n---\n\nBlocking condition: stale\n",
            )
            report = orch.RunReport()
            agent = mock.Mock(
                error=None,
                usage=None,
                agent_id="agent-1",
                run_id="run-1",
            )
            found = {
                "ref": ref,
                "plan": str(plan_path),
                "tracker_id": "",
                "type": "bug",
                "title": "x",
                "plan_checkpoint": False,
                "done_checkpoint": False,
            }

            def fake_mark_done(*_a, **_k):
                return None

            with (
                mock.patch.object(pipe, "tickets_find", return_value=found),
                mock.patch.object(pipe, "require_clean_tree"),
                mock.patch.object(pipe, "checkout_work_branch"),
                mock.patch.object(pipe, "run_cursor_agent", return_value=agent),
                mock.patch.object(
                    pipe, "tickets_mark_done", side_effect=fake_mark_done
                ),
                mock.patch.object(
                    scm_mod, "has_unpushed_or_new_commits", return_value=False
                ),
            ):
                orch.process_ticket(
                    project_root=root,
                    ref=ref,
                    report=report,
                    model="auto",
                    dry_run=False,
                    no_push=True,
                )
            self.assertIsNone(report.next_steps)
            self.assertEqual(report.units[-1].outcome, "done")
            self.assertEqual(report.units[-1].plan_status, "built")

    def test_missing_plan_and_no_result_is_error_with_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_bmad-output").mkdir()
            slug = "bug-missing"
            ref = f"{slug}.md"
            plan_path = root / "_bmad-output" / "backlog" / f"{slug}-plan.md"
            plan_path.parent.mkdir(parents=True)
            report = orch.RunReport()
            agent = mock.Mock(
                error=None,
                usage=None,
                agent_id="agent-1",
                run_id="run-1",
            )
            found = {
                "ref": ref,
                "plan": str(plan_path),
                "tracker_id": "",
                "type": "bug",
                "title": "x",
                "plan_checkpoint": False,
                "done_checkpoint": False,
            }
            with (
                mock.patch.object(pipe, "tickets_find", return_value=found),
                mock.patch.object(pipe, "require_clean_tree"),
                mock.patch.object(pipe, "checkout_work_branch"),
                mock.patch.object(pipe, "run_cursor_agent", return_value=agent),
            ):
                with self.assertRaises(orch.OrchestratorHalt) as ctx:
                    orch.process_ticket(
                        project_root=root,
                        ref=ref,
                        report=report,
                        model="auto",
                        dry_run=False,
                        no_push=True,
                    )
            self.assertEqual(ctx.exception.shutdown, orch.SHUTDOWN_ERROR)
            self.assertIn("(missing)", ctx.exception.detail or "")
            assert report.next_steps is not None
            self.assertIn("bmad-build-auto-result-bug-missing.md", report.next_steps)
            self.assertIn("Next steps to re-dispatch:", report.format_human())


class AheadOfDefaultTests(unittest.TestCase):
    def test_commits_ahead_equal_tips_is_zero(self) -> None:
        with (
            mock.patch.object(scm_mod, "default_branch_tip", return_value="origin/main"),
            mock.patch.object(
                scm_mod,
                "run_git",
                return_value=mock.Mock(returncode=0, stdout="0\n", stderr=""),
            ) as run_git,
        ):
            self.assertEqual(orch.commits_ahead_of_default(Path("/tmp/repo")), 0)
            run_git.assert_called_once_with(
                Path("/tmp/repo"), "rev-list", "--count", "origin/main..HEAD"
            )

    def test_commits_ahead_divergent_tip(self) -> None:
        with (
            mock.patch.object(scm_mod, "default_branch_tip", return_value="main"),
            mock.patch.object(
                scm_mod,
                "run_git",
                return_value=mock.Mock(returncode=0, stdout="3\n", stderr=""),
            ),
        ):
            self.assertEqual(orch.commits_ahead_of_default(Path("/tmp/repo")), 3)

    def test_commits_ahead_missing_tip_is_zero(self) -> None:
        with mock.patch.object(scm_mod, "default_branch_tip", return_value=None):
            self.assertEqual(orch.commits_ahead_of_default(Path("/tmp/repo")), 0)

    def test_has_unpushed_false_on_protected_branch(self) -> None:
        with mock.patch.object(scm_mod, "current_branch", return_value="main"):
            self.assertFalse(orch.has_unpushed_or_new_commits(Path("/tmp/repo")))

    def test_has_unpushed_true_when_ahead(self) -> None:
        with (
            mock.patch.object(scm_mod, "current_branch", return_value="bmad/work"),
            mock.patch.object(scm_mod, "commits_ahead_of_default", return_value=2),
        ):
            self.assertTrue(orch.has_unpushed_or_new_commits(Path("/tmp/repo")))

    def test_has_unpushed_false_when_not_ahead(self) -> None:
        with (
            mock.patch.object(scm_mod, "current_branch", return_value="bmad/work"),
            mock.patch.object(scm_mod, "commits_ahead_of_default", return_value=0),
        ):
            self.assertFalse(orch.has_unpushed_or_new_commits(Path("/tmp/repo")))


class EnsurePushAndPrEmptyDiffTests(unittest.TestCase):
    def test_skips_push_and_pr_when_not_ahead(self) -> None:
        with (
            mock.patch.object(scm_mod, "current_branch", return_value="bmad/work"),
            mock.patch.object(scm_mod, "commits_ahead_of_default", return_value=0),
            mock.patch.object(scm_mod, "default_branch", return_value="main"),
            mock.patch.object(scm_mod.subprocess, "run") as sp_run,
        ):
            url = orch.ensure_push_and_pr(
                Path("/tmp/repo"),
                epic="epic-x",
                refs=["retrospective:epic-x"],
                no_push=False,
                dry_run=False,
                kind="retrospective",
            )
        self.assertIsNone(url)
        sp_run.assert_not_called()


class RunRetrospectiveEmptyDiffTests(unittest.TestCase):
    def test_done_without_pr_when_no_commits_ahead(self) -> None:
        report = orch.RunReport()
        agent = mock.Mock(
            error=None,
            usage=None,
            agent_id="agent-retro",
            run_id="run-retro",
        )
        with (
            mock.patch.object(pipe, "require_clean_tree"),
            mock.patch.object(pipe, "checkout_work_branch"),
            mock.patch.object(pipe, "run_cursor_agent", return_value=agent),
            mock.patch.object(
                scm_mod, "has_unpushed_or_new_commits", return_value=False
            ) as ahead,
            mock.patch.object(scm_mod, "ensure_push_pr_and_merge") as push_merge,
        ):
            orch.run_retrospective(
                project_root=Path("/tmp/repo"),
                epic="epic-platform-foundation",
                report=report,
                model="auto",
                dry_run=False,
                no_push=False,
            )
        ahead.assert_called_once()
        push_merge.assert_not_called()
        self.assertEqual(len(report.units), 1)
        unit = report.units[0]
        self.assertEqual(unit.kind, "retrospective")
        self.assertEqual(unit.outcome, "done")
        self.assertIsNone(unit.pr_url)

    def test_pushes_when_ahead(self) -> None:
        report = orch.RunReport()
        agent = mock.Mock(
            error=None,
            usage=None,
            agent_id="agent-retro",
            run_id="run-retro",
        )
        with (
            mock.patch.object(pipe, "require_clean_tree"),
            mock.patch.object(pipe, "checkout_work_branch"),
            mock.patch.object(pipe, "run_cursor_agent", return_value=agent),
            mock.patch.object(scm_mod, "has_unpushed_or_new_commits", return_value=True),
            mock.patch.object(
                scm_mod, "ensure_push_pr_and_merge", return_value="https://example/pr/1"
            ) as push_merge,
        ):
            orch.run_retrospective(
                project_root=Path("/tmp/repo"),
                epic="epic-platform-foundation",
                report=report,
                model="auto",
                dry_run=False,
                no_push=False,
            )
        push_merge.assert_called_once()
        self.assertEqual(report.units[-1].pr_url, "https://example/pr/1")


class ProcessTicketPushGateTests(unittest.TestCase):
    def test_pushes_when_ahead(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slug = "bug-x"
            ref = f"{slug}.md"
            plan_path = root / "_bmad-output" / "backlog" / f"{slug}-plan.md"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(
                "---\nstatus: built\nfollowup_review_recommended: false\ndeferred: []\n---\n",
                encoding="utf-8",
            )
            report = orch.RunReport()
            agent = mock.Mock(
                error=None,
                usage=None,
                agent_id="agent-1",
                run_id="run-1",
            )
            found = {
                "ref": ref,
                "plan": str(plan_path),
                "tracker_id": "",
                "type": "bug",
                "title": "x",
                "plan_checkpoint": False,
                "done_checkpoint": False,
            }
            with (
                mock.patch.object(pipe, "tickets_find", return_value=found),
                mock.patch.object(pipe, "require_clean_tree"),
                mock.patch.object(pipe, "checkout_work_branch"),
                mock.patch.object(pipe, "run_cursor_agent", return_value=agent),
                mock.patch.object(pipe, "tickets_mark_done"),
                mock.patch.object(
                    scm_mod, "has_unpushed_or_new_commits", return_value=True
                ),
                mock.patch.object(
                    scm_mod,
                    "ensure_push_pr_and_merge",
                    return_value="https://example/pr/9",
                ) as push_merge,
                mock.patch.object(pipe, "epic_fully_done", return_value=False),
            ):
                orch.process_ticket(
                    project_root=root,
                    ref=ref,
                    report=report,
                    model="auto",
                    dry_run=False,
                    no_push=False,
                )
            push_merge.assert_called_once()
            self.assertEqual(report.units[-1].pr_url, "https://example/pr/9")


if __name__ == "__main__":
    unittest.main()
