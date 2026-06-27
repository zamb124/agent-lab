"""Локальные release-артефакты HumanitecAgent для TESTING (без GitHub API)."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
from pathlib import Path

from apps.agent.config import get_agent_settings
from apps.agent.desktop.artifact_verify import MIN_RELEASE_BYTES, is_placeholder_artifact
from apps.agent.desktop.build_contract import (
    artifact_path as contract_artifact_path,
)
from apps.agent.desktop.build_contract import (
    load_default_distro_config,
)
from apps.agent.models import AgentReleaseAssetChecksum, AgentReleaseStatusResponse
from core.logging import get_logger

logger = get_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_DIST_DIR = REPO_ROOT / "apps" / "agent" / "desktop" / "dist"
LOCAL_RELEASE_TAG = "humanitec-agent-local"


def detect_host_platform() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "macos-arm64"
        return "macos-x64"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux-deb"
    raise RuntimeError(f"Unsupported host OS for HumanitecAgent build: {system}")


def release_source() -> str:
    configured = os.environ.get("AGENT__RELEASES__SOURCE")
    if configured is not None and configured.strip():
        return configured.strip()
    if os.environ.get("TESTING") == "true":
        return "local"
    return "github"


def use_local_release_artifact() -> bool:
    return release_source() == "local"


def git_head_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
    )
    sha = completed.stdout.strip()
    if not sha:
        raise RuntimeError("git rev-parse HEAD returned empty sha")
    return sha


def resolve_local_release_artifact_path(platform: str) -> Path:
    distro = load_default_distro_config()
    version_sha = git_head_sha()
    artifact = contract_artifact_path(DESKTOP_DIST_DIR, platform, version_sha, distro)
    if not artifact.is_file():
        raise FileNotFoundError(
            f"Local HumanitecAgent artifact missing: {artifact}. "
            + "Run: AGENT_ARTIFACT_MODE=release make agent-ensure"
        )
    if is_placeholder_artifact(artifact):
        raise ValueError(
            f"Local HumanitecAgent artifact is placeholder: {artifact}. "
            + "Run: AGENT_ARTIFACT_MODE=release make agent-ensure"
        )
    if artifact.stat().st_size < MIN_RELEASE_BYTES:
        raise ValueError(
            f"Local HumanitecAgent artifact too small: {artifact} "
            + f"({artifact.stat().st_size} bytes). "
            + "Run: AGENT_ARTIFACT_MODE=release make agent-ensure"
        )
    return artifact


def local_release_artifact_route(platform: str) -> str:
    return f"/frontend/api/agent/releases/artifact/{platform}"


def build_local_release_status(platform: str) -> AgentReleaseStatusResponse:
    settings = get_agent_settings()
    artifact = resolve_local_release_artifact_path(platform)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return AgentReleaseStatusResponse(
        ready=True,
        latest_tag=LOCAL_RELEASE_TAG,
        github_owner=settings.releases.github_owner,
        github_repo=settings.releases.github_repo,
        asset_checksums=[
            AgentReleaseAssetChecksum(asset_name=artifact.name, sha256=digest),
        ],
    )


def build_local_release_unavailable_status(platform: str, detail: str) -> AgentReleaseStatusResponse:
    settings = get_agent_settings()
    logger.warning(
        "agent.releases.local_unavailable",
        platform=platform,
        detail=detail,
    )
    return AgentReleaseStatusResponse(
        ready=False,
        latest_tag=None,
        github_owner=settings.releases.github_owner,
        github_repo=settings.releases.github_repo,
        detail=detail,
    )
