"""api healthcheck start_period must cover bootstrap lock+work worst case (#70)."""

from __future__ import annotations

import re
from pathlib import Path

from app.db.bootstrap import LOCK_TIMEOUT_SECONDS, WORK_TIMEOUT_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[3]

# Documented margin beyond LOCK + 2×WORK (compose comments / README).
START_PERIOD_MARGIN_SECONDS = 60.0


def _service_body(compose: str, service: str) -> str:
    pattern = rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)"
    match = re.search(pattern, compose)
    assert match is not None, f"service {service!r} not found"
    return match.group(1)


def _api_start_period_seconds(compose_text: str) -> float:
    body = _service_body(compose_text, "api")
    match = re.search(r"(?m)^      start_period:\s*(\d+(?:\.\d+)?)s\s*$", body)
    assert match is not None, "api healthcheck start_period missing or not Ns form"
    return float(match.group(1))


def test_compose_api_start_period_covers_bootstrap_budget() -> None:
    budget = LOCK_TIMEOUT_SECONDS + 2 * WORK_TIMEOUT_SECONDS + START_PERIOD_MARGIN_SECONDS
    for filename in ("compose.yaml", "compose.dev.yaml"):
        seconds = _api_start_period_seconds((REPO_ROOT / filename).read_text())
        assert seconds >= budget, (
            f"{filename}: api start_period {seconds:g}s < bootstrap budget "
            f"{budget:g}s (LOCK {LOCK_TIMEOUT_SECONDS:g} + 2×WORK "
            f"{WORK_TIMEOUT_SECONDS:g} + margin {START_PERIOD_MARGIN_SECONDS:g})"
        )
