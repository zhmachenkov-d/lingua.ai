"""Client TURN_IDLE_MS must exceed server LLM+write turn worst case (#111)."""

from __future__ import annotations

import re
from pathlib import Path

from app.llm.adapter import REQUEST_TIMEOUT_SECONDS
from app.router.turn import CHECKPOINTER_WRITE_TIMEOUT_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[3]
CHAT_SHELL = REPO_ROOT / "apps/web/src/app/chat/chat-shell.ts"


def _turn_idle_ms(source: str) -> int:
    match = re.search(
        r"(?m)^export const TURN_IDLE_MS = (\d[\d_]*)\s*;\s*$",
        source,
    )
    assert match is not None, "TURN_IDLE_MS export missing or not numeric form"
    return int(match.group(1).replace("_", ""))


def test_chat_turn_idle_above_server_llm_write_worst_case() -> None:
    # classify_turn: primary then escalate; write_turn_snapshot: aput then mirror.
    worst_case_ms = int(
        (
            2 * REQUEST_TIMEOUT_SECONDS
            + 2 * CHECKPOINTER_WRITE_TIMEOUT_SECONDS
        )
        * 1000
    )
    idle_ms = _turn_idle_ms(CHAT_SHELL.read_text(encoding="utf-8"))
    assert idle_ms > worst_case_ms, (
        f"TURN_IDLE_MS {idle_ms}ms ≤ server turn worst case {worst_case_ms}ms "
        f"(2×REQUEST {REQUEST_TIMEOUT_SECONDS:g}s + 2×CHECKPOINTER "
        f"{CHECKPOINTER_WRITE_TIMEOUT_SECONDS:g}s)"
    )
