"""CI script scripts/gates/flows/tool_contracts.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.timeout(60, func_only=True)
def test_check_tool_contracts_exits_zero_on_current_tree() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.gates.flows.tool_contracts"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
