"""Offline execution contracts for the public bootstrap shell entry points."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "ops" / "test-bootstrap-scripts.sh"


def test_bootstrap_entry_points_with_fake_commands_only():
    """Run the shell harness without Docker, network access, or real installs."""
    if os.name == "nt":
        wsl = shutil.which("wsl.exe")
        if wsl is None:
            pytest.skip("WSL is required to execute bootstrap shell contracts")
        command = [
            wsl,
            "--cd",
            str(REPO_ROOT),
            "--",
            "bash",
            "ops/test-bootstrap-scripts.sh",
        ]
    else:
        bash = shutil.which("bash")
        if bash is None:
            pytest.skip("bash is required to execute bootstrap shell contracts")
        command = [bash, str(HARNESS)]

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
