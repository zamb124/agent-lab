"""HumanitecAgent download URL host-aware (multi-brand)."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.agent.service import fetch_latest_release_asset_url


@pytest.mark.asyncio
async def test_fetch_latest_release_asset_url_linnex_local_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.agent.service.use_local_release_artifact", lambda: True)
    monkeypatch.setattr(
        "apps.agent.service.resolve_local_release_artifact_path",
        lambda _platform: Path("HumanitecAgent-macos-arm64-test.dmg"),
    )
    monkeypatch.setattr(
        "apps.agent.service.local_release_artifact_route",
        lambda _platform: "/frontend/api/agent/releases/artifact/macos-arm64",
    )
    url = await fetch_latest_release_asset_url("macos-arm64", brand_host="linnex.io")
    assert url == "https://linnex.io/frontend/api/agent/releases/artifact/macos-arm64"
