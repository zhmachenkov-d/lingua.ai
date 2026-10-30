"""Unit tests for mutation soft-gate report normalization."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from quality.mutation_report import (
    build_summary,
    load_baseline,
    main,
    parse_mutmut_stats,
    parse_stryker_report,
)


class ParseMutmutTests(unittest.TestCase):
    def test_counts(self) -> None:
        counts = parse_mutmut_stats(
            {"killed": 10, "survived": 2, "timeout": 1, "total": 13}
        )
        self.assertEqual(counts["killed"], 10)
        self.assertEqual(counts["survived"], 2)
        self.assertEqual(counts["timeout"], 1)


class ParseStrykerTests(unittest.TestCase):
    def test_aggregates_statuses(self) -> None:
        payload = {
            "files": {
                "a.ts": {
                    "mutants": [
                        {"status": "Killed"},
                        {"status": "Survived"},
                        {"status": "Timeout"},
                        {"status": "CompileError"},
                        {"status": "NoCoverage"},
                    ]
                }
            }
        }
        counts = parse_stryker_report(payload)
        self.assertEqual(counts["killed"], 1)
        self.assertEqual(counts["survived"], 1)
        self.assertEqual(counts["timeout"], 1)
        self.assertEqual(counts["suspicious"], 1)
        self.assertEqual(counts["no_tests"], 1)


class SoftPolicyTests(unittest.TestCase):
    def test_pass_when_above_baseline(self) -> None:
        summary = build_summary(
            stack="api",
            counts={"killed": 8, "survived": 2, "timeout": 0, "total": 10},
            baseline={"min_score": 50, "max_survived": None},
        )
        self.assertEqual(summary["score"], 80.0)
        self.assertEqual(summary["status"], "pass")
        self.assertFalse(summary["hard"])

    def test_soft_fail_on_low_score(self) -> None:
        summary = build_summary(
            stack="web",
            counts={"killed": 1, "survived": 9, "timeout": 0, "total": 10},
            baseline={"min_score": 50, "max_survived": None},
        )
        self.assertEqual(summary["status"], "soft_fail")

    def test_soft_fail_on_max_survived(self) -> None:
        summary = build_summary(
            stack="api",
            counts={"killed": 9, "survived": 5, "timeout": 0, "total": 14},
            baseline={"min_score": 0, "max_survived": 3},
        )
        self.assertEqual(summary["status"], "soft_fail")

    def test_error_on_parse_failure(self) -> None:
        summary = build_summary(
            stack="api",
            counts={},
            baseline={"min_score": 0, "max_survived": None},
            parse_error="boom",
        )
        self.assertEqual(summary["status"], "error")

    def test_empty_run_passes_even_with_min_score(self) -> None:
        summary = build_summary(
            stack="api",
            counts={"killed": 0, "survived": 0, "timeout": 0, "total": 0},
            baseline={"min_score": 80, "max_survived": None},
        )
        self.assertEqual(summary["status"], "pass")


class CliTests(unittest.TestCase):
    def test_writes_summary_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp = root / "mutmut-cicd-stats.json"
            inp.write_text(
                json.dumps({"killed": 3, "survived": 1, "timeout": 0, "total": 4}),
                encoding="utf-8",
            )
            baseline = root / "baseline.json"
            baseline.write_text(
                json.dumps({"min_score": 0, "max_survived": None}),
                encoding="utf-8",
            )
            out = root / "out" / "api.json"
            code = main(
                [
                    "--stack",
                    "api",
                    "--input",
                    str(inp),
                    "--baseline",
                    str(baseline),
                    "--out",
                    str(out),
                    "--project-root",
                    str(root),
                ]
            )
            self.assertEqual(code, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["stack"], "api")
            self.assertEqual(payload["killed"], 3)
            self.assertEqual(payload["status"], "pass")

    def test_load_baseline_defaults(self) -> None:
        self.assertEqual(load_baseline(None)["min_score"], 0)


if __name__ == "__main__":
    unittest.main()
