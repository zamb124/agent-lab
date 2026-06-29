"""Unit-тесты followup state machine macOS notarization."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from apps.agent.desktop.macos_notarize import (
    MacosNotarizeManifest,
    MacosNotarizePlatformRecord,
    MacosNotarizeStatus,
    NotaryPollResult,
    followup_release,
)


def _pending_manifest() -> MacosNotarizeManifest:
    return MacosNotarizeManifest(
        release_tag="humanitec-agent-c38f05e",
        version_sha="c38f05eba2528021240ea9f3fface4299e4d30b2",
        deadline_utc="2099-01-01T00:00:00Z",
        platforms={
            "macos-arm64": MacosNotarizePlatformRecord(
                platform="macos-arm64",
                version_sha="c38f05eba2528021240ea9f3fface4299e4d30b2",
                submission_id="903659f6-49e1-42d3-a507-951d750d97e2",
                submitted_at="2026-06-29T07:23:52Z",
                status=MacosNotarizeStatus.PENDING,
                app_bundle_asset="HumanitecAgent-macos-arm64-c38f05e.app-bundle.zip",
                dmg_asset="HumanitecAgent-macos-arm64-c38f05e.dmg",
            ),
        },
    )


def test_followup_keeps_pending_when_apple_in_progress(tmp_path: Path) -> None:
    manifest = _pending_manifest()
    with (
        patch(
            "apps.agent.desktop.macos_notarize.resolve_release_version_sha",
            return_value=manifest.version_sha,
        ),
        patch(
            "apps.agent.desktop.macos_notarize.download_manifest_from_release",
            return_value=manifest,
        ),
        patch(
            "apps.agent.desktop.macos_notarize.poll_submission_once",
            return_value=NotaryPollResult(
                submission_id="903659f6-49e1-42d3-a507-951d750d97e2",
                status="In Progress",
            ),
        ),
        patch("apps.agent.desktop.macos_notarize.upload_release_assets") as upload_mock,
    ):
        summary = followup_release(
            repo="zamb124/agent-lab",
            release_tag=manifest.release_tag,
            work_dir=tmp_path,
        )
    assert summary.platforms_pending == ["macos-arm64"]
    upload_mock.assert_called_once()


def test_followup_marks_expired_after_deadline(tmp_path: Path) -> None:
    manifest = MacosNotarizeManifest(
        release_tag="humanitec-agent-c38f05e",
        version_sha="c38f05eba2528021240ea9f3fface4299e4d30b2",
        deadline_utc="2020-01-01T00:00:00Z",
        platforms=_pending_manifest().platforms,
    )
    with (
        patch(
            "apps.agent.desktop.macos_notarize.resolve_release_version_sha",
            return_value=manifest.version_sha,
        ),
        patch(
            "apps.agent.desktop.macos_notarize.download_manifest_from_release",
            return_value=manifest,
        ),
        patch("apps.agent.desktop.macos_notarize.poll_submission_once") as poll_mock,
        patch("apps.agent.desktop.macos_notarize.upload_release_assets"),
        patch("apps.agent.desktop.macos_notarize.delete_release_assets"),
    ):
        summary = followup_release(
            repo="zamb124/agent-lab",
            release_tag=manifest.release_tag,
            work_dir=tmp_path,
        )
    poll_mock.assert_not_called()
    assert summary.platforms_expired == ["macos-arm64"]


def test_followup_raises_on_rejected_submission(tmp_path: Path) -> None:
    manifest = _pending_manifest()
    with (
        patch(
            "apps.agent.desktop.macos_notarize.resolve_release_version_sha",
            return_value=manifest.version_sha,
        ),
        patch(
            "apps.agent.desktop.macos_notarize.download_manifest_from_release",
            return_value=manifest,
        ),
        patch(
            "apps.agent.desktop.macos_notarize.poll_submission_once",
            return_value=NotaryPollResult(
                submission_id="903659f6-49e1-42d3-a507-951d750d97e2",
                status="Invalid",
            ),
        ),
        patch(
            "apps.agent.desktop.macos_notarize.fetch_notary_submission_log",
            return_value="invalid log",
        ),
        patch("apps.agent.desktop.macos_notarize.upload_release_assets"),
        patch("apps.agent.desktop.macos_notarize.delete_release_assets"),
    ):
        with pytest.raises(RuntimeError, match="rejected"):
            _ = followup_release(
                repo="zamb124/agent-lab",
                release_tag=manifest.release_tag,
                work_dir=tmp_path,
            )
