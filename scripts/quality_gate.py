#!/usr/bin/env python3
"""Run layered AST quality checks for CI and BMAD factory verify.

Hard layer (always gating): ast-grep antipatterns (severity error).
Soft layers (report-only unless --strict-*): AST Metrics, Revet.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from quality.ingest_report import append_metrics  # noqa: E402

REQUIRED_BINARIES = ("ast-grep", "ast-metrics", "revet")
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_MISSING_TOOLS = 2


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_sha(project_root: Path) -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _require_binaries() -> list[str]:
    missing = [name for name in REQUIRED_BINARIES if shutil.which(name) is None]
    return missing


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    out_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return proc


def _count_ast_grep_findings(stdout: str) -> tuple[int, int, int]:
    """Return (total, error, warning) from ast-grep JSON output."""
    text = stdout.strip()
    if not text:
        return 0, 0, 0
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # stream / NDJSON fallback
        findings = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                findings.append(json.loads(line))
            except json.JSONDecodeError:
                return 0, 0, 0
        data = findings
    if isinstance(data, dict):
        data = data.get("matches") or data.get("diagnostics") or data.get("findings") or []
    if not isinstance(data, list):
        return 0, 0, 0
    errors = 0
    warnings = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        sev = str(
            item.get("severity")
            or item.get("level")
            or (item.get("rule") or {}).get("severity")
            or ""
        ).lower()
        if sev in {"error", "err"}:
            errors += 1
        elif sev in {"warning", "warn"}:
            warnings += 1
    return len(data), errors, warnings


def _count_json_findings(stdout: str, *keys: str) -> int:
    text = stdout.strip()
    if not text:
        return 0
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return 0
    if isinstance(data, list):
        return len(data)
    if not isinstance(data, dict):
        return 0
    for key in keys:
        val = data.get(key)
        if isinstance(val, list):
            return len(val)
        if isinstance(val, dict) and "findings" in val and isinstance(val["findings"], list):
            return len(val["findings"])
    for fallback in ("findings", "regressions", "results", "issues"):
        val = data.get(fallback)
        if isinstance(val, list):
            return len(val)
    return 0


def run_ast_grep(project_root: Path, out_dir: Path) -> dict[str, Any]:
    raw_path = out_dir / "ast-grep.json"
    # Prefer JSON report; fall back if flag unsupported.
    proc = _run(
        ["ast-grep", "scan", "--json", "."],
        cwd=project_root,
        out_path=raw_path,
    )
    if proc.returncode == 2 and "unexpected argument" in (proc.stderr or "").lower():
        proc = _run(
            ["ast-grep", "scan", "-f", "json", "."],
            cwd=project_root,
            out_path=raw_path,
        )
    total, errors, warnings = _count_ast_grep_findings(proc.stdout)
    # ast-grep exits non-zero when error-severity matches exist.
    hard_fail = proc.returncode != 0 or errors > 0
    status = "fail" if hard_fail else "pass"
    return {
        "name": "ast-grep",
        "hard": True,
        "status": status,
        "exit_code": proc.returncode,
        "finding_count": total,
        "error_count": errors,
        "warning_count": warnings,
        "report": str(raw_path.relative_to(project_root))
        if raw_path.is_relative_to(project_root)
        else str(raw_path),
    }


def run_ast_metrics(
    project_root: Path,
    out_dir: Path,
    *,
    base: str,
    strict: bool,
) -> dict[str, Any]:
    report_json = out_dir / "ast-metrics-review.json"
    fail_on = "high" if strict else "never"
    cmd = [
        "ast-metrics",
        "review",
        f"--base={base}",
        f"--fail-on={fail_on}",
        f"--report-json={report_json}",
        ".",
    ]
    proc = _run(cmd, cwd=project_root, out_path=out_dir / "ast-metrics.meta.json")
    finding_count = 0
    if report_json.is_file():
        try:
            payload = json.loads(report_json.read_text(encoding="utf-8"))
            finding_count = _count_json_findings(
                json.dumps(payload), "regressions", "findings", "violations"
            )
        except (json.JSONDecodeError, OSError):
            finding_count = 0
    else:
        finding_count = _count_json_findings(proc.stdout, "regressions", "findings")
    hard_fail = strict and proc.returncode != 0
    status = "fail" if hard_fail else ("warn" if proc.returncode != 0 else "pass")
    if not strict and proc.returncode != 0:
        status = "soft_fail"
    return {
        "name": "ast-metrics",
        "hard": strict,
        "status": status if not (strict and proc.returncode != 0) else "fail",
        "exit_code": proc.returncode,
        "finding_count": finding_count,
        "error_count": finding_count if hard_fail else 0,
        "warning_count": finding_count if not hard_fail else 0,
        "report": str(report_json.relative_to(project_root))
        if report_json.is_relative_to(project_root)
        else str(report_json),
    }


def run_revet(
    project_root: Path,
    out_dir: Path,
    *,
    base: str,
    strict: bool,
) -> dict[str, Any]:
    raw_path = out_dir / "revet.json"
    cmd = [
        "revet",
        "review",
        "--diff",
        base,
        "--format",
        "json",
    ]
    if strict:
        cmd.extend(["--gate", "error:0"])
    else:
        cmd.extend(["--fail-on", "never"])
    proc = _run(cmd, cwd=project_root, out_path=raw_path)
    # Prefer stdout JSON; meta file also stores stdout.
    finding_count = _count_json_findings(proc.stdout, "findings", "results")
    if finding_count == 0 and raw_path.is_file():
        try:
            meta = json.loads(raw_path.read_text(encoding="utf-8"))
            finding_count = _count_json_findings(
                meta.get("stdout") or "", "findings", "results"
            )
        except (json.JSONDecodeError, OSError):
            pass
    hard_fail = strict and proc.returncode != 0
    if hard_fail:
        status = "fail"
    elif proc.returncode != 0:
        status = "soft_fail"
    else:
        status = "pass"
    return {
        "name": "revet",
        "hard": strict,
        "status": status,
        "exit_code": proc.returncode,
        "finding_count": finding_count,
        "error_count": finding_count if hard_fail else 0,
        "warning_count": finding_count if not hard_fail else 0,
        "report": str(raw_path.relative_to(project_root))
        if raw_path.is_relative_to(project_root)
        else str(raw_path),
    }


def build_summary(
    layers: list[dict[str, Any]],
    *,
    base: str,
    sha: str | None,
    out_dir: Path,
) -> dict[str, Any]:
    failed: list[str] = []
    for layer in layers:
        if layer.get("hard") and layer.get("status") == "fail":
            failed.append(str(layer["name"]))
    verdict = "fail" if failed else "pass"
    return {
        "ts": _utc_now(),
        "sha": sha,
        "base": base,
        "pr": os.environ.get("QUALITY_PR"),
        "ticket": os.environ.get("QUALITY_TICKET"),
        "agent_run_id": os.environ.get("QUALITY_AGENT_RUN_ID"),
        "out_dir": str(out_dir),
        "layers": {layer["name"]: layer for layer in layers},
        "failed_layers": failed,
        "verdict": verdict,
    }


def run_gate(
    *,
    project_root: Path,
    base: str,
    out_dir: Path,
    strict_metrics: bool = False,
    strict_impact: bool = False,
    skip_ingest: bool = False,
) -> tuple[dict[str, Any], int]:
    missing = _require_binaries()
    if missing:
        msg = (
            "quality_gate: missing required binaries: "
            + ", ".join(missing)
            + ". Install via scripts/quality/install_tools.sh"
        )
        print(msg, file=sys.stderr)
        summary = {
            "ts": _utc_now(),
            "sha": _git_sha(project_root),
            "base": base,
            "verdict": "error",
            "failed_layers": ["toolchain"],
            "layers": {},
            "error": msg,
        }
        return summary, EXIT_MISSING_TOOLS

    out_dir.mkdir(parents=True, exist_ok=True)
    layers = [
        run_ast_grep(project_root, out_dir),
        run_ast_metrics(
            project_root, out_dir, base=base, strict=strict_metrics
        ),
        run_revet(project_root, out_dir, base=base, strict=strict_impact),
    ]
    summary = build_summary(
        layers, base=base, sha=_git_sha(project_root), out_dir=out_dir
    )
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if not skip_ingest:
        append_metrics(summary, project_root=project_root)
    exit_code = EXIT_FAIL if summary["verdict"] == "fail" else EXIT_OK
    return summary, exit_code


def _default_out_dir(project_root: Path, sha: str | None) -> Path:
    stamp = sha[:12] if sha else datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return project_root / "_bmad-output" / "quality" / "runs" / stamp


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Git ref to diff against (default: origin/main)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for per-run tool JSON + summary.json",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Repository root (default: cwd)",
    )
    parser.add_argument(
        "--strict-metrics",
        action="store_true",
        help="Fail when AST Metrics regressions cross fail-on=high",
    )
    parser.add_argument(
        "--strict-impact",
        action="store_true",
        help="Fail when Revet finds exceed gate error:0",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Do not append metrics.jsonl",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = (args.project_root or Path.cwd()).resolve()
    sha = _git_sha(project_root)
    out_dir = (args.out_dir or _default_out_dir(project_root, sha)).resolve()
    summary, code = run_gate(
        project_root=project_root,
        base=args.base,
        out_dir=out_dir,
        strict_metrics=args.strict_metrics,
        strict_impact=args.strict_impact,
        skip_ingest=args.skip_ingest,
    )
    print(json.dumps({"verdict": summary.get("verdict"), "out_dir": str(out_dir)}))
    if summary.get("failed_layers"):
        print(
            "failed_layers: " + ", ".join(summary["failed_layers"]),
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
