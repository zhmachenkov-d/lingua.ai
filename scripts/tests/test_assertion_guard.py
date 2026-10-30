"""Unit tests for scripts/assertion_guard.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import assertion_guard as ag  # noqa: E402


class IsTestPathTests(unittest.TestCase):
    def test_python_tests_dir(self) -> None:
        self.assertTrue(ag.is_test_path("apps/api/tests/test_health.py"))
        self.assertTrue(ag.is_test_path("scripts/tests/test_foo.py"))

    def test_python_suffix_forms(self) -> None:
        self.assertTrue(ag.is_test_path("pkg/foo_test.py"))
        self.assertTrue(ag.is_test_path("pkg/test_foo.py"))
        self.assertFalse(ag.is_test_path("apps/api/app/main.py"))

    def test_ts_spec_and_test(self) -> None:
        self.assertTrue(ag.is_test_path("apps/web/src/app/chat/cta-labels.spec.ts"))
        self.assertTrue(ag.is_test_path("apps/web/src/x.test.ts"))
        self.assertFalse(ag.is_test_path("apps/web/src/app/chat/cta-labels.ts"))


class ScanPythonTests(unittest.TestCase):
    def test_real_assert_ok(self) -> None:
        src = "def test_ok():\n    assert 1 + 1 == 2\n"
        self.assertEqual(ag.scan_python_source("t.py", src), [])

    def test_assert_true_fails(self) -> None:
        src = "def test_vacuous():\n    assert True\n"
        findings = ag.scan_python_source("t.py", src)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].reason, "only vacuous assertions")

    def test_empty_body_fails(self) -> None:
        src = "def test_empty():\n    pass\n"
        findings = ag.scan_python_source("t.py", src)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].reason, "empty test body")

    def test_no_assert_fails(self) -> None:
        src = "def test_noop():\n    x = 1 + 1\n"
        findings = ag.scan_python_source("t.py", src)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].reason, "no assertion sites")

    def test_pytest_raises_counts(self) -> None:
        src = (
            "import pytest\n"
            "def test_raises():\n"
            "    with pytest.raises(ValueError):\n"
            "        raise ValueError('x')\n"
        )
        self.assertEqual(ag.scan_python_source("t.py", src), [])

    def test_mock_assert_called_counts(self) -> None:
        src = (
            "def test_mock(m):\n"
            "    m()\n"
            "    m.assert_called_once()\n"
        )
        self.assertEqual(ag.scan_python_source("t.py", src), [])

    def test_unittest_style_counts(self) -> None:
        src = (
            "import unittest\n"
            "class TestFoo(unittest.TestCase):\n"
            "    def test_eq(self):\n"
            "        self.assertEqual(1, 1)\n"
        )
        self.assertEqual(ag.scan_python_source("t.py", src), [])

    def test_non_test_function_ignored(self) -> None:
        src = "def helper():\n    pass\n"
        self.assertEqual(ag.scan_python_source("t.py", src), [])


class ScanTsTests(unittest.TestCase):
    def test_expect_ok(self) -> None:
        src = "it('maps ids', () => {\n  expect(mapCtaIds(['tutor'])).toEqual([]);\n});\n"
        self.assertEqual(ag.scan_ts_source("t.spec.ts", src), [])

    def test_empty_it_fails(self) -> None:
        src = "it('empty', () => {\n});\n"
        findings = ag.scan_ts_source("t.spec.ts", src)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].reason, "empty test body")

    def test_vacuous_expect_fails(self) -> None:
        src = "it('vacuous', () => {\n  expect(true).toBe(true);\n});\n"
        findings = ag.scan_ts_source("t.spec.ts", src)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].reason, "only vacuous assertions")

    def test_toHaveBeenCalled_counts(self) -> None:
        src = "it('mock', () => {\n  expect(fn).toHaveBeenCalled();\n});\n"
        self.assertEqual(ag.scan_ts_source("t.spec.ts", src), [])

    def test_fc_assert_counts(self) -> None:
        src = (
            "it('property', () => {\n"
            "  fc.assert(fc.property(fc.string(), (s) => s === s));\n"
            "});\n"
        )
        self.assertEqual(ag.scan_ts_source("t.spec.ts", src), [])


class RunGuardTests(unittest.TestCase):
    def test_run_guard_scans_untracked_test(self) -> None:
        # Use a temp git repo so we control changed files.
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "t@example.com"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "t"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            (root / "README").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "README"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "init"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            tests = root / "tests"
            tests.mkdir()
            bad = tests / "test_bad.py"
            bad.write_text("def test_bad():\n    assert True\n", encoding="utf-8")
            out = root / "out.json"
            report = ag.run_guard(project_root=root, base="HEAD", out_path=out)
            self.assertEqual(report.status, "fail")
            self.assertEqual(report.finding_count, 1)
            self.assertTrue(out.is_file())

            good = tests / "test_good.py"
            bad.unlink()
            good.write_text("def test_good():\n    assert 1 == 1\n", encoding="utf-8")
            report2 = ag.run_guard(project_root=root, base="HEAD", out_path=out)
            self.assertEqual(report2.status, "pass")
            self.assertEqual(report2.finding_count, 0)


if __name__ == "__main__":
    unittest.main()
