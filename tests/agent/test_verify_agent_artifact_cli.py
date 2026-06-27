"""CLI verify_agent_artifact интеграция."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "apps" / "agent" / "desktop" / "scripts" / "build.sh"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_agent_artifact.py"


def test_verify_agent_artifact_cli_placeholder(tmp_path: Path) -> None:
    version_sha = f"cli-{uuid.uuid4().hex[:12]}"
    env = {"AGENT_OUTPUT_DIR": str(tmp_path)}
    _ = subprocess.run(
        [
            str(BUILD_SCRIPT),
            "--platform",
            "linux-deb",
            "--artifact-mode",
            "placeholder",
            "--version-sha",
            version_sha,
        ],
        cwd=str(REPO_ROOT),
        env={**env, **__import__("os").environ},
        check=True,
    )
    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(VERIFY_SCRIPT),
            "--platform",
            "linux-deb",
            "--version-sha",
            version_sha,
            "--artifact-mode",
            "placeholder",
            "--dist-dir",
            str(tmp_path),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
