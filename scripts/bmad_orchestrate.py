#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "cursor-sdk",
#   "pyyaml",
# ]
# ///
"""BMAD Cursor build orchestrator (ticket-tree loop).

Thin entrypoint — implementation lives in ``scripts/bmad_orchestrate/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `uv run scripts/bmad_orchestrate.py` to import the sibling package.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from bmad_orchestrate.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
