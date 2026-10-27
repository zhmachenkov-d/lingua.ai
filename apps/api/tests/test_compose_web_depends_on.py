"""compose.dev web must wait on api healthy (parity with compose.yaml / #64)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _service_body(compose: str, service: str) -> str:
    pattern = rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)"
    match = re.search(pattern, compose)
    assert match is not None, f"service {service!r} not found"
    return match.group(1)


def test_compose_web_depends_on_api_service_healthy() -> None:
    for filename in ("compose.yaml", "compose.dev.yaml"):
        body = _service_body((REPO_ROOT / filename).read_text(), "web")
        depends = re.search(r"(?ms)^    depends_on:\n((?:^      .+\n)+)", body)
        assert depends is not None, f"{filename}: web.depends_on missing"
        block = depends.group(1)
        assert re.search(
            r"(?m)^      api:\n        condition: service_healthy\s*$",
            block,
        ), (
            f"{filename}: web must wait on api with condition service_healthy; got:\n{block}"
        )
