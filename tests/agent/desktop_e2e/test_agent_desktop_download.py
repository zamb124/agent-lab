"""Desktop E2E: download, discover, release install (локальный release-артефакт)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from apps.agent.desktop.artifact_verify import is_placeholder_artifact
from apps.agent.config import reset_agent_settings
from apps.frontend.config import get_frontend_public_base_url
from tests.agent._helpers import AGENT_API_PREFIX
from tests.agent.fixtures.local_releases import require_local_release_asset_name
from scripts.agent_build import detect_host_platform


@pytest.mark.asyncio
async def test_d1_download_redirect(
    agent_frontend_http_client: AsyncClient,
    agent_local_release_artifact: Path,
) -> None:
    reset_agent_settings()
    asset_name = require_local_release_asset_name(agent_local_release_artifact)
    platform_name = detect_host_platform()
    response = await agent_frontend_http_client.get(
        f"{AGENT_API_PREFIX}/download/{platform_name}",
        follow_redirects=False,
    )
    assert response.status_code == 307
    location = response.headers.get("location")
    assert isinstance(location, str)
    assert "/releases/artifact/" in location
    assert asset_name in location or location.endswith(platform_name)


@pytest.mark.asyncio
async def test_d2_releases_status_checksums(
    agent_frontend_http_client: AsyncClient,
    agent_local_release_artifact: Path,
) -> None:
    reset_agent_settings()
    asset_name = require_local_release_asset_name(agent_local_release_artifact)
    response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/releases/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["latest_tag"] == "humanitec-agent-local"
    checksums = body.get("asset_checksums")
    assert isinstance(checksums, list)
    assert any(entry.get("asset_name") == asset_name for entry in checksums)


def test_d3_release_artifact_installed(
    humanitec_desktop_release_artifact: str,
    humanitec_desktop_install,
) -> None:
    artifact_path = Path(humanitec_desktop_release_artifact)
    assert artifact_path.is_file()
    assert not is_placeholder_artifact(artifact_path)
    assert humanitec_desktop_install.executable.is_file()


@pytest.mark.asyncio
async def test_d_discover_url_bundle(
    agent_frontend_http_client: AsyncClient,
    agent_local_release_artifact: Path,
) -> None:
    reset_agent_settings()
    _ = require_local_release_asset_name(agent_local_release_artifact)
    response = await agent_frontend_http_client.get(f"{AGENT_API_PREFIX}/discover")
    assert response.status_code == 200
    body = response.json()
    base = get_frontend_public_base_url()
    assert body["frontend_base_url"] == base
    assert body["platform_mcp_url"] == f"{base}/flows/api/v1/agent/platform-mcp"
    assert body["tunnel_ws_url"].startswith("ws://")
    assert body["releases"]["ready"] is True
