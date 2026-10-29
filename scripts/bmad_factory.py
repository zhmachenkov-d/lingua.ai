#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "cursor-sdk",
#   "pyyaml",
# ]
# ///
"""BMAD factory — lean autonomous ticket/epic/bugs/spikes/deferred orchestrator.

Thin entrypoint — implementation lives in ``scripts/bmad_factory/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `uv run scripts/bmad_factory.py` to import the sibling package.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from bmad_factory.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
