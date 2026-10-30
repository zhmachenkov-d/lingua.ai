"""Tests for factory run.log dual-sink and short tool console output."""

from __future__ import annotations

import io
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bmad_factory import agent as agent_mod
from bmad_factory.constants import (
    attach_run_log,
    configure_logging,
    detach_run_log,
    log,
)
from bmad_factory.run_state import create_run, run_log_path


class RunLogPathTests(unittest.TestCase):
    def test_run_log_path_under_runs_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = run_log_path(root, "rid-1")
            self.assertEqual(
                path, root / ".bmad-factory" / "runs" / "rid-1" / "run.log"
            )


class AttachRunLogTests(unittest.TestCase):
    def tearDown(self) -> None:
        detach_run_log()
        configure_logging("WARNING")

    def test_attach_writes_info_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            configure_logging("INFO")
            attach_run_log(path)
            log.info("hello-run-log")
            detach_run_log()
            text = path.read_text(encoding="utf-8")
            self.assertIn("hello-run-log", text)
            self.assertIn("INFO", text)

    def test_attach_idempotent_same_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            configure_logging("INFO")
            attach_run_log(path)
            attach_run_log(path)
            root = logging.getLogger()
            file_handlers = [
                h
                for h in root.handlers
                if getattr(h, "name", None) == "bmad_factory_run_log"
            ]
            self.assertEqual(len(file_handlers), 1)


class ToolEmitTests(unittest.TestCase):
    def tearDown(self) -> None:
        agent_mod.detach_agent_run_log()

    def test_tool_console_header_only_full_in_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            agent_mod.attach_agent_run_log(path)
            msg = SimpleNamespace(
                type="tool_call",
                name="grep",
                status="running",
                args={"pattern": "foo", "path": "bar.py"},
                result=None,
            )
            buf = io.StringIO()
            with mock.patch.object(sys, "stderr", buf):
                with mock.patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
                    agent_mod._emit_agent_message(msg)

            console = buf.getvalue()
            self.assertIn("grep [running]", console)
            self.assertNotIn("pattern", console)
            self.assertNotIn("foo", console)

            file_text = path.read_text(encoding="utf-8")
            self.assertIn("grep [running]", file_text)
            self.assertIn("pattern", file_text)
            self.assertIn("foo", file_text)

    def test_tool_completed_result_only_in_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            agent_mod.attach_agent_run_log(path)
            msg = SimpleNamespace(
                type="tool_call",
                name="Shell",
                status="completed",
                args={"command": "echo hi"},
                result={"stdout": "hi\n"},
            )
            buf = io.StringIO()
            with mock.patch.object(sys, "stderr", buf):
                with mock.patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
                    agent_mod._emit_agent_message(msg)

            console = buf.getvalue()
            self.assertIn("Shell [completed]", console)
            self.assertNotIn("echo hi", console)
            self.assertNotIn("→", console)

            file_text = path.read_text(encoding="utf-8")
            self.assertIn("Shell [completed]", file_text)
            self.assertIn("echo hi", file_text)
            self.assertIn("→", file_text)
            self.assertIn("stdout", file_text)


class CreateRunLogAlongsideState(unittest.TestCase):
    def tearDown(self) -> None:
        detach_run_log()
        agent_mod.detach_agent_run_log()
        configure_logging("WARNING")

    def test_create_run_log_path_matches_run_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "_bmad").mkdir()
            state = create_run(root, mode="bugs", model="auto")
            path = run_log_path(root, state.run_id)
            self.assertTrue(path.parent.is_dir())
            configure_logging("INFO")
            attach_run_log(path)
            agent_mod.attach_agent_run_log(path)
            log.info("session-start")
            agent_mod._emit_agent_line("status", "----- begin -----")
            detach_run_log()
            agent_mod.detach_agent_run_log()
            text = path.read_text(encoding="utf-8")
            self.assertIn("session-start", text)
            self.assertIn("----- begin -----", text)


if __name__ == "__main__":
    unittest.main()
