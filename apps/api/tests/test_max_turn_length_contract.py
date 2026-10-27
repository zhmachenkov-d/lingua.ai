"""Api and web max turn length must share one SoT (#112 / backlog 30)."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SOT_PATH = (
    REPO_ROOT
    / "apps"
    / "web"
    / "src"
    / "app"
    / "chat"
    / "max-turn-text-length.json"
)
WS_PY = REPO_ROOT / "apps" / "api" / "app" / "schemas" / "ws.py"
CHAT_COPY_TS = REPO_ROOT / "apps" / "web" / "src" / "app" / "chat" / "chat.copy.ts"

API_ORIGIN = "apps/api/app/schemas/ws.py:MAX_TURN_TEXT_LENGTH"
WEB_ORIGIN = "apps/web/src/app/chat/chat.copy.ts:MAX_MESSAGE_LENGTH"
SOT_ORIGIN = "apps/web/src/app/chat/max-turn-text-length.json:maxTurnTextLength"


def _sot_max() -> int:
    assert SOT_PATH.is_file(), f"SoT missing: {SOT_PATH}"
    raw = json.loads(SOT_PATH.read_text(encoding="utf-8"))
    value = raw.get("maxTurnTextLength", raw)
    assert type(value) is int, (
        f"SoT {SOT_ORIGIN} must be a Number (int), got {type(value).__name__!r}"
    )
    return value


def _web_sot_binding(source: str) -> str | None:
    """Return the import binding name if MAX_MESSAGE_LENGTH uses that SoT field."""
    imports_sot = re.search(
        r"import\s+(\w+)\s+from\s+['\"]\./max-turn-text-length\.json['\"]",
        source,
    )
    if imports_sot is None:
        return None
    name = imports_sot.group(1)
    binds = re.search(
        rf"export\s+const\s+MAX_MESSAGE_LENGTH\s*=\s*{re.escape(name)}\.maxTurnTextLength\s*;",
        source,
    )
    if binds is None:
        return None
    if re.search(r"(?m)^export\s+const\s+MAX_MESSAGE_LENGTH\s*=\s*\d+\s*;", source):
        return None
    return name


def _api_uses_sot(source: str) -> bool:
    loads = "_load_max_turn_text_length" in source and "max-turn-text-length.json" in source
    binds = re.search(
        r"MAX_TURN_TEXT_LENGTH\s*=\s*_load_max_turn_text_length\s*\(\s*\)",
        source,
    )
    bare_literal = re.search(
        r"(?m)^MAX_TURN_TEXT_LENGTH\s*=\s*\d+\s*$",
        source,
    )
    return loads and binds is not None and bare_literal is None


def test_max_turn_length_locked_across_api_and_web() -> None:
    sot = _sot_max()

    from app.schemas.ws import MAX_TURN_TEXT_LENGTH as api_max

    ws_src = WS_PY.read_text(encoding="utf-8")
    copy_src = CHAT_COPY_TS.read_text(encoding="utf-8")

    assert _api_uses_sot(ws_src), (
        f"{API_ORIGIN} must load {SOT_ORIGIN} (fail-closed; no independent literal)"
    )
    assert _web_sot_binding(copy_src) is not None, (
        f"{WEB_ORIGIN} must import/bind {SOT_ORIGIN} "
        f"(same identifier; fail-closed; no independent literal)"
    )

    # Web effective max is the SoT field once the same-binding check above passes.
    web_max = sot
    assert api_max == web_max, (
        f"max turn length diverge: {API_ORIGIN}={api_max!r} "
        f"{WEB_ORIGIN}={web_max!r} {SOT_ORIGIN}={sot!r}"
    )
