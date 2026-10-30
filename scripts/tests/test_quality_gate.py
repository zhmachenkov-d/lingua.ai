"""Unit tests for quality_gate verdict policy and metrics ingest (no live binaries)."""

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

from quality.ingest_report import append_metrics, build_metrics_record  # noqa: E402
from quality_gate import (  # noqa: E402
    EXIT_FAIL,
    EXIT_MISSING_TOOLS,
    EXIT_OK,
    _count_ast_grep_findings,
    build_summary,
    run_gate,
)


def _layer(
    name: str,
    *,
    hard: bool,
    status: str,
    exit_code: int = 0,
    finding_count: int = 0,
    error_count: int = 0,
    warning_count: int = 0,
) -> dict:
    return {
        "name": name,
        "hard": hard,
        "status": status,
        "exit_code": exit_code,
        "finding_count": finding_count,
        "error_count": error_count,
        "warning_count": warning_count,
        "report": f"{name}.json",
    }


class CountAstGrepTests(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(_count_ast_grep_findings(""), (0, 0, 0))

    def test_list_with_severities(self) -> None:
        payload = json.dumps(
            [
                {"severity": "error", "message": "bad"},
                {"severity": "warning", "message": "meh"},
                {"severity": "hint", "message": "info"},
            ]
        )
        self.assertEqual(_count_ast_grep_findings(payload), (3, 1, 1))


class SummaryVerdictTests(unittest.TestCase):
    def test_pass_when_only_soft_layers_fail(self) -> None:
        summary = build_summary(
            [
                _layer("ast-grep", hard=True, status="pass"),
                _layer("ast-metrics", hard=False, status="soft_fail", exit_code=1),
                _layer("revet", hard=False, status="soft_fail", exit_code=1),
            ],
            base="origin/main",
            sha="abc",
            out_dir=Path("/tmp/q"),
        )
        self.assertEqual(summary["verdict"], "pass")
        self.assertEqual(summary["failed_layers"], [])

    def test_fail_when_hard_ast_grep_fails(self) -> None:
        summary = build_summary(
            [
                _layer(
                    "ast-grep",
                    hard=True,
                    status="fail",
                    exit_code=1,
                    error_count=2,
                    finding_count=2,
                ),
                _layer("ast-metrics", hard=False, status="pass"),
                _layer("revet", hard=False, status="pass"),
            ],
            base="origin/main",
            sha="abc",
            out_dir=Path("/tmp/q"),
        )
        self.assertEqual(summary["verdict"], "fail")
        self.assertEqual(summary["failed_layers"], ["ast-grep"])

    def test_strict_metrics_can_fail_verdict(self) -> None:
        summary = build_summary(
            [
                _layer("ast-grep", hard=True, status="pass"),
                _layer("ast-metrics", hard=True, status="fail", exit_code=1),
                _layer("revet", hard=False, status="pass"),
            ],
            base="origin/main",
            sha="abc",
            out_dir=Path("/tmp/q"),
        )
        self.assertEqual(summary["verdict"], "fail")
        self.assertEqual(summary["failed_layers"], ["ast-metrics"])


class IngestReportTests(unittest.TestCase):
    def test_build_metrics_record_shape(self) -> None:
        summary = {
            "ts": "2026-01-01T00:00:00Z",
            "sha": "deadbeef",
            "base": "origin/main",
            "verdict": "pass",
            "failed_layers": [],
            "layers": {
                "ast-grep": _layer("ast-grep", hard=True, status="pass"),
                "ast-metrics": _layer("ast-metrics", hard=False, status="pass"),
                "revet": _layer("revet", hard=False, status="pass"),
            },
        }
        record = build_metrics_record(
            summary, ticket="story-1.md", agent_run_id="run-9", pr="42"
        )
        self.assertEqual(record["ticket"], "story-1.md")
        self.assertEqual(record["agent_run_id"], "run-9")
        self.assertEqual(record["pr"], "42")
        self.assertEqual(record["verdict"], "pass")
        self.assertEqual(record["antipattern"]["status"], "pass")
        self.assertEqual(record["complexity"]["status"], "pass")
        self.assertEqual(record["impact"]["status"], "pass")

    def test_append_metrics_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = root / "metrics.jsonl"
            summary = {
                "ts": "2026-01-01T00:00:00Z",
                "sha": "abc",
                "base": "origin/main",
                "verdict": "fail",
                "failed_layers": ["ast-grep"],
                "layers": {
                    "ast-grep": _layer(
                        "ast-grep", hard=True, status="fail", error_count=1
                    ),
                },
            }
            path = append_metrics(
                summary, metrics_path=metrics, project_root=root, ticket="t-1"
            )
            self.assertEqual(path, metrics)
            lines = metrics.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["ticket"], "t-1")
            self.assertEqual(row["verdict"], "fail")
            self.assertEqual(row["failed_layers"], ["ast-grep"])


class RunGateMissingToolsTests(unittest.TestCase):
    def test_missing_binaries_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch("quality_gate._require_binaries", return_value=["ast-grep"]):
                summary, code = run_gate(
                    project_root=root,
                    base="origin/main",
                    out_dir=root / "out",
                    skip_ingest=True,
                )
            self.assertEqual(code, EXIT_MISSING_TOOLS)
            self.assertEqual(summary["verdict"], "error")


class RunGateMockedLayersTests(unittest.TestCase):
    def test_hard_fail_exit_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            with (
                mock.patch("quality_gate._require_binaries", return_value=[]),
                mock.patch(
                    "quality_gate.run_ast_grep",
                    return_value=_layer(
                        "ast-grep", hard=True, status="fail", exit_code=1
                    ),
                ),
                mock.patch(
                    "quality_gate.run_ast_metrics",
                    return_value=_layer("ast-metrics", hard=False, status="pass"),
                ),
                mock.patch(
                    "quality_gate.run_revet",
                    return_value=_layer("revet", hard=False, status="pass"),
                ),
            ):
                summary, code = run_gate(
                    project_root=root,
                    base="origin/main",
                    out_dir=out,
                    skip_ingest=True,
                )
            self.assertEqual(code, EXIT_FAIL)
            self.assertEqual(summary["verdict"], "fail")
            self.assertTrue((out / "summary.json").is_file())

    def test_all_soft_pass_exit_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            with (
                mock.patch("quality_gate._require_binaries", return_value=[]),
                mock.patch(
                    "quality_gate.run_ast_grep",
                    return_value=_layer("ast-grep", hard=True, status="pass"),
                ),
                mock.patch(
                    "quality_gate.run_ast_metrics",
                    return_value=_layer(
                        "ast-metrics", hard=False, status="soft_fail", exit_code=1
                    ),
                ),
                mock.patch(
                    "quality_gate.run_revet",
                    return_value=_layer("revet", hard=False, status="pass"),
                ),
            ):
                summary, code = run_gate(
                    project_root=root,
                    base="origin/main",
                    out_dir=out,
                    skip_ingest=True,
                )
            self.assertEqual(code, EXIT_OK)
            self.assertEqual(summary["verdict"], "pass")


if __name__ == "__main__":
    unittest.main()
