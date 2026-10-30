"""Normalize a quality_gate summary into one append-only JSONL metrics line."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_METRICS_PATH = Path("_bmad-output/quality/metrics.jsonl")


def _layer_counts(summary: dict[str, Any], name: str) -> dict[str, Any]:
    layer = summary.get("layers", {}).get(name) or {}
    if not isinstance(layer, dict):
        return {"status": "missing"}
    return {
        "status": layer.get("status"),
        "exit_code": layer.get("exit_code"),
        "finding_count": layer.get("finding_count"),
        "error_count": layer.get("error_count"),
        "warning_count": layer.get("warning_count"),
        "hard": bool(layer.get("hard")),
    }


def build_metrics_record(
    summary: dict[str, Any],
    *,
    ticket: str | None = None,
    agent_run_id: str | None = None,
    pr: str | None = None,
) -> dict[str, Any]:
    """Build one JSONL-ready record from a gate summary dict."""
    failed = list(summary.get("failed_layers") or [])
    return {
        "ts": summary.get("ts") or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha": summary.get("sha"),
        "base": summary.get("base"),
        "pr": pr
        if pr is not None
        else summary.get("pr") or os.environ.get("QUALITY_PR"),
        "ticket": ticket
        if ticket is not None
        else summary.get("ticket") or os.environ.get("QUALITY_TICKET"),
        "agent_run_id": agent_run_id
        if agent_run_id is not None
        else summary.get("agent_run_id") or os.environ.get("QUALITY_AGENT_RUN_ID"),
        "antipattern": _layer_counts(summary, "ast-grep"),
        "assertions": _layer_counts(summary, "assertion-guard"),
        "complexity": _layer_counts(summary, "ast-metrics"),
        "impact": _layer_counts(summary, "revet"),
        "verdict": summary.get("verdict"),
        "failed_layers": failed,
    }


def append_metrics(
    summary: dict[str, Any],
    *,
    metrics_path: Path | None = None,
    project_root: Path | None = None,
    ticket: str | None = None,
    agent_run_id: str | None = None,
    pr: str | None = None,
) -> Path:
    """Append one normalized metrics line; create parent dirs as needed."""
    root = project_root or Path.cwd()
    path = metrics_path or (root / DEFAULT_METRICS_PATH)
    if not path.is_absolute():
        path = root / path
    path.parent.mkdir(parents=True, exist_ok=True)
    record = build_metrics_record(
        summary, ticket=ticket, agent_run_id=agent_run_id, pr=pr
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "summary",
        type=Path,
        help="Path to quality_gate summary.json",
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=None,
        help=f"JSONL path (default: {DEFAULT_METRICS_PATH})",
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    out = append_metrics(
        summary, metrics_path=args.metrics, project_root=args.project_root
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
