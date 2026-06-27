"""Release smoke tests for HumanitecAgent download redirect (локальный артефакт)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from apps.agent.config import reset_agent_settings
from scripts.agent_build import detect_host_platform
from tests.agent._helpers import AGENT_API_PREFIX
from tests.agent.fixtures.local_releases import require_local_release_asset_name


@pytest.mark.asyncio
async def test_r_d1_download_local_release_redirect(
    agent_frontend_http_client: AsyncClient,
    agent_local_release_artifact: Path,
) -> None:
    reset_agent_settings()
    _ = require_local_release_asset_name(agent_local_release_artifact)
    response = await agent_frontend_http_client.get(
        f"{AGENT_API_PREFIX}/releases/status",
        timeout=30.0,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    platform_name = detect_host_platform()
    download_response = await agent_frontend_http_client.get(
        f"{AGENT_API_PREFIX}/download/{platform_name}",
        follow_redirects=False,
        timeout=30.0,
    )
    assert download_response.status_code == 307
    location = download_response.headers.get("location")
    assert isinstance(location, str)
    assert "/releases/artifact/" in location
