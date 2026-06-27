"""Unit-тесты разбора GitHub release payload для HumanitecAgent."""

from __future__ import annotations

from apps.agent.models import AgentReleaseAssetChecksum
from apps.agent.service import build_agent_release_status_from_github_payload
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
