#!/usr/bin/env python3
"""Diff-scoped assertion guard for worker-generated / PR-changed tests.

Scans test files changed vs a git base and fails when a test function has no
real assertion sites, or only vacuous ones (``assert True``, empty bodies,
``expect(true).toBe(true)``).

Stdlib-only. Python uses AST; TypeScript/JavaScript specs use lightweight
heuristics (expect / toHaveBeenCalled* / fc.assert).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_FAIL = 1

# Mock / unittest assertion helpers that count as real checks.
_PY_MOCK_ASSERT_PREFIXES = (
    "assert_called",
    "assert_not_called",
    "assert_any_call",
    "assert_has_calls",
)
_PY_UNITTEST_ASSERT_PREFIX = "assert"
_PY_PYTEST_CONTEXT = frozenset({"raises", "warns", "deprecated_call"})

_TS_IT_START = re.compile(
    r"(?:^|\s)(?:it|test|it\.only|test\.only|it\.skip|test\.skip)\s*\(",
    re.MULTILINE,
)
_TS_EXPECT = re.compile(r"\bexpect\s*\(")
_TS_MOCK_ASSERT = re.compile(r"\btoHaveBeenCalled(?:Once|Times|With|OnceWith)?\b")
_TS_FC_ASSERT = re.compile(r"\bfc\.assert\s*\(")
_TS_VACUOUS_EXPECT = re.compile(
    r"expect\s*\(\s*true\s*\)\s*\.\s*toBe(?:Truthy)?\s*\(\s*true\s*\)"
    r"|expect\s*\(\s*true\s*\)\s*\.\s*toBeTruthy\s*\(\s*\)",
    re.IGNORECASE,
)


@dataclass
class Finding:
    path: str
    name: str
    line: int
    reason: str


@dataclass
class GuardReport:
    base: str
    scanned_files: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    finding_count: int = 0
    status: str = "pass"

    def finalize(self) -> None:
        self.finding_count = len(self.findings)
        self.status = "fail" if self.findings else "pass"


def is_test_path(rel_path: str) -> bool:
    """Return True if path looks like a Python or TS/JS test file."""
    p = rel_path.replace("\\", "/")
    name = Path(p).name
    if p.endswith(".py"):
        if "/tests/" in f"/{p}" or p.startswith("tests/"):
            return True
        return name.endswith("_test.py") or name.startswith("test_")
    if p.endswith((".ts", ".tsx", ".js", ".jsx")):
        return (
            name.endswith(".spec.ts")
            or name.endswith(".spec.tsx")
            or name.endswith(".test.ts")
            or name.endswith(".test.tsx")
            or name.endswith(".spec.js")
            or name.endswith(".test.js")
        )
    return False


def list_changed_paths(project_root: Path, base: str) -> list[str]:
    """Paths changed vs base (tracked + untracked), relative to project_root."""
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    paths: set[str] = set()
    if tracked.returncode == 0:
        for line in tracked.stdout.splitlines():
            line = line.strip()
            if line:
                paths.add(line.replace("\\", "/"))
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if untracked.returncode == 0:
        for line in untracked.stdout.splitlines():
            line = line.strip()
            if line:
                paths.add(line.replace("\\", "/"))
    return sorted(paths)


def _is_vacuous_assert_test(node: ast.AST) -> bool:
    """True for always-passing asserts: ``assert True``, ``assert 1``, ``assert 'x'``."""
    if isinstance(node, ast.Constant):
        return node.value is True or (
            isinstance(node.value, (int, float, str, bytes)) and bool(node.value)
        )
    if isinstance(node, ast.Name) and node.id == "True":
        return True
    return False


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        cur: ast.AST = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
        return parts[0] if parts else None
    return None


def _attr_is_mock_or_unittest_assert(attr: str) -> bool:
    if any(attr == p or attr.startswith(f"{p}_") for p in _PY_MOCK_ASSERT_PREFIXES):
        return True
    if attr.startswith("assert_called") or attr.startswith("assert_not_called"):
        return True
    # unittest: assertEqual, assertRaises, assertIn, ...
    if attr.startswith(_PY_UNITTEST_ASSERT_PREFIX) and not attr.startswith("assert_"):
        return len(attr) > len(_PY_UNITTEST_ASSERT_PREFIX)
    return False


def _is_real_py_assertion(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return not _is_vacuous_assert_test(node.test)

    if isinstance(node, ast.With):
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Call):
                name = _call_name(ctx.func)
                if name is None:
                    continue
                tail = name.rsplit(".", 1)[-1]
                if tail in _PY_PYTEST_CONTEXT:
                    return True
        return False

    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        name = _call_name(node.value.func)
        if name is None:
            return False
        attr = name.rsplit(".", 1)[-1]
        return _attr_is_mock_or_unittest_assert(attr)
    return False


def _stmt_is_noop(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr):
        if isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
            return True
        if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            return True  # docstring-only body piece
    return False


def _body_has_real_work(body: list[ast.stmt]) -> bool:
    """Skip leading docstring; require at least one non-noop statement or assertion."""
    stmts = list(body)
    if (
        stmts
        and isinstance(stmts[0], ast.Expr)
        and isinstance(stmts[0].value, ast.Constant)
        and isinstance(stmts[0].value.value, str)
    ):
        stmts = stmts[1:]
    return any(not _stmt_is_noop(s) for s in stmts)


class _PyTestVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self._class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def _is_test_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        if node.name.startswith("test"):
            return True
        if self._class_stack and self._class_stack[-1].startswith("Test"):
            if node.name.startswith("test"):
                return True
        return False

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not self._is_test_function(node):
            return
        qual = ".".join([*self._class_stack, node.name])
        line = node.lineno

        if not _body_has_real_work(node.body):
            self.findings.append(
                Finding(self.path, qual, line, "empty test body")
            )
            return

        real = 0
        vacuous_only = 0
        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                if _is_vacuous_assert_test(child.test):
                    vacuous_only += 1
                else:
                    real += 1
            elif _is_real_py_assertion(child):
                # Avoid double-counting Assert already handled above
                if not isinstance(child, ast.Assert):
                    real += 1

        if real == 0:
            reason = (
                "only vacuous assertions"
                if vacuous_only > 0
                else "no assertion sites"
            )
            self.findings.append(Finding(self.path, qual, line, reason))


def scan_python_source(path: str, source: str) -> list[Finding]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [
            Finding(
                path,
                "<module>",
                exc.lineno or 1,
                f"syntax error: {exc.msg}",
            )
        ]
    visitor = _PyTestVisitor(path)
    visitor.visit(tree)
    return visitor.findings


def _extract_balanced_call_body(source: str, open_paren_idx: int) -> str | None:
    """Return text inside the outermost (...) starting at open_paren_idx, or None."""
    if open_paren_idx < 0 or open_paren_idx >= len(source) or source[open_paren_idx] != "(":
        return None
    depth = 0
    in_str: str | None = None
    escape = False
    for i in range(open_paren_idx, len(source)):
        ch = source[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in {'"', "'", "`"}:
            in_str = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return source[open_paren_idx + 1 : i]
    return None


def _ts_callback_body(call_inside: str) -> str | None:
    """Extract arrow/function callback body from it('name', () => { ... }).

    Uses the first top-level ``=>`` / ``function`` so nested arrows inside
    ``fc.property(..., (x) => ...)`` are not mistaken for the test callback.
    """
    depth = 0
    in_str: str | None = None
    escape = False
    i = 0
    start = -1
    while i < len(call_inside):
        ch = call_inside[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in {'"', "'", "`"}:
            in_str = ch
            i += 1
            continue
        if ch in "([{":
            depth += 1
            i += 1
            continue
        if ch in ")]}":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth == 0:
            if call_inside.startswith("=>", i):
                start = i
                break
            if call_inside.startswith("function", i) and (
                i + 8 >= len(call_inside) or not (call_inside[i + 8].isalnum() or call_inside[i + 8] == "_")
            ):
                start = i
                break
        i += 1
    if start < 0:
        return None
    brace = call_inside.find("{", start)
    if brace < 0:
        if call_inside.startswith("=>", start):
            return call_inside[start + 2 :].strip()
        return None
    depth = 0
    in_str = None
    escape = False
    for j in range(brace, len(call_inside)):
        ch = call_inside[j]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in {'"', "'", "`"}:
            in_str = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return call_inside[brace + 1 : j]
    return None


def _line_at(source: str, index: int) -> int:
    return source.count("\n", 0, index) + 1


def scan_ts_source(path: str, source: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in _TS_IT_START.finditer(source):
        # Find '(' of it(
        paren = source.find("(", match.start())
        if paren < 0:
            continue
        inside = _extract_balanced_call_body(source, paren)
        if inside is None:
            continue
        # First string-ish arg as name (best-effort)
        name_m = re.match(r"\s*['\"`]([^'\"`]*)['\"`]", inside)
        name = name_m.group(1) if name_m else "<anonymous>"
        line = _line_at(source, match.start())
        body = _ts_callback_body(inside)
        if body is None or not body.strip():
            findings.append(Finding(path, name, line, "empty test body"))
            continue
        vacuous = list(_TS_VACUOUS_EXPECT.finditer(body))
        # Strip vacuous expects when counting real ones
        scrubbed = _TS_VACUOUS_EXPECT.sub("", body)
        real = (
            len(_TS_EXPECT.findall(scrubbed))
            + len(_TS_MOCK_ASSERT.findall(scrubbed))
            + len(_TS_FC_ASSERT.findall(scrubbed))
        )
        if real == 0:
            reason = (
                "only vacuous assertions" if vacuous else "no assertion sites"
            )
            findings.append(Finding(path, name, line, reason))
    return findings


def scan_file(project_root: Path, rel_path: str) -> list[Finding]:
    full = project_root / rel_path
    if not full.is_file():
        return []
    try:
        source = full.read_text(encoding="utf-8")
    except OSError as exc:
        return [Finding(rel_path, "<file>", 1, f"unreadable: {exc}")]
    if rel_path.endswith(".py"):
        return scan_python_source(rel_path, source)
    if rel_path.endswith((".ts", ".tsx", ".js", ".jsx")):
        return scan_ts_source(rel_path, source)
    return []


def run_guard(
    *,
    project_root: Path,
    base: str,
    out_path: Path | None = None,
) -> GuardReport:
    report = GuardReport(base=base)
    changed = [p for p in list_changed_paths(project_root, base) if is_test_path(p)]
    report.scanned_files = changed
    for rel in changed:
        report.findings.extend(scan_file(project_root, rel))
    report.finalize()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "base": report.base,
            "scanned_files": report.scanned_files,
            "finding_count": report.finding_count,
            "status": report.status,
            "findings": [asdict(f) for f in report.findings],
        }
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Git ref to diff against (default: origin/main)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Repository root (default: cwd)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON report to this path",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = (args.project_root or Path.cwd()).resolve()
    out = args.out
    if out is None:
        out = project_root / "_bmad-output" / "quality" / "assertion-guard.json"
    report = run_guard(project_root=project_root, base=args.base, out_path=out)
    print(
        json.dumps(
            {
                "status": report.status,
                "finding_count": report.finding_count,
                "scanned_files": len(report.scanned_files),
                "out": str(out),
            }
        )
    )
    if report.findings:
        for f in report.findings:
            print(f"{f.path}:{f.line}: {f.name}: {f.reason}", file=sys.stderr)
    return EXIT_FAIL if report.status == "fail" else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
