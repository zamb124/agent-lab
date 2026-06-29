"""Unit-тесты macOS async notarization manifest."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apps.agent.desktop.build_contract import (
    load_default_distro_config,
    macos_app_bundle_asset_filename,
    macos_notarize_fragment_filename,
    macos_notarize_manifest_filename,
    matches_release_asset_name,
)
from apps.agent.desktop.macos_notarize import (
    MacosNotarizeFragment,
    MacosNotarizeManifest,
    MacosNotarizePlatformRecord,
    MacosNotarizeStatus,
    build_fragment_for_submit,
    is_followup_active,
    mark_superseded,
    merge_platform_fragments,
    update_checksums_for_dmg,
    write_manifest,
)


def test_internal_asset_names_do_not_match_public_download() -> None:
    distro = load_default_distro_config()
    version_sha = "c38f05eba2528021240ea9f3fface4299e4d30b2"
    app_bundle_asset = macos_app_bundle_asset_filename(
        "macos-arm64",
        version_sha,
        distro.bundle_name,
    )
    assert app_bundle_asset.endswith(".app-bundle.zip")
    assert matches_release_asset_name("macos-arm64", app_bundle_asset, distro.bundle_name) is False
    dmg_name = f"{distro.bundle_name}-macos-arm64-{version_sha}.dmg"
    assert matches_release_asset_name("macos-arm64", dmg_name, distro.bundle_name) is True


def test_merge_platform_fragments_builds_manifest(tmp_path: Path) -> None:
    distro = load_default_distro_config()
    version_sha = "c38f05eba2528021240ea9f3fface4299e4d30b2"
    release_tag = "humanitec-agent-c38f05e"
    for platform_name in ("macos-arm64", "macos-x64"):
        fragment = build_fragment_for_submit(
            platform=platform_name,
            version_sha=version_sha,
            submission_id=f"submission-{platform_name}",
            distro=distro,
        )
        fragment_path = tmp_path / macos_notarize_fragment_filename(
            platform_name,
            version_sha,
            distro.bundle_name,
        )
        fragment_path.write_text(
            json.dumps(fragment.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
    manifest = merge_platform_fragments(
        release_tag=release_tag,
        version_sha=version_sha,
        dist_dir=tmp_path,
    )
    assert manifest.release_tag == release_tag
    assert manifest.version_sha == version_sha
    assert set(manifest.platforms.keys()) == {"macos-arm64", "macos-x64"}
    assert manifest.platforms["macos-arm64"].status == MacosNotarizeStatus.PENDING


def test_mark_superseded_only_pending_platforms() -> None:
    manifest = MacosNotarizeManifest(
        release_tag="humanitec-agent-deadbeef",
        version_sha="deadbeef" * 5,
        deadline_utc="2099-01-01T00:00:00Z",
        platforms={
            "macos-arm64": MacosNotarizePlatformRecord(
                platform="macos-arm64",
                version_sha="deadbeef" * 5,
                submission_id="pending-id",
                submitted_at="2026-06-29T00:00:00Z",
                status=MacosNotarizeStatus.PENDING,
                app_bundle_asset="HumanitecAgent-macos-arm64-deadbeef.app-bundle.zip",
                dmg_asset="HumanitecAgent-macos-arm64-deadbeef.dmg",
            ),
            "macos-x64": MacosNotarizePlatformRecord(
                platform="macos-x64",
                version_sha="deadbeef" * 5,
                submission_id="completed-id",
                submitted_at="2026-06-29T00:00:00Z",
                status=MacosNotarizeStatus.COMPLETED,
                app_bundle_asset="HumanitecAgent-macos-x64-deadbeef.app-bundle.zip",
                dmg_asset="HumanitecAgent-macos-x64-deadbeef.dmg",
            ),
        },
    )
    updated = mark_superseded(manifest)
    assert updated.platforms["macos-arm64"].status == MacosNotarizeStatus.SUPERSEDED
    assert updated.platforms["macos-x64"].status == MacosNotarizeStatus.COMPLETED


def test_is_followup_active_respects_deadline_and_status() -> None:
    now = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)
    manifest = MacosNotarizeManifest(
        release_tag="humanitec-agent-deadbeef",
        version_sha="deadbeef" * 5,
        deadline_utc="2026-06-29T13:00:00Z",
        platforms={
            "macos-arm64": MacosNotarizePlatformRecord(
                platform="macos-arm64",
                version_sha="deadbeef" * 5,
                submission_id="pending-id",
                submitted_at="2026-06-29T00:00:00Z",
                status=MacosNotarizeStatus.PENDING,
                app_bundle_asset="HumanitecAgent-macos-arm64-deadbeef.app-bundle.zip",
                dmg_asset="HumanitecAgent-macos-arm64-deadbeef.dmg",
            ),
        },
    )
    assert is_followup_active(manifest, now=now) is True
    expired_manifest = manifest.model_copy(
        update={"deadline_utc": "2026-06-29T11:00:00Z"},
    )
    assert is_followup_active(expired_manifest, now=now) is False


def test_update_checksums_for_dmg_replaces_existing_line(tmp_path: Path) -> None:
    checksums_path = tmp_path / "checksums.txt"
    checksums_path.write_text(
        "olddigest  HumanitecAgent-macos-arm64-deadbeef.dmg\n"
        "otherdigest  HumanitecAgent-Setup-deadbeef.msi\n",
        encoding="utf-8",
    )
    dmg_path = tmp_path / "HumanitecAgent-macos-arm64-deadbeef.dmg"
    dmg_path.write_bytes(b"notarized-dmg-bytes")
    update_checksums_for_dmg(
        checksums_path=checksums_path,
        dmg_asset_name="HumanitecAgent-macos-arm64-deadbeef.dmg",
        dmg_path=dmg_path,
    )
    lines = checksums_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("  HumanitecAgent-macos-arm64-deadbeef.dmg")
    assert lines[0].startswith("olddigest") is False
    assert lines[1] == "otherdigest  HumanitecAgent-Setup-deadbeef.msi"


def test_manifest_filename_uses_short_sha() -> None:
    version_sha = "c38f05eba2528021240ea9f3fface4299e4d30b2"
    assert macos_notarize_manifest_filename(version_sha) == "humanitec-agent-macos-notarize-c38f05e.json"


def test_write_manifest_roundtrip(tmp_path: Path) -> None:
    manifest = MacosNotarizeManifest(
        release_tag="humanitec-agent-c38f05e",
        version_sha="c38f05eba2528021240ea9f3fface4299e4d30b2",
        deadline_utc=(datetime.now(tz=UTC) + timedelta(hours=48)).replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
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
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored = MacosNotarizeManifest.model_validate(payload)
    assert restored.platforms["macos-arm64"].submission_id == "903659f6-49e1-42d3-a507-951d750d97e2"


def test_build_fragment_for_submit() -> None:
    distro = load_default_distro_config()
    fragment = build_fragment_for_submit(
        platform="macos-arm64",
        version_sha="c38f05eba2528021240ea9f3fface4299e4d30b2",
        submission_id="903659f6-49e1-42d3-a507-951d750d97e2",
        distro=distro,
    )
    assert fragment.status == MacosNotarizeStatus.PENDING
    assert fragment.submission_id == "903659f6-49e1-42d3-a507-951d750d97e2"
    MacosNotarizeFragment.model_validate(fragment.model_dump(mode="json"))
