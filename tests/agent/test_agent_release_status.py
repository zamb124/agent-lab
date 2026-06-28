"""Unit-тесты разбора GitHub release payload для HumanitecAgent."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from apps.agent.models import AgentReleaseAssetChecksum
from apps.agent.service import (
    _github_api_headers,
    _resolve_asset_url_from_release,
    build_agent_release_status_from_github_payload,
)
from core.types import JsonObject


def test_release_status_draft_not_ready() -> None:
    payload: JsonObject = {
        "tag_name": "humanitec-agent-v0.2.0",
        "draft": True,
        "assets": [{"name": "HumanitecAgent-macos-arm64-deadbeef.dmg"}],
    }
    status = build_agent_release_status_from_github_payload(
        payload,
        github_owner="zamb124",
        github_repo="agent-lab",
        asset_checksums=[],
    )
    assert status.ready is False
    assert status.latest_tag == "humanitec-agent-v0.2.0"
    assert status.detail is not None
    assert "draft" in status.detail


def test_release_status_empty_assets_not_ready() -> None:
    payload: JsonObject = {
        "tag_name": "humanitec-agent-v0.2.0",
        "draft": False,
        "assets": [],
    }
    status = build_agent_release_status_from_github_payload(
        payload,
        github_owner="zamb124",
        github_repo="agent-lab",
        asset_checksums=[],
    )
    assert status.ready is False
    assert status.detail == "Release без assets"


def test_release_status_ready_with_checksums() -> None:
    payload: JsonObject = {
        "tag_name": "humanitec-agent-v0.2.0",
        "draft": False,
        "assets": [{"name": "HumanitecAgent-macos-arm64-deadbeef.dmg"}],
    }
    checksums = [
        AgentReleaseAssetChecksum(
            asset_name="HumanitecAgent-macos-arm64-deadbeef.dmg",
            sha256="abc123",
        )
    ]
    status = build_agent_release_status_from_github_payload(
        payload,
        github_owner="zamb124",
        github_repo="agent-lab",
        asset_checksums=checksums,
    )
    assert status.ready is True
    assert status.latest_tag == "humanitec-agent-v0.2.0"
    assert len(status.asset_checksums) == 1


def test_resolve_asset_url_macos_ignores_appimage_listed_first() -> None:
    version_sha = "077d469f78e574fe8b34f66adf77312402a3d5"
    appimage_name = f"HumanitecAgent-{version_sha}.AppImage"
    dmg_name = f"HumanitecAgent-macos-arm64-{version_sha}.dmg"
    payload: JsonObject = {
        "assets": [
            {
                "name": appimage_name,
                "browser_download_url": "https://github.example/appimage",
            },
            {
                "name": dmg_name,
                "browser_download_url": "https://github.example/dmg",
            },
        ],
    }
    url = _resolve_asset_url_from_release(payload, "macos-arm64")
    assert url == "https://github.example/dmg"


def test_resolve_asset_url_appimage_not_macos_dmg() -> None:
    version_sha = "077d469f78e574fe8b34f66adf77312402a3d5"
    appimage_name = f"HumanitecAgent-{version_sha}.AppImage"
    dmg_name = f"HumanitecAgent-macos-arm64-{version_sha}.dmg"
    payload: JsonObject = {
        "assets": [
            {"name": dmg_name, "browser_download_url": "https://github.example/dmg"},
            {
                "name": appimage_name,
                "browser_download_url": "https://github.example/appimage",
            },
        ],
    }
    url = _resolve_asset_url_from_release(payload, "linux-appimage")
    assert url == "https://github.example/appimage"


def test_resolve_asset_url_missing_platform() -> None:
    payload: JsonObject = {
        "assets": [
            {
                "name": "HumanitecAgent-deadbeef.AppImage",
                "browser_download_url": "https://github.example/appimage",
            },
        ],
    }
    with pytest.raises(HTTPException) as exc_info:
        _ = _resolve_asset_url_from_release(payload, "macos-arm64")
    assert exc_info.value.status_code == 404


def test_github_api_headers_include_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.agent.config import reset_agent_settings

    monkeypatch.setenv("AGENT__RELEASES__GITHUB_TOKEN", "ghp_test_token")
    reset_agent_settings()
    headers = _github_api_headers()
    assert headers["Authorization"] == "Bearer ghp_test_token"
    reset_agent_settings()
    monkeypatch.delenv("AGENT__RELEASES__GITHUB_TOKEN", raising=False)
