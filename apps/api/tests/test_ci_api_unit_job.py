"""CI must run the unmarked api unit suite (retro R12 / #62)."""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "apps" / "api"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_api_unit_job_runs_unmarked_pytest() -> None:
    workflow = CI_WORKFLOW.read_text()
    assert "api-unit:" in workflow
    assert 'pytest -m "not integration_db"' in workflow
    assert "pytest -m integration_db" in workflow


def test_ci_api_unit_markexpr_does_not_require_database_url() -> None:
    env = {**os.environ, "CI": "true"}
    env.pop("DATABASE_URL", None)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "not integration_db",
            "--collect-only",
            "-q",
        ],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "DATABASE_URL not set" not in out
