"""Python CTAS must match web CtaId / label-map keys (#74)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TURN_PY = REPO_ROOT / "apps" / "api" / "app" / "router" / "turn.py"
CHAT_TYPES_TS = REPO_ROOT / "apps" / "web" / "src" / "app" / "chat" / "chat.types.ts"
CTA_LABELS_TS = REPO_ROOT / "apps" / "web" / "src" / "app" / "chat" / "cta-labels.ts"


def _python_ctas() -> list[str]:
    text = TURN_PY.read_text()
    match = re.search(
        r"(?m)^CTAS: Final(?:\[[^\]]+\])? = \(([^)]*)\)",
        text,
    )
    assert match is not None, "CTAS tuple not found in turn.py"
    ids = re.findall(r'"([^"]+)"', match.group(1))
    assert ids, "CTAS tuple is empty"
    return ids


def _ts_cta_ids() -> list[str]:
    text = CHAT_TYPES_TS.read_text()
    match = re.search(
        r"export type CtaId = (.+?);",
        text,
        re.DOTALL,
    )
    assert match is not None, "CtaId type not found in chat.types.ts"
    ids = re.findall(r"'([^']+)'", match.group(1))
    assert ids, "CtaId union is empty"
    return ids


def _ts_label_keys() -> list[str]:
    text = CTA_LABELS_TS.read_text()
    match = re.search(
        r"const CTA_LABELS: Record<CtaId, string> = \{([^}]+)\}",
        text,
        re.DOTALL,
    )
    assert match is not None, "CTA_LABELS not found in cta-labels.ts"
    keys = re.findall(r"(?m)^\s*([a-z_]+)\s*:", match.group(1))
    assert keys, "CTA_LABELS has no keys"
    return keys


def test_cta_id_sets_locked_across_api_and_web() -> None:
    python_ids = _python_ctas()
    ts_ids = _ts_cta_ids()
    label_keys = _ts_label_keys()
    assert set(python_ids) == set(ts_ids) == set(label_keys), (
        f"CTA id sets diverge: CTAS={python_ids!r} CtaId={ts_ids!r} "
        f"CTA_LABELS keys={label_keys!r}"
    )
    assert python_ids == ts_ids == label_keys, (
        f"CTA id order diverges: CTAS={python_ids!r} CtaId={ts_ids!r} "
        f"CTA_LABELS keys={label_keys!r}"
    )
