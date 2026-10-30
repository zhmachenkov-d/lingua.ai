"""Normalize mutmut / Stryker results into a soft-gate mutation summary."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_OUT_DIR = Path("_bmad-output/quality/mutation")


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _score(killed: int, survived: int, timeout: int) -> float:
    denom = killed + survived + timeout
    if denom <= 0:
        return 0.0
    return round(100.0 * (killed + timeout) / denom, 2)


def load_baseline(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"min_score": 0, "max_survived": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"min_score": 0, "max_survived": None}
    if not isinstance(data, dict):
        return {"min_score": 0, "max_survived": None}
    return {
        "min_score": float(data.get("min_score") or 0),
        "max_survived": data.get("max_survived"),
    }


def parse_mutmut_stats(payload: dict[str, Any]) -> dict[str, int]:
    return {
        "killed": int(payload.get("killed") or 0),
        "survived": int(payload.get("survived") or 0),
        "timeout": int(payload.get("timeout") or 0),
        "no_tests": int(payload.get("no_tests") or 0),
        "skipped": int(payload.get("skipped") or 0),
        "suspicious": int(payload.get("suspicious") or 0),
        "total": int(payload.get("total") or 0),
    }


def parse_stryker_report(payload: dict[str, Any]) -> dict[str, int]:
    """Aggregate mutant statuses from a mutation-testing-report schema JSON."""
    killed = 0
    survived = 0
    timeout = 0
    no_coverage = 0
    errors = 0
    ignored = 0
    files = payload.get("files") or {}
    if not isinstance(files, dict):
        files = {}
    for meta in files.values():
        if not isinstance(meta, dict):
            continue
        for mutant in meta.get("mutants") or []:
            if not isinstance(mutant, dict):
                continue
            status_l = str(mutant.get("status") or "").lower()
            if status_l == "killed":
                killed += 1
            elif status_l == "survived":
                survived += 1
            elif status_l == "timeout":
                timeout += 1
            elif status_l in {"nocoverage", "no_coverage", "no coverage"}:
                no_coverage += 1
            elif status_l in {"compileerror", "runtimeerror", "error"}:
                errors += 1
            elif status_l in {"ignored", "ignoredallowed"}:
                ignored += 1
    total = killed + survived + timeout + no_coverage + errors + ignored
    return {
        "killed": killed,
        "survived": survived,
        "timeout": timeout,
        "no_tests": no_coverage,
        "skipped": ignored,
        "suspicious": errors,
        "total": total,
    }


def build_summary(
    *,
    stack: str,
    counts: dict[str, int],
    baseline: dict[str, Any],
    tool_exit: int = 0,
    parse_error: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    killed = int(counts.get("killed") or 0)
    survived = int(counts.get("survived") or 0)
    timeout = int(counts.get("timeout") or 0)
    score = _score(killed, survived, timeout)

    status = "pass"
    if parse_error:
        status = "error"
    elif tool_exit != 0:
        status = "soft_fail"
    elif (killed + survived + timeout) == 0:
        # Diff skip / empty run: do not soft-fail against min_score.
        status = "pass"
    else:
        min_score = float(baseline.get("min_score") or 0)
        max_survived = baseline.get("max_survived")
        if score < min_score:
            status = "soft_fail"
        if max_survived is not None and survived > int(max_survived):
            status = "soft_fail"

    return {
        "ts": _utc_now(),
        "stack": stack,
        "hard": False,
        "status": status,
        "killed": killed,
        "survived": survived,
        "timeout": timeout,
        "no_tests": int(counts.get("no_tests") or 0),
        "skipped": int(counts.get("skipped") or 0),
        "suspicious": int(counts.get("suspicious") or 0),
        "total": int(counts.get("total") or 0),
        "score": score,
        "baseline": {
            "min_score": float(baseline.get("min_score") or 0),
            "max_survived": baseline.get("max_survived"),
        },
        "tool_exit": tool_exit,
        "parse_error": parse_error,
        "source": source,
    }


def write_summary(summary: dict[str, Any], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", choices=("api", "web"), required=True)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="mutmut-cicd-stats.json or Stryker mutation.json",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Committed baseline JSON (min_score / max_survived)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Output path (default: {DEFAULT_OUT_DIR}/{{stack}}.json)",
    )
    parser.add_argument("--tool-exit", type=int, default=0)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Repo root for relative --out default",
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    out_path = args.out
    if out_path is None:
        out_path = root / DEFAULT_OUT_DIR / f"{args.stack}.json"
    elif not out_path.is_absolute():
        out_path = root / out_path

    parse_error: str | None = None
    counts: dict[str, int] = {
        "killed": 0,
        "survived": 0,
        "timeout": 0,
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "total": 0,
    }
    if not args.input.is_file():
        parse_error = f"missing input: {args.input}"
    else:
        try:
            payload = json.loads(args.input.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                parse_error = "input JSON is not an object"
            elif args.stack == "api":
                counts = parse_mutmut_stats(payload)
            else:
                counts = parse_stryker_report(payload)
        except (OSError, json.JSONDecodeError) as exc:
            parse_error = str(exc)

    baseline = load_baseline(args.baseline)
    summary = build_summary(
        stack=args.stack,
        counts=counts,
        baseline=baseline,
        tool_exit=args.tool_exit,
        parse_error=parse_error,
        source=str(args.input),
    )
    write_summary(summary, out_path)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "score": summary["score"],
                "out": str(out_path),
            }
        )
    )
    # Soft gate: always exit 0 so CI can use continue-on-error or rely on this.
    return 0


if __name__ == "__main__":
    sys.exit(main())
