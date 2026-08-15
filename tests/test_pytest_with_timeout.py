"""Wall-clock обёртка убивает process group, не только родителя."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WRAPPER = _REPO_ROOT / "scripts" / "pytest_with_timeout.py"


@pytest.mark.timeout(10)
def test_pytest_with_timeout_kills_child_before_sleep_finishes() -> None:
    started = time.monotonic()
    completed = subprocess.run(
        [
            sys.executable,
            str(_WRAPPER),
            "0.8",
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ],
        check=False,
        cwd=_REPO_ROOT,
    )
    elapsed = time.monotonic() - started
    assert completed.returncode == 124
    assert elapsed < 5.0
