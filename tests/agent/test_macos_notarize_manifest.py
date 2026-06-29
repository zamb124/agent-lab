"""Unit-тесты macOS async notarization manifest."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

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
    discover_pending_release_tags,
    is_followup_active,
    mark_superseded,
    merge_platform_fragments,
    normalize_submission_id,
    resolve_manifest_asset_name,
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
            submission_id=(
                "903659f6-49e1-42d3-a507-951d750d97e2"
                if platform_name == "macos-arm64"
                else "70f95b5c-a515-4588-8f02-1e314eb6d0cb"
            ),
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


def test_normalize_submission_id_accepts_clean_uuid() -> None:
    submission_id = "2a6e1f41-3384-430e-8840-764292f03d9c"
    assert normalize_submission_id(submission_id) == submission_id


def test_normalize_submission_id_extracts_uuid_from_log_blob() -> None:
    corrupt = (
        "Verifying signature before notarization\n"
        "Notarization submission id: 2a6e1f41-3384-430e-8840-764292f03d9c\n"
        "2a6e1f41-3384-430e-8840-764292f03d9c"
    )
    assert normalize_submission_id(corrupt) == "2a6e1f41-3384-430e-8840-764292f03d9c"


def test_load_manifest_normalizes_corrupt_submission_id(tmp_path: Path) -> None:
    from apps.agent.desktop.macos_notarize import load_manifest

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "release_tag": "humanitec-agent-d719594",
                "version_sha": "d71959406b132cffa0f6cc6087c9c8161bd6cfd7",
                "deadline_utc": "2099-01-01T00:00:00Z",
                "platforms": {
                    "macos-arm64": {
                        "platform": "macos-arm64",
                        "version_sha": "d71959406b132cffa0f6cc6087c9c8161bd6cfd7",
                        "submission_id": (
                            "Submitting app\n"
                            "2a6e1f41-3384-430e-8840-764292f03d9c"
                        ),
                        "submitted_at": "2026-06-29T11:21:23Z",
                        "status": "pending",
                        "app_bundle_asset": "HumanitecAgent-macos-arm64-d719594.app-bundle.zip",
                        "dmg_asset": "HumanitecAgent-macos-arm64-d719594.dmg",
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = load_manifest(manifest_path)
    assert (
        manifest.platforms["macos-arm64"].submission_id
        == "2a6e1f41-3384-430e-8840-764292f03d9c"
    )


def test_resolve_manifest_asset_name_from_release_assets() -> None:
    version_sha = "d71959406b132cffa0f6cc6087c9c8161bd6cfd7"
    assets_payload = json.dumps(
        {
            "assets": [
                {"name": "HumanitecAgent-macos-arm64-d719594.dmg"},
                {"name": "humanitec-agent-macos-notarize-d719594.json"},
            ]
        }
    )

    class Completed:
        returncode = 0
        stdout = assets_payload
        stderr = ""

    with patch(
        "apps.agent.desktop.macos_notarize._run_gh_command",
        return_value=Completed(),
    ):
        asset_name = resolve_manifest_asset_name(
            repo="zamb124/agent-lab",
            release_tag="humanitec-agent-d719594",
        )
    assert asset_name == "humanitec-agent-macos-notarize-d719594.json"
    with patch(
        "apps.agent.desktop.macos_notarize._run_gh_command",
        return_value=Completed(),
    ):
        explicit_name = resolve_manifest_asset_name(
            repo="zamb124/agent-lab",
            release_tag="humanitec-agent-d719594",
            version_sha=version_sha,
        )
    assert explicit_name == "humanitec-agent-macos-notarize-d719594.json"


def test_discover_pending_release_tags_filters_inactive_manifests() -> None:
    active_manifest = MacosNotarizeManifest(
        release_tag="humanitec-agent-d719594",
        version_sha="d71959406b132cffa0f6cc6087c9c8161bd6cfd7",
        deadline_utc="2099-01-01T00:00:00Z",
        platforms={
            "macos-arm64": MacosNotarizePlatformRecord(
                platform="macos-arm64",
                version_sha="d71959406b132cffa0f6cc6087c9c8161bd6cfd7",
                submission_id="2a6e1f41-3384-430e-8840-764292f03d9c",
                submitted_at="2026-06-29T11:21:23Z",
                status=MacosNotarizeStatus.PENDING,
                app_bundle_asset="HumanitecAgent-macos-arm64-d719594.app-bundle.zip",
                dmg_asset="HumanitecAgent-macos-arm64-d719594.dmg",
            ),
        },
    )
    completed_manifest = active_manifest.model_copy(
        update={
            "release_tag": "humanitec-agent-deadbeef",
            "platforms": {
                "macos-arm64": active_manifest.platforms["macos-arm64"].model_copy(
                    update={"status": MacosNotarizeStatus.COMPLETED}
                ),
            },
        }
    )
    releases_payload = json.dumps(
        [
            {"tagName": "humanitec-agent-d719594", "isDraft": False},
            {"tagName": "humanitec-agent-deadbeef", "isDraft": False},
            {"tagName": "humanitec-agent-no-manifest", "isDraft": False},
        ]
    )

    class ListCompleted:
        returncode = 0
        stdout = releases_payload
        stderr = ""

    def download_side_effect(
        *,
        repo: str,
        release_tag: str,
        work_dir: Path,
        version_sha: str | None = None,
    ) -> MacosNotarizeManifest:
        _ = repo
        _ = work_dir
        _ = version_sha
        if release_tag == "humanitec-agent-d719594":
            return active_manifest
        if release_tag == "humanitec-agent-deadbeef":
            return completed_manifest
        raise FileNotFoundError(release_tag)

    with (
        patch(
            "apps.agent.desktop.macos_notarize._run_gh_command",
            return_value=ListCompleted(),
        ),
        patch(
            "apps.agent.desktop.macos_notarize.download_manifest_from_release",
            side_effect=download_side_effect,
        ),
    ):
        pending_tags = discover_pending_release_tags(repo="zamb124/agent-lab")
    assert pending_tags == ["humanitec-agent-d719594"]
