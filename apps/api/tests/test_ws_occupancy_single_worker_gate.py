"""MVP /ws occupancy is process-local — deploy must stay single-worker (#69)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _service_body(compose: str, service: str) -> str:
    pattern = rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:|\Z)"
    match = re.search(pattern, compose)
    assert match is not None, f"service {service!r} not found"
    return match.group(1)


def _assert_single_worker_surface(text: str, *, label: str) -> None:
    assert "--workers" not in text, (
        f"{label}: do not pass uvicorn --workers — MVP /ws occupancy is process-local (C2)"
    )
    assert "WEB_CONCURRENCY" not in text, (
        f"{label}: WEB_CONCURRENCY is unsupported — occupancy is process-local"
    )
    for match in re.finditer(
        r"(?m)^\s*replicas:\s*[\"']?(\d+)[\"']?\s*(?:#.*)?$",
        text,
    ):
        n = int(match.group(1))
        assert n <= 1, f"{label}: api deploy.replicas must be ≤1 for MVP C2; got {n}"


def test_api_dockerfile_cmd_is_single_worker() -> None:
    dockerfile = (REPO_ROOT / "apps/api/Dockerfile").read_text()
    _assert_single_worker_surface(dockerfile, label="apps/api/Dockerfile")
    assert re.search(
        r'(?m)^CMD\s*\[\s*"uvicorn"',
        dockerfile,
    ), "apps/api/Dockerfile must CMD uvicorn (single process by default)"


def test_compose_api_launch_is_single_worker() -> None:
    for filename in ("compose.yaml", "compose.dev.yaml"):
        body = _service_body((REPO_ROOT / filename).read_text(), "api")
        _assert_single_worker_surface(body, label=f"{filename} api")
        if filename == "compose.yaml":
            assert not re.search(r"(?m)^    (?:command|entrypoint):", body), (
                "compose.yaml api must inherit Dockerfile CMD (no command/entrypoint override)"
            )
        else:
            assert re.search(r"(?m)^    command:", body), (
                "compose.dev.yaml api must set an explicit command"
            )
            assert '"uvicorn"' in body or "'uvicorn'" in body, (
                "compose.dev.yaml api.command must launch uvicorn (single process by default)"
            )
