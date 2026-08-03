"""CI script check_tool_contracts.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_check_tool_contracts_exits_zero_on_current_tree() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "check_tool_contracts.py")],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
