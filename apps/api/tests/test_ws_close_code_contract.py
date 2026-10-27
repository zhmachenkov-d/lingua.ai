"""Api and web WS already-open close codes must stay locked at 4009 (#113)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WS_PY = REPO_ROOT / "apps" / "api" / "app" / "api" / "routes" / "ws.py"
CHAT_TYPES_TS = REPO_ROOT / "apps" / "web" / "src" / "app" / "chat" / "chat.types.ts"
CHAT_WS_SERVICE_TS = (
    REPO_ROOT / "apps" / "web" / "src" / "app" / "chat" / "chat-ws.service.ts"
)

LOCKED_CODE = 4009
CONST_NAME = "WS_ALREADY_OPEN_CLOSE_CODE"


def _python_close_code(source: str) -> int:
    match = re.search(
        rf"(?m)^{CONST_NAME}\s*=\s*(\d+)\s*$",
        source,
    )
    assert match is not None, f"{CONST_NAME} not found in ws.py"
    return int(match.group(1))


def _ts_close_code(source: str) -> int:
    match = re.search(
        rf"(?m)^export const {CONST_NAME}\s*=\s*(\d+)\s*;\s*$",
        source,
    )
    assert match is not None, f"{CONST_NAME} not found in chat.types.ts"
    return int(match.group(1))


def _prod_uses_named_close(source: str) -> bool:
    """True when a close site passes the named constant (not a raw literal)."""
    return bool(
        re.search(
            rf"\.close\(\s*code\s*=\s*{CONST_NAME}\s*\)",
            source,
        )
    )


def _prod_reads_named_close(source: str) -> bool:
    """True when the close-code read path compares against the named constant."""
    return CONST_NAME in source and bool(
        re.search(
            rf"event\.code\s*===\s*{CONST_NAME}",
            source,
        )
    )


def _has_raw_prod_close_literal(source: str, code: int) -> bool:
    """Detect raw close(code=<code>) outside the constant definition line."""
    for line in source.splitlines():
        if re.search(rf"(?m)^\s*{CONST_NAME}\s*=", line):
            continue
        if re.search(rf"\.close\(\s*code\s*=\s*{code}\s*\)", line):
            return True
        if re.search(rf"event\.code\s*===\s*{code}\b", line):
            return True
    return False


def test_ws_already_open_close_code_locked_across_api_and_web() -> None:
    ws_src = WS_PY.read_text(encoding="utf-8")
    types_src = CHAT_TYPES_TS.read_text(encoding="utf-8")
    service_src = CHAT_WS_SERVICE_TS.read_text(encoding="utf-8")

    api_code = _python_close_code(ws_src)
    web_code = _ts_close_code(types_src)

    assert api_code == web_code == LOCKED_CODE, (
        f"{CONST_NAME} diverge: api={api_code!r} web={web_code!r} "
        f"locked={LOCKED_CODE!r}"
    )

    assert _prod_uses_named_close(ws_src), (
        f"api close path must use {CONST_NAME}, not a raw literal"
    )
    assert _prod_reads_named_close(service_src), (
        f"web close-code read path must use {CONST_NAME}, not a raw literal"
    )
    assert not _has_raw_prod_close_literal(ws_src, LOCKED_CODE), (
        f"api prod site must not use raw close(code={LOCKED_CODE})"
    )
    assert not _has_raw_prod_close_literal(service_src, LOCKED_CODE), (
        f"web prod site must not compare event.code === {LOCKED_CODE}"
    )
