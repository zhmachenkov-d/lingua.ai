"""Tests for factory verify_cmd (require_diff + command runner)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bmad_factory.constants import SHUTDOWN_ERROR, FactoryHalt
from bmad_factory.policy import Policy, VerifyPolicy
from bmad_factory.verify_cmd import (
    has_code_diff_vs_target,
    run_policy_verify,
    run_verify_commands,
)


class HasCodeDiffTests(unittest.TestCase):
    def test_true_when_commits_ahead(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch(
                    "bmad_factory.verify_cmd.default_branch_tip",
                    return_value="origin/main",
                ),
                mock.patch("bmad_factory.verify_cmd.run_git") as run_git,
            ):

                def _side(root_arg, *args, check=True):
                    del root_arg, check
                    if args[:2] == ("rev-list", "--count"):
                        return mock.Mock(returncode=0, stdout="2\n", stderr="")
                    return mock.Mock(returncode=0, stdout="", stderr="")

                run_git.side_effect = _side
                self.assertTrue(has_code_diff_vs_target(root))

    def test_false_when_no_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch(
                    "bmad_factory.verify_cmd.default_branch_tip",
                    return_value="origin/main",
                ),
                mock.patch("bmad_factory.verify_cmd.run_git") as run_git,
            ):
                run_git.return_value = mock.Mock(returncode=0, stdout="", stderr="")
                self.assertFalse(has_code_diff_vs_target(root))


class RunVerifyCommandsTests(unittest.TestCase):
    def test_non_zero_halts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            verify = VerifyPolicy(commands=["python -c 'raise SystemExit(1)'"])
            with self.assertRaises(FactoryHalt) as ctx:
                run_verify_commands(root, verify, ticket_ref="story-1.md")
            self.assertEqual(ctx.exception.shutdown, SHUTDOWN_ERROR)
            self.assertIn("verify failed", ctx.exception.detail or "")

    def test_success_sets_quality_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Print env vars; exit 0.
            cmd = (
                'python -c "import os,sys; '
                "sys.exit(0 if os.environ.get('QUALITY_TICKET')=='t-1' else 1)\""
            )
            verify = VerifyPolicy(commands=[cmd])
            run_verify_commands(root, verify, ticket_ref="t-1", agent_run_id="r-9")


class RunPolicyVerifyTests(unittest.TestCase):
    def test_require_diff_blocks_empty_branch(self) -> None:
        policy = Policy(verify=VerifyPolicy(commands=[], require_diff=True))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch(
                    "bmad_factory.verify_cmd.has_code_diff_vs_target",
                    return_value=False,
                ),
                self.assertRaises(FactoryHalt) as ctx,
            ):
                run_policy_verify(root, policy, ticket_ref="story-x.md")
            self.assertIn("require_diff", ctx.exception.detail or "")

    def test_finish_path_invokes_verify_before_mark_done(self) -> None:
        """_finish_built must call run_policy_verify before tickets_mark_done."""
        from bmad_factory import pipeline as pipeline_mod
        from bmad_factory.report import RunReport
        from bmad_factory.run_state import RunState, UnitAttemptState

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = Policy(
                verify=VerifyPolicy(commands=["python -c 'pass'"], require_diff=False)
            )
            # Avoid mark_done side effects.
            policy.tickets.mark_done = "never"
            policy.scm.remote = "none"
            report = RunReport()
            run_state = RunState(run_id="run-1", completed_refs=[], task_phases={})
            unit_state = UnitAttemptState(
                ref="story-1.md", kind="ticket", phase="built"
            )

            order: list[str] = []

            def _verify(*_a, **_k):
                order.append("verify")

            def _mark(*_a, **_k):
                order.append("mark_done")

            with (
                mock.patch.object(
                    pipeline_mod, "run_policy_verify", side_effect=_verify
                ),
                mock.patch.object(pipeline_mod, "tickets_mark_done", side_effect=_mark),
                mock.patch.object(
                    pipeline_mod, "has_unpushed_or_new_commits", return_value=False
                ),
                mock.patch.object(pipeline_mod, "save_run"),
                mock.patch.object(pipeline_mod, "append_journal"),
                mock.patch.object(pipeline_mod, "log_cumulative_tokens"),
                mock.patch.object(pipeline_mod, "epic_fully_done", return_value=False),
            ):
                policy.tickets.mark_done = "auto"
                pipeline_mod._finish_built(
                    project_root=root,
                    report=report,
                    policy=policy,
                    run_state=run_state,
                    unit_state=unit_state,
                    ticket_ref="story-1.md",
                    epic=None,
                    ticket_type="story",
                    ticket_title="t",
                    tracker_id=None,
                    plan_path=root / "plan.md",
                    plan_fm={},
                    plan_status="built",
                    no_push=True,
                    dry_run=False,
                    model="auto",
                    tokens=None,
                    agent_id="a1",
                    run_id="r1",
                )
            self.assertEqual(order[0], "verify")
            self.assertIn("mark_done", order)
            self.assertLess(order.index("verify"), order.index("mark_done"))

    def test_verify_failure_blocks_finish(self) -> None:
        from bmad_factory import pipeline as pipeline_mod
        from bmad_factory.report import RunReport
        from bmad_factory.run_state import RunState, UnitAttemptState

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = Policy(verify=VerifyPolicy(commands=["x"], require_diff=False))
            policy.tickets.mark_done = "auto"
            policy.scm.remote = "none"
            report = RunReport()
            run_state = RunState(run_id="run-1", completed_refs=[], task_phases={})
            unit_state = UnitAttemptState(
                ref="story-1.md", kind="ticket", phase="built"
            )
            marked = {"n": 0}

            def _mark(*_a, **_k):
                marked["n"] += 1

            with (
                mock.patch.object(
                    pipeline_mod,
                    "run_policy_verify",
                    side_effect=FactoryHalt(SHUTDOWN_ERROR, "verify failed"),
                ),
                mock.patch.object(pipeline_mod, "tickets_mark_done", side_effect=_mark),
            ):
                with self.assertRaises(FactoryHalt):
                    pipeline_mod._finish_built(
                        project_root=root,
                        report=report,
                        policy=policy,
                        run_state=run_state,
                        unit_state=unit_state,
                        ticket_ref="story-1.md",
                        epic=None,
                        ticket_type="story",
                        ticket_title="t",
                        tracker_id=None,
                        plan_path=root / "plan.md",
                        plan_fm={},
                        plan_status="built",
                        no_push=True,
                        dry_run=False,
                        model="auto",
                        tokens=None,
                        agent_id="a1",
                        run_id="r1",
                    )
            self.assertEqual(marked["n"], 0)


if __name__ == "__main__":
    unittest.main()
