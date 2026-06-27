"""Локальный release-артефакт HumanitecAgent для тестов (без GitHub API)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from apps.agent.config import reset_agent_settings
from scripts.agent_build import detect_host_platform


@pytest.fixture(scope="session")
def agent_local_release_artifact() -> Path:
    from tests.agent.desktop_e2e.desktop_app import ensure_humanitec_desktop_release_artifact

    artifact_path = ensure_humanitec_desktop_release_artifact()
    return artifact_path


def require_local_release_asset_name(artifact_path: Path) -> str:
    platform_name = detect_host_platform()
    pattern_prefix = artifact_path.name.split(platform_name)[0]
    if platform_name not in artifact_path.name:
        raise RuntimeError(
            f"Local artifact {artifact_path.name!r} does not match platform {platform_name!r}"
        )
    _ = pattern_prefix
    return artifact_path.name


@contextmanager
def agent_release_github_env(
    *,
    github_owner: str | None = None,
    github_repo: str | None = None,
    github_api_base_url: str | None = None,
    release_source: str | None = None,
) -> Iterator[None]:
    previous: dict[str, str | None] = {
        "AGENT__RELEASES__GITHUB_OWNER": os.environ.get("AGENT__RELEASES__GITHUB_OWNER"),
        "AGENT__RELEASES__GITHUB_REPO": os.environ.get("AGENT__RELEASES__GITHUB_REPO"),
        "AGENT__RELEASES__GITHUB_API_BASE_URL": os.environ.get(
            "AGENT__RELEASES__GITHUB_API_BASE_URL"
        ),
        "AGENT__RELEASES__SOURCE": os.environ.get("AGENT__RELEASES__SOURCE"),
    }
    try:
        if github_owner is not None:
            os.environ["AGENT__RELEASES__GITHUB_OWNER"] = github_owner
        if github_repo is not None:
            os.environ["AGENT__RELEASES__GITHUB_REPO"] = github_repo
        if github_api_base_url is not None:
            os.environ["AGENT__RELEASES__GITHUB_API_BASE_URL"] = github_api_base_url
        if release_source is not None:
            os.environ["AGENT__RELEASES__SOURCE"] = release_source
        reset_agent_settings()
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_agent_settings()


@pytest.fixture
def agent_release_github_missing_repo() -> Iterator[None]:
    with agent_release_github_env(
        github_owner="octocat",
        github_repo="humanitec-agent-release-missing-test-repo",
        release_source="github",
    ):
        yield
