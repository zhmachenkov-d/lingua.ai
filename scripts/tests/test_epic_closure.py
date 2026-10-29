"""Tests for epic retrospective parse, close eligibility, and backlog materialization."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bmad_factory.cli import _execute_pick_loop
from bmad_factory.constants import FactoryHalt
from bmad_factory.epic_closure import (
    ACCEPT_VERDICTS,
    ActionItem,
    EpicClosureResult,
    close_epic_container,
    extract_acceptance_detail,
    materialize_action_items,
    parse_retro_contract,
    process_epic_closure,
    retro_marker,
)
from bmad_factory.pick import (
    CLOSURE_REJECTED,
    HALT_AWAITING_CLOSURE,
    HALT_EPIC_REJECTED,
    Halt,
    Skip,
)
from bmad_factory.plan_io import read_frontmatter
from bmad_factory.report import RunReport
from bmad_factory.run_state import create_run


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _epic_tree(root: Path, slug: str = "epic-demo") -> tuple[Path, Path]:
    epic_dir = root / "_bmad-output" / "initiative-mvp" / "tickets" / slug
    epic_md = _write(
        epic_dir / f"{slug}.md",
        "---\n"
        "type: epic\n"
        'title: "Demo"\n'
        "id: 9\n"
        'tracker_id: "99"\n'
        "tracker_status: backlog\n"
        "covers: [R4]\n"
        "after: [epic-other]\n"
        "sources: [_bmad-output/initiative-mvp/initiative-mvp.md]\n"
        "---\n\n# Demo\n",
    )
    (root / "_bmad-output" / "backlog").mkdir(parents=True, exist_ok=True)
    return epic_md, epic_dir


def _frontmatter_block(text: str) -> str:
    assert text.startswith("---\n")
    end = text.find("\n---", 3)
    assert end > 0
    return text[4:end]


def _has_block_list_line(frontmatter: str) -> bool:
    return any(line.lstrip().startswith("- ") for line in frontmatter.splitlines())


class ParseRetroTests(unittest.TestCase):
    def test_accept_derives_closure_and_action_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            retro = _write(
                root / "epic-demo-retrospective.md",
                "---\n"
                "epic: epic-demo\n"
                "verdict: accepted-with-open-items\n"
                "criteria: declared\n"
                "headless: true\n"
                "action_items:\n"
                "  - id: R1\n"
                "    kind: remediation\n"
                "    disposition: fix-now\n"
                "    title: Fix the thing\n"
                "    owner: eng\n"
                "    summary: Because evidence.\n"
                "  - id: R2\n"
                "    kind: process\n"
                "    disposition: accept-as-is\n"
                "    title: Keep as is\n"
                "    summary: Fine.\n"
                "---\n\n"
                "## Acceptance verdict\n\n"
                "accepted-with-open-items — criteria met; one open item.\n",
            )
            verdict, closure, items = parse_retro_contract(retro)
            self.assertEqual(verdict, "accepted-with-open-items")
            self.assertEqual(closure, "recommended")
            self.assertIn(verdict, ACCEPT_VERDICTS)
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].id, "R1")
            self.assertEqual(items[0].disposition, "fix-now")
            detail = extract_acceptance_detail(retro)
            self.assertIn("accepted-with-open-items", detail)

    def test_rejected_derives_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            retro = _write(
                Path(tmp) / "r.md",
                "---\nverdict: rejected\ncriteria: profiled\n---\n\n"
                "## Acceptance verdict\n\nrejected — pending tickets.\n",
            )
            verdict, closure, items = parse_retro_contract(retro)
            self.assertEqual(verdict, "rejected")
            self.assertEqual(closure, "refused")
            self.assertEqual(items, [])

    def test_quoted_summary_with_colon_parses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            retro = _write(
                Path(tmp) / "r.md",
                "---\n"
                "verdict: accepted-with-open-items\n"
                "closure: recommended\n"
                "action_items:\n"
                "  - id: R1\n"
                "    kind: remediation\n"
                "    disposition: defer\n"
                '    title: "Filter noise"\n'
                "    owner: ingest\n"
                '    summary: "No min-length. Source: live db; apps/ingest/app/chunk/split.py"\n'
                "---\n\n"
                "## Acceptance verdict\n\naccepted-with-open-items.\n",
            )
            verdict, closure, items = parse_retro_contract(retro)
            self.assertEqual(verdict, "accepted-with-open-items")
            self.assertEqual(closure, "recommended")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].id, "R1")
            self.assertIn("Source: live db", items[0].summary)

    def test_unquoted_summary_with_colon_raises_factory_halt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            retro = _write(
                Path(tmp) / "r.md",
                "---\n"
                "verdict: accepted\n"
                "action_items:\n"
                "  - id: R1\n"
                "    kind: remediation\n"
                "    disposition: defer\n"
                "    title: Filter noise\n"
                "    summary: No min-length. Source: live db; apps/ingest/app/chunk/split.py\n"
                "---\n\n"
                "## Acceptance verdict\n\naccepted.\n",
            )
            with self.assertRaises(FactoryHalt) as ctx:
                parse_retro_contract(retro)
            self.assertIn("invalid YAML frontmatter", str(ctx.exception))
            self.assertIn(str(retro), str(ctx.exception))


class CloseEpicTests(unittest.TestCase):
    def test_sets_status_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epic_md, _ = _epic_tree(root)
            with mock.patch(
                "bmad_factory.epic_closure._load_store_config",
                return_value={"tickets": {"store": "repo"}},
            ):
                close_epic_container(root, epic_md)
            fm = read_frontmatter(epic_md)
            self.assertEqual(fm.get("status"), "done")
            self.assertEqual(fm.get("tracker_status"), "done")

    def test_preserves_inline_lists_for_tickets_py(self) -> None:
        """Close must not rewrite covers/after into block lists tickets.py rejects."""
        tickets_scripts = (
            Path(__file__).resolve().parents[2] / "_bmad" / "method" / "scripts"
        )
        if str(tickets_scripts) not in sys.path:
            sys.path.insert(0, str(tickets_scripts))
        from tickets import parse_frontmatter  # type: ignore[import-not-found]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epic_md, _ = _epic_tree(root)
            with mock.patch(
                "bmad_factory.epic_closure._load_store_config",
                return_value={"tickets": {"store": "repo"}},
            ):
                close_epic_container(root, epic_md)
            text = epic_md.read_text(encoding="utf-8")
            block = _frontmatter_block(text)
            self.assertFalse(
                _has_block_list_line(block),
                f"block-style list lines after close:\n{block}",
            )
            self.assertIn("covers: [R4]", block)
            self.assertIn("after: [epic-other]", block)
            fm = parse_frontmatter(text)
            self.assertEqual(fm.get("status"), "done")
            self.assertEqual(fm.get("covers"), ["R4"])
            self.assertEqual(fm.get("after"), ["epic-other"])

    def test_github_store_closes_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epic_md, _ = _epic_tree(root)
            with (
                mock.patch(
                    "bmad_factory.epic_closure._load_store_config",
                    return_value={"tickets": {"store": "github", "repo": "org/repo"}},
                ),
                mock.patch("bmad_factory.epic_closure._github_mark_done") as gh,
            ):
                close_epic_container(root, epic_md)
            gh.assert_called_once()
            fm = read_frontmatter(epic_md)
            self.assertEqual(fm.get("status"), "done")
            self.assertEqual(fm.get("tracker_status"), "done")


class MaterializeTests(unittest.TestCase):
    def test_creates_fix_now_skips_accept_as_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epic_md, epic_dir = _epic_tree(root)
            retro = _write(
                epic_dir / "epic-demo-retrospective.md",
                "---\nverdict: accepted\nclosure: recommended\n---\n",
            )
            items = [
                ActionItem(
                    id="R1",
                    kind="remediation",
                    disposition="fix-now",
                    title="Encode passwords",
                    summary="Percent-encode @ in DATABASE_URL.",
                ),
                ActionItem(
                    id="R2",
                    kind="process",
                    disposition="accept-as-is",
                    title="Keep gate short-circuit",
                    summary="Intentional.",
                ),
                ActionItem(
                    id="R3",
                    kind="spec-reconciliation",
                    disposition="defer",
                    title="Align Done when wording",
                    summary="Story 2.1 diverged.",
                ),
            ]
            created, skipped, errors = materialize_action_items(
                root,
                epic_slug="epic-demo",
                retro_md=retro,
                action_items=items,
            )
            self.assertEqual(errors, [])
            self.assertEqual(skipped, ["R2"])
            self.assertEqual(len(created), 2)
            backlog = root / "_bmad-output" / "backlog"
            texts = [p.read_text(encoding="utf-8") for p in backlog.glob("bug-*.md")]
            joined = "\n".join(texts)
            self.assertIn(retro_marker("epic-demo", "R1"), joined)
            self.assertIn(retro_marker("epic-demo", "R3"), joined)
            self.assertIn("refine: true", joined)
            for text in texts:
                block = _frontmatter_block(text)
                self.assertNotIn(
                    "\n...\n",
                    f"\n{block}\n",
                    f"yaml document-end litter in frontmatter:\n{block}",
                )
                self.assertTrue(
                    any(line.startswith("title: ") for line in block.splitlines())
                )
                title_line = next(
                    line for line in block.splitlines() if line.startswith("title: ")
                )
                self.assertTrue(
                    title_line.startswith('title: "'),
                    f"title should be JSON-quoted, got: {title_line!r}",
                )

            created2, skipped2, errors2 = materialize_action_items(
                root,
                epic_slug="epic-demo",
                retro_md=retro,
                action_items=items,
            )
            self.assertEqual(errors2, [])
            self.assertEqual(created2, [])
            self.assertEqual(set(skipped2), {"R1", "R2", "R3"})
            self.assertEqual(len(list(backlog.glob("bug-*.md"))), 2)
            del epic_md


class ProcessEpicClosureTests(unittest.TestCase):
    def test_rejected_after_agent_does_not_close_or_materialize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epic_md, epic_dir = _epic_tree(root)
            (root / "_bmad").mkdir()
            run_state = create_run(root, mode="epic", epic="epic-demo", model="auto")
            report = RunReport()

            def _fake_agent(**_kwargs):
                _write(
                    epic_dir / "epic-demo-retrospective.md",
                    "---\n"
                    "epic: epic-demo\n"
                    "verdict: rejected\n"
                    "closure: refused\n"
                    "action_items:\n"
                    "  - id: R1\n"
                    "    kind: remediation\n"
                    "    disposition: fix-now\n"
                    "    title: Should not create\n"
                    "    summary: No.\n"
                    "---\n\n"
                    "## Acceptance verdict\n\n"
                    "rejected — unfinished work remains.\n",
                )
                return mock.Mock(
                    status="finished",
                    error=None,
                    usage=None,
                    agent_id="a1",
                    run_id="r1",
                )

            with mock.patch(
                "bmad_factory.epic_closure.run_cursor_agent",
                side_effect=_fake_agent,
            ):
                result = process_epic_closure(
                    project_root=root,
                    epic_slug="epic-demo",
                    report=report,
                    policy=mock.Mock(limits=None),
                    run_state=run_state,
                    model="auto",
                )
            self.assertFalse(result.closed)
            self.assertEqual(result.verdict, "rejected")
            self.assertIn("cannot close", result.detail)
            self.assertIn("rejected", result.detail)
            self.assertNotEqual(read_frontmatter(epic_md).get("status"), "done")
            self.assertEqual(
                list((root / "_bmad-output" / "backlog").glob("bug-*.md")), []
            )

    def test_accepted_closes_and_materializes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            epic_md, epic_dir = _epic_tree(root)
            (root / "_bmad").mkdir()
            run_state = create_run(root, mode="epic", epic="epic-demo", model="auto")
            report = RunReport()

            def _fake_agent(**_kwargs):
                _write(
                    epic_dir / "epic-demo-retrospective.md",
                    "---\n"
                    "epic: epic-demo\n"
                    "verdict: accepted\n"
                    "closure: recommended\n"
                    "action_items:\n"
                    "  - id: R9\n"
                    "    kind: remediation\n"
                    "    disposition: fix-now\n"
                    "    title: Retro remedia\n"
                    "    summary: Do it.\n"
                    "---\n\n"
                    "## Acceptance verdict\n\n"
                    "accepted — all Done when met.\n",
                )
                return mock.Mock(
                    status="finished",
                    error=None,
                    usage=None,
                    agent_id="a1",
                    run_id="r1",
                )

            with (
                mock.patch(
                    "bmad_factory.epic_closure.run_cursor_agent",
                    side_effect=_fake_agent,
                ),
                mock.patch(
                    "bmad_factory.epic_closure._load_store_config",
                    return_value={"tickets": {"store": "repo"}},
                ),
            ):
                result = process_epic_closure(
                    project_root=root,
                    epic_slug="epic-demo",
                    report=report,
                    policy=mock.Mock(limits=None),
                    run_state=run_state,
                    model="auto",
                )
            self.assertTrue(result.closed)
            self.assertEqual(result.verdict, "accepted")
            self.assertEqual(read_frontmatter(epic_md).get("status"), "done")
            self.assertEqual(len(result.created_tickets), 1)
            self.assertTrue(
                any(
                    retro_marker("epic-demo", "R9") in p.read_text(encoding="utf-8")
                    for p in (root / "_bmad-output" / "backlog").glob("bug-*.md")
                )
            )


class CliEpicBoundaryTests(unittest.TestCase):
    def test_accept_continues_without_pause(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_bmad").mkdir()
            run_state = create_run(root, mode="epic", epic="epic-demo", model="auto")
            report = RunReport()
            halt = Halt(
                HALT_AWAITING_CLOSURE,
                "epic-demo",
                None,
                "every ticket of epic-demo is done; close epic-demo",
            )
            calls = {"n": 0}

            def _decide(*_a, **_k):
                calls["n"] += 1
                if calls["n"] == 1:
                    return halt
                return Skip("empty")

            with (
                mock.patch(
                    "bmad_factory.cli._views_for_mode", return_value=(None, None)
                ),
                mock.patch("bmad_factory.cli.decide_pick", side_effect=_decide),
                mock.patch(
                    "bmad_factory.cli.process_epic_closure",
                    return_value=EpicClosureResult(
                        closed=True,
                        verdict="accepted",
                        closure="recommended",
                        detail="closed epic-demo",
                    ),
                ),
            ):
                _execute_pick_loop(
                    project_root=root,
                    report=report,
                    policy=mock.Mock(),
                    run_state=run_state,
                    model="auto",
                    dry_run=False,
                    no_push=True,
                    ticket=None,
                    epic="epic-demo",
                    backlog=False,
                    cli_label="--epic epic-demo",
                )
            self.assertEqual(run_state.status, "completed")
            self.assertEqual(
                run_state.ticket_epic_closures.get("epic-demo"), "accepted"
            )
            self.assertIn("epic-demo", run_state.ticket_epic_closure_acked)

    def test_reject_pauses_with_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_bmad").mkdir()
            run_state = create_run(root, mode="epic", epic="epic-demo", model="auto")
            report = RunReport()
            halt = Halt(
                HALT_AWAITING_CLOSURE,
                "epic-demo",
                None,
                "every ticket of epic-demo is done; close epic-demo",
            )
            detail = (
                "cannot close epic-demo: retrospective refused closure\n"
                "verdict='rejected' closure='refused'\n"
                "Acceptance verdict:\nrejected — unfinished."
            )
            with (
                mock.patch(
                    "bmad_factory.cli._views_for_mode", return_value=(None, None)
                ),
                mock.patch("bmad_factory.cli.decide_pick", return_value=halt),
                mock.patch(
                    "bmad_factory.cli.process_epic_closure",
                    return_value=EpicClosureResult(
                        closed=False,
                        verdict="rejected",
                        closure="refused",
                        detail=detail,
                    ),
                ),
                self.assertRaises(FactoryHalt) as ctx,
            ):
                _execute_pick_loop(
                    project_root=root,
                    report=report,
                    policy=mock.Mock(),
                    run_state=run_state,
                    model="auto",
                    dry_run=False,
                    no_push=True,
                    ticket=None,
                    epic="epic-demo",
                    backlog=False,
                    cli_label="--epic epic-demo",
                )
            self.assertEqual(ctx.exception.shutdown, HALT_EPIC_REJECTED)
            self.assertIn("Acceptance verdict", ctx.exception.detail or "")
            self.assertEqual(
                run_state.ticket_epic_closures.get("epic-demo"), CLOSURE_REJECTED
            )
            self.assertEqual(run_state.status, "paused")


if __name__ == "__main__":
    unittest.main()
