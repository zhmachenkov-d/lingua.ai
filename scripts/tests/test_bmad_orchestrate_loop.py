"""Tests for policy, verify, run_state, worktrees, plateau-defer, and sweep."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bmad_orchestrate import pipeline as pipe
from bmad_orchestrate import scm as scm_mod
from bmad_orchestrate.agent import AgentRunResult, _stream_run_with_limits
from bmad_orchestrate.constants import (
    DEFAULT_AGENT_MAX_TOKENS,
    DEFAULT_AGENT_TIMEOUT_S,
)
from bmad_orchestrate.policy import (
    DEFAULT_POLICY_TOML,
    Policy,
    ensure_policy_template,
    load_policy,
)
from bmad_orchestrate.report import RunReport
from bmad_orchestrate.run_state import (
    ENGINE_NAME,
    PAUSE_BLOCKED,
    PAUSE_PLAN_CHECKPOINT,
    UnitAttemptState,
    confirm_parked,
    create_run,
    load_run,
    pause_run,
    resolve_blocked,
    save_run,
)
from bmad_orchestrate.scm import (
    worktree_branch_name,
    worktree_path_for,
)
from bmad_orchestrate.sweep import (
    close_ledger_entries,
    parse_ledger,
    parse_triage_response,
)
from bmad_orchestrate.verify import (
    VerifyPolicy,
    resolve_plan_status,
    verify_unit,
)


class PolicyTests(unittest.TestCase):
    def test_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = load_policy(root, create_if_missing=False)
            self.assertEqual(policy.scm.isolation, "worktree")
            self.assertEqual(policy.scm.remote, "none")
            self.assertEqual(policy.limits.max_dev_attempts, 2)
            self.assertEqual(policy.limits.agent_timeout_s, DEFAULT_AGENT_TIMEOUT_S)
            self.assertEqual(policy.limits.agent_max_tokens, DEFAULT_AGENT_MAX_TOKENS)
            self.assertEqual(policy.review.trigger, "recommended")
            self.assertEqual(policy.verify.commands, [])

    def test_creates_template_and_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = ensure_policy_template(root)
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("[scm]", text)
            self.assertIn("agent_timeout_s", text)
            self.assertIn("agent_max_tokens", text)
            policy = load_policy(root)
            self.assertEqual(policy.scm.merge_strategy, "squash")
            self.assertEqual(policy.effective_max_followup_reviews, 1)
            self.assertEqual(policy.limits.agent_timeout_s, 600)
            self.assertEqual(policy.limits.agent_max_tokens, 2_000_000)

    def test_loads_agent_call_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = ensure_policy_template(root)
            text = path.read_text(encoding="utf-8")
            text = text.replace("agent_timeout_s = 600", "agent_timeout_s = 120")
            text = text.replace(
                "agent_max_tokens = 2000000", "agent_max_tokens = 50000"
            )
            path.write_text(text, encoding="utf-8")
            policy = load_policy(root, create_if_missing=False)
            self.assertEqual(policy.limits.agent_timeout_s, 120)
            self.assertEqual(policy.limits.agent_max_tokens, 50_000)

    def test_rejects_negative_agent_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = ensure_policy_template(root)
            path.write_text(
                DEFAULT_POLICY_TOML.replace(
                    "agent_timeout_s = 600", "agent_timeout_s = -1"
                ),
                encoding="utf-8",
            )
            with self.assertRaises(Exception) as ctx:
                load_policy(root, create_if_missing=False)
            self.assertIn("agent_timeout_s", str(ctx.exception))

    def test_rejects_invalid_remote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = ensure_policy_template(root)
            path.write_text(
                DEFAULT_POLICY_TOML.replace('remote = "none"', 'remote = "force"'),
                encoding="utf-8",
            )
            with self.assertRaises(Exception) as ctx:
                load_policy(root, create_if_missing=False)
            self.assertIn("remote", str(ctx.exception))

    def test_tickets_mark_done_and_thorough_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = ensure_policy_template(root)
            text = path.read_text(encoding="utf-8")
            text = text.replace('mark_done = "auto"', 'mark_done = "never"')
            text = text.replace(
                'thorough_review = "never"', 'thorough_review = "high-risk"'
            )
            path.write_text(text, encoding="utf-8")
            policy = load_policy(root, create_if_missing=False)
            self.assertEqual(policy.tickets.mark_done, "never")
            self.assertEqual(policy.tickets.thorough_review, "high-risk")

    def test_rejects_invalid_thorough_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = ensure_policy_template(root)
            path.write_text(
                DEFAULT_POLICY_TOML.replace(
                    'thorough_review = "never"', 'thorough_review = "sometimes"'
                ),
                encoding="utf-8",
            )
            with self.assertRaises(Exception) as ctx:
                load_policy(root, create_if_missing=False)
            self.assertIn("thorough_review", str(ctx.exception))


class _FakeUsage:
    def __init__(self, total_tokens: int) -> None:
        self.input_tokens = total_tokens
        self.output_tokens = 0
        self.total_tokens = total_tokens
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0


class _FakeUsageMessage:
    type = "usage"

    def __init__(self, total_tokens: int) -> None:
        self.usage = _FakeUsage(total_tokens)


class _FakeResult:
    def __init__(
        self, status: str = "finished", usage: _FakeUsage | None = None
    ) -> None:
        self.status = status
        self.usage = usage


class _FakeRun:
    def __init__(
        self,
        messages: list[object],
        *,
        hang_s: float = 0.0,
        final_usage: _FakeUsage | None = None,
    ) -> None:
        self._messages = messages
        self._hang_s = hang_s
        self._cancelled = False
        self.id = "run-test"
        self.run_id = "run-test"
        self.usage = final_usage

    def messages(self):
        import time as _time

        for msg in self._messages:
            if self._hang_s > 0:
                _time.sleep(self._hang_s)
            yield msg

    def wait(self) -> _FakeResult:
        return _FakeResult(status="finished", usage=self.usage)

    def cancel(self) -> None:
        self._cancelled = True


class AgentLimitsTests(unittest.TestCase):
    def test_timeout_cancels_run(self) -> None:
        class _HangingRun(_FakeRun):
            def messages(self):
                import time as _time

                _time.sleep(2.0)
                if False:  # pragma: no cover
                    yield None

        hanging = _HangingRun([])
        outcome = _stream_run_with_limits(hanging, timeout_s=1, max_tokens=0)
        self.assertEqual(outcome.status, "cancelled")
        self.assertIn("timed out", outcome.error or "")
        self.assertTrue(hanging._cancelled)

    def test_token_limit_cancels_mid_stream(self) -> None:
        run = _FakeRun([_FakeUsageMessage(100)])
        outcome = _stream_run_with_limits(run, timeout_s=0, max_tokens=50)
        self.assertEqual(outcome.status, "error")
        self.assertIn("token limit", outcome.error or "")
        self.assertTrue(run._cancelled)
        self.assertIsNotNone(outcome.usage)
        assert outcome.usage is not None
        self.assertEqual(outcome.usage.total_tokens, 100)

    def test_token_limit_after_wait(self) -> None:
        usage = _FakeUsage(200)
        run = _FakeRun([], final_usage=usage)
        outcome = _stream_run_with_limits(run, timeout_s=0, max_tokens=150)
        self.assertEqual(outcome.status, "error")
        self.assertIn("token limit", outcome.error or "")
        self.assertTrue(run._cancelled)

    def test_success_under_limits(self) -> None:
        usage = _FakeUsage(10)
        run = _FakeRun([_FakeUsageMessage(10)], final_usage=usage)
        outcome = _stream_run_with_limits(run, timeout_s=5, max_tokens=100)
        self.assertEqual(outcome.status, "finished")
        self.assertIsNone(outcome.error)
        self.assertFalse(run._cancelled)


class VerifyTests(unittest.TestCase):
    def test_accepts_built_without_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "plan.md"
            plan.write_text("---\nstatus: built\n---\n", encoding="utf-8")
            with mock.patch(
                "bmad_orchestrate.verify.worktree_has_diff", return_value=True
            ):
                result = verify_unit(
                    project_root=root,
                    ticket_ref="bug-x.md",
                    plan_path=plan,
                    policy=VerifyPolicy(commands=[], require_diff=True),
                    baseline_rev="abc",
                    expect_diff=True,
                )
            self.assertTrue(result.ok)
            self.assertEqual(result.plan_status, "built")

    def test_rejects_missing_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_bmad-output").mkdir()
            plan = root / "plan.md"
            plan.write_text("---\ntitle: x\n---\n", encoding="utf-8")
            result = verify_unit(
                project_root=root,
                ticket_ref="bug-x.md",
                plan_path=plan,
                policy=VerifyPolicy(commands=[], require_diff=False),
                baseline_rev=None,
                expect_diff=False,
            )
            self.assertFalse(result.ok)
            self.assertIn("missing", result.summary)

    def test_result_file_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "missing-plan.md"
            result_path = root / "_bmad-output" / "bmad-build-auto-result-bug-x.md"
            result_path.parent.mkdir(parents=True)
            result_path.write_text("---\nstatus: blocked\n---\n", encoding="utf-8")
            status, _, fm, found, from_result = resolve_plan_status(
                project_root=root,
                ticket_ref="bug-x.md",
                plan_path=plan,
            )
            self.assertEqual(status, "blocked")
            self.assertTrue(from_result)
            self.assertEqual(found, result_path)


class RunStateTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = create_run(root, mode="all", model="auto")
            state.current_unit = UnitAttemptState(ref="bug-x.md", phase="build")
            save_run(root, state)
            loaded = load_run(root, state.run_id)
            self.assertEqual(loaded.run_id, state.run_id)
            self.assertEqual(loaded.engine, ENGINE_NAME)
            assert loaded.current_unit is not None
            self.assertEqual(loaded.current_unit.ref, "bug-x.md")

    def test_refuse_foreign_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = create_run(root, mode="ticket", model="auto", ticket="x")
            path = root / ".bmad-orchestrate" / "runs" / state.run_id / "state.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["engine"] = "other-engine"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(Exception) as ctx:
                load_run(root, state.run_id)
            self.assertIn("foreign engine", str(ctx.exception))

    def test_resolve_and_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = create_run(root, mode="ticket", model="auto", ticket="bug-x.md")
            state.current_unit = UnitAttemptState(
                ref="bug-x.md", phase="build", dev_attempts=2
            )
            pause_run(
                root, state, reason=PAUSE_BLOCKED, detail="blocked", ticket="bug-x.md"
            )
            resolve_blocked(root, state, ticket="bug-x.md")
            self.assertEqual(state.status, "running")
            assert state.current_unit is not None
            self.assertEqual(state.current_unit.dev_attempts, 0)

            pause_run(
                root,
                state,
                reason=PAUSE_PLAN_CHECKPOINT,
                detail="plan",
                ticket="bug-x.md",
            )
            confirm_parked(root, state, ticket="bug-x.md")
            self.assertEqual(state.status, "running")
            self.assertEqual(state.current_unit.phase, "build")
            self.assertTrue(state.current_unit.extra.get("plan_checkpoint_cleared"))

    def test_confirm_pick_plan_checkpoint_records_approval(self) -> None:
        from bmad_orchestrate.run_state import PAUSE_PICK_PLAN_CHECKPOINT

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = create_run(root, mode="all", model="auto")
            pause_run(
                root,
                state,
                reason=PAUSE_PICK_PLAN_CHECKPOINT,
                detail="approve story",
                ticket="1.1",
            )
            confirm_parked(root, state, ticket="1.1")
            self.assertEqual(state.status, "running")
            self.assertIn("1.1", state.ticket_story_approvals)

    def test_resolve_escalation_clears_escalated_phase(self) -> None:
        from bmad_orchestrate.run_state import PAUSE_PICK_ESCALATION

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = create_run(root, mode="all", model="auto")
            state.task_phases["1.1"] = "escalated"
            pause_run(
                root,
                state,
                reason=PAUSE_PICK_ESCALATION,
                detail="blocked plan",
                ticket="1.1",
            )
            resolve_blocked(root, state, ticket="1.1")
            self.assertEqual(state.status, "running")
            self.assertNotIn("1.1", state.task_phases)


class PickLoopHaltTests(unittest.TestCase):
    def test_halt_before_dispatch_does_not_call_process_ticket(self) -> None:
        from bmad_orchestrate import cli as cli_mod
        from bmad_orchestrate.policy import Policy
        from bmad_orchestrate.report import RunReport
        from bmad_orchestrate.tickets_source import (
            HALT_HITL,
            PAUSE_TICKET_HITL,
            Halt,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_bmad").mkdir()
            state = create_run(root, mode="all", model="auto")
            report = RunReport()
            halt = Halt(HALT_HITL, "1.1", None, "1.1 is a hitl ticket")
            with (
                mock.patch.object(cli_mod, "load_next_view"),
                mock.patch.object(cli_mod, "load_status_view"),
                mock.patch.object(cli_mod, "decide_pick", return_value=halt),
                mock.patch.object(cli_mod, "process_ticket") as process,
            ):
                with self.assertRaises(Exception) as ctx:
                    cli_mod._execute_run_loop(
                        project_root=root,
                        report=report,
                        policy=Policy(),
                        run_state=state,
                        model="auto",
                        dry_run=False,
                        no_push=True,
                        yes=True,
                        ticket=None,
                        epic=None,
                    )
                process.assert_not_called()
                self.assertIn("hitl", str(ctx.exception).lower())
            loaded = load_run(root, state.run_id)
            self.assertEqual(loaded.status, "paused")
            self.assertEqual(loaded.pause_reason, PAUSE_TICKET_HITL)


class WorktreeNamingTests(unittest.TestCase):
    def test_branch_and_path(self) -> None:
        self.assertEqual(
            worktree_branch_name("20260101T000000-abcd", "bug-x.md"),
            "bmad-orch/20260101t000000-abcd/bug-x.md",
        )
        root = Path("/repo")
        path = worktree_path_for(root, "run1", "Epic One")
        self.assertEqual(
            path, root / ".bmad-orchestrate" / "worktrees" / "run1" / "epic-one"
        )


class PlateauDeferTests(unittest.TestCase):
    def test_plateau_after_exhausted_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "plan.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text("---\nstatus: in-progress\n---\n", encoding="utf-8")
            report = RunReport()
            policy = Policy()
            policy.limits.max_dev_attempts = 2
            policy.verify.require_diff = False
            policy.review.trigger = "never"
            policy.scm.isolation = "inplace"
            policy.scm.remote = "none"
            run_state = create_run(root, mode="ticket", model="auto", ticket="bug-x.md")
            found = {
                "ref": "bug-x.md",
                "plan": str(plan),
                "tracker_id": "",
                "type": "bug",
                "title": "x",
                "plan_checkpoint": False,
                "done_checkpoint": False,
            }
            agent = AgentRunResult(
                status="finished",
                usage=None,
                agent_id="a1",
                run_id="r1",
                error=None,
            )
            bad = mock.Mock(
                ok=False,
                plan_status="in-progress",
                plan_path=plan,
                plan_fm={"status": "in-progress"},
                result_path=None,
                status_from_result_only=False,
                summary="verify failed",
                command_outputs=["fail"],
                messages=["verify failed"],
            )
            with (
                mock.patch.object(pipe, "tickets_find", return_value=found),
                mock.patch.object(pipe, "require_clean_tree"),
                mock.patch.object(pipe, "checkout_work_branch", return_value="bmad/x"),
                mock.patch.object(pipe, "run_cursor_agent", return_value=agent),
                mock.patch("bmad_orchestrate.pipeline.verify_unit", return_value=bad),
                mock.patch.object(
                    scm_mod,
                    "run_git",
                    return_value=mock.Mock(stdout="abc\n", returncode=0),
                ),
            ):
                result = pipe.process_ticket(
                    project_root=root,
                    ref="bug-x.md",
                    report=report,
                    model="auto",
                    dry_run=False,
                    no_push=True,
                    policy=policy,
                    run_state=run_state,
                )
            self.assertIsNone(result)
            self.assertEqual(report.units[-1].outcome, "plateau_deferred")
            self.assertIn("bug-x.md", run_state.deferred_refs)


class SweepHarvestTests(unittest.TestCase):
    def test_parse_and_close_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deferred-work.md"
            path.write_text(
                "# Deferred work\n\n"
                "- source_plan: `plans/a-plan.md`\n"
                "  summary: leftover test\n"
                "  evidence: saw it\n"
                "  severity: low\n",
                encoding="utf-8",
            )
            entries = parse_ledger(path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].summary, "leftover test")
            closed = close_ledger_entries(path, {entries[0].key})
            self.assertEqual(closed, 1)
            self.assertIn("status: closed", path.read_text(encoding="utf-8"))
            self.assertEqual(parse_ledger(path), [])

    def test_parse_triage_json(self) -> None:
        keys = {"p::s"}
        triage = parse_triage_response(
            json.dumps(
                {
                    "resolved": ["p::s"],
                    "skip": [],
                    "blocked": [],
                    "bundles": [
                        {
                            "title": "cleanup",
                            "intent": "remove leftover",
                            "entry_keys": ["p::s"],
                            "needs_decision": False,
                        }
                    ],
                }
            ),
            known_keys=keys,
        )
        self.assertEqual(triage.resolved_keys, ["p::s"])
        self.assertEqual(len(triage.bundles), 1)
        self.assertEqual(triage.bundles[0].intent, "remove leftover")


class FreshReviewAgentTests(unittest.TestCase):
    def test_review_creates_new_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "plan.md"
            plan.write_text(
                "---\nstatus: built\nfollowup_review_recommended: true\ndeferred: []\n---\n",
                encoding="utf-8",
            )
            report = RunReport()
            policy = Policy()
            policy.limits.max_dev_attempts = 1
            policy.limits.max_review_cycles = 1
            policy.review.trigger = "recommended"
            policy.review.max_followup_reviews = 1
            policy.verify.require_diff = False
            policy.scm.isolation = "inplace"
            policy.scm.remote = "none"
            policy.gates.done_checkpoint = False
            run_state = create_run(root, mode="ticket", model="auto", ticket="bug-x.md")
            found = {
                "ref": "bug-x.md",
                "plan": str(plan),
                "tracker_id": "",
                "type": "bug",
                "title": "x",
                "plan_checkpoint": False,
                "done_checkpoint": False,
            }
            agents = [
                AgentRunResult("ok", None, "implementer", "r1"),
                AgentRunResult("ok", None, "reviewer", "r2"),
            ]
            calls: list[dict] = []

            def fake_agent(**kwargs):
                calls.append(kwargs)
                return agents.pop(0)

            ok = mock.Mock(
                ok=True,
                plan_status="built",
                plan_path=plan,
                plan_fm={
                    "status": "built",
                    "followup_review_recommended": True,
                    "deferred": [],
                },
                result_path=None,
                status_from_result_only=False,
                summary="ok",
                command_outputs=[],
                messages=[],
            )
            with (
                mock.patch.object(pipe, "tickets_find", return_value=found),
                mock.patch.object(pipe, "require_clean_tree"),
                mock.patch.object(pipe, "checkout_work_branch", return_value="bmad/x"),
                mock.patch.object(pipe, "run_cursor_agent", side_effect=fake_agent),
                mock.patch.object(pipe, "tickets_mark_done"),
                mock.patch.object(pipe, "land_unit", return_value=None),
                mock.patch.object(pipe, "epic_fully_done", return_value=False),
                mock.patch("bmad_orchestrate.pipeline.verify_unit", return_value=ok),
                mock.patch.object(
                    scm_mod,
                    "run_git",
                    return_value=mock.Mock(stdout="abc\n", returncode=0),
                ),
            ):
                pipe.process_ticket(
                    project_root=root,
                    ref="bug-x.md",
                    report=report,
                    model="auto",
                    dry_run=False,
                    no_push=True,
                    policy=policy,
                    run_state=run_state,
                )
            self.assertGreaterEqual(len(calls), 2)
            # Review call must not resume the implementer.
            self.assertIsNone(calls[1].get("resume_agent_id"))
            self.assertIn("follow-up review", calls[1]["prompt"])
            self.assertEqual(report.units[-1].outcome, "done")


if __name__ == "__main__":
    unittest.main()
