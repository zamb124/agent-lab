"""
Async macOS notarization: manifest merge, Apple poll, staple, DMG replace.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from apps.agent.desktop.build_contract import (
    MACOS_PLATFORMS,
    HumanitecDistroConfig,
    artifact_filename,
    load_default_distro_config,
    macos_app_bundle_asset_filename,
    macos_notarize_fragment_filename,
    macos_notarize_manifest_filename,
)

NOTARY_FOLLOWUP_MAX_AGE_SECONDS_DEFAULT = 172_800
MANIFEST_ASSET_NAME_PREFIX = "humanitec-agent-macos-notarize-"
MANIFEST_ASSET_NAME_SUFFIX = ".json"
NOTARY_SUBMISSION_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


class MacosNotarizeStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class MacosNotarizePlatformRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str
    version_sha: str
    submission_id: str
    submitted_at: str
    status: MacosNotarizeStatus
    app_bundle_asset: str
    dmg_asset: str


class MacosNotarizeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_tag: str
    version_sha: str
    deadline_utc: str
    platforms: dict[str, MacosNotarizePlatformRecord] = Field(default_factory=dict)


class MacosNotarizeFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str
    version_sha: str
    submission_id: str
    submitted_at: str
    status: MacosNotarizeStatus
    app_bundle_asset: str
    dmg_asset: str


class NotaryPollResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str
    status: str


class MacosNotarizeFollowupSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_tag: str
    platforms_completed: list[str] = Field(default_factory=list)
    platforms_pending: list[str] = Field(default_factory=list)
    platforms_rejected: list[str] = Field(default_factory=list)
    platforms_expired: list[str] = Field(default_factory=list)
    platforms_superseded: list[str] = Field(default_factory=list)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _followup_max_age_seconds() -> int:
    raw_value = os.environ.get("NOTARY_FOLLOWUP_MAX_AGE_SECONDS")
    if raw_value is None or not raw_value.strip():
        return NOTARY_FOLLOWUP_MAX_AGE_SECONDS_DEFAULT
    return int(raw_value.strip())


def _parse_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _now_utc_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_platform_record_from_fragment(fragment: MacosNotarizeFragment) -> MacosNotarizePlatformRecord:
    return MacosNotarizePlatformRecord.model_validate(fragment.model_dump())


def build_fragment_for_submit(
    *,
    platform: str,
    version_sha: str,
    submission_id: str,
    distro: HumanitecDistroConfig,
) -> MacosNotarizeFragment:
    if platform not in MACOS_PLATFORMS:
        raise ValueError(f"Unsupported macOS platform: {platform!r}")
    submitted_at = _now_utc_iso()
    return MacosNotarizeFragment(
        platform=platform,
        version_sha=version_sha,
        submission_id=submission_id,
        submitted_at=submitted_at,
        status=MacosNotarizeStatus.PENDING,
        app_bundle_asset=macos_app_bundle_asset_filename(platform, version_sha, distro.bundle_name),
        dmg_asset=artifact_filename(platform, version_sha, distro.bundle_name),
    )


def normalize_submission_id(raw: str) -> str:
    stripped = raw.strip()
    if not stripped:
        raise ValueError("submission_id is required")
    matches = NOTARY_SUBMISSION_ID_PATTERN.findall(stripped)
    if not matches:
        raise ValueError(f"submission_id does not contain a notary UUID: {raw!r}")
    return str(matches[-1]).lower()


def load_fragment(path: Path) -> MacosNotarizeFragment:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fragment = MacosNotarizeFragment.model_validate(payload)
    normalized_submission_id = normalize_submission_id(fragment.submission_id)
    if normalized_submission_id == fragment.submission_id:
        return fragment
    return fragment.model_copy(update={"submission_id": normalized_submission_id})


def load_manifest(path: Path) -> MacosNotarizeManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = MacosNotarizeManifest.model_validate(payload)
    updated_platforms: dict[str, MacosNotarizePlatformRecord] = {}
    changed = False
    for platform_name, record in manifest.platforms.items():
        normalized_submission_id = normalize_submission_id(record.submission_id)
        if normalized_submission_id != record.submission_id:
            updated_platforms[platform_name] = record.model_copy(
                update={"submission_id": normalized_submission_id}
            )
            changed = True
        else:
            updated_platforms[platform_name] = record
    if changed:
        return manifest.model_copy(update={"platforms": updated_platforms})
    return manifest


def write_manifest(path: Path, manifest: MacosNotarizeManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def merge_platform_fragments(
    *,
    release_tag: str,
    version_sha: str,
    dist_dir: Path,
    distro: HumanitecDistroConfig | None = None,
) -> MacosNotarizeManifest:
    resolved_distro = distro if distro is not None else load_default_distro_config()
    deadline = datetime.now(tz=UTC) + timedelta(seconds=_followup_max_age_seconds())
    deadline_utc = deadline.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    platforms: dict[str, MacosNotarizePlatformRecord] = {}
    for platform_name in MACOS_PLATFORMS:
        fragment_name = macos_notarize_fragment_filename(
            platform_name,
            version_sha,
            resolved_distro.bundle_name,
        )
        fragment_path = dist_dir / fragment_name
        if not fragment_path.is_file():
            continue
        fragment = load_fragment(fragment_path)
        platforms[platform_name] = build_platform_record_from_fragment(fragment)
    if not platforms:
        raise FileNotFoundError(
            f"No macOS notarize fragments found under {dist_dir} for version {version_sha!r}"
        )
    return MacosNotarizeManifest(
        release_tag=release_tag,
        version_sha=version_sha,
        deadline_utc=deadline_utc,
        platforms=platforms,
    )


def mark_superseded(manifest: MacosNotarizeManifest) -> MacosNotarizeManifest:
    updated_platforms: dict[str, MacosNotarizePlatformRecord] = {}
    for platform_name, record in manifest.platforms.items():
        if record.status == MacosNotarizeStatus.PENDING:
            updated_platforms[platform_name] = record.model_copy(
                update={"status": MacosNotarizeStatus.SUPERSEDED}
            )
        else:
            updated_platforms[platform_name] = record
    return manifest.model_copy(update={"platforms": updated_platforms})


def is_followup_active(manifest: MacosNotarizeManifest, *, now: datetime | None = None) -> bool:
    current = now if now is not None else datetime.now(tz=UTC)
    deadline = _parse_iso8601(manifest.deadline_utc)
    if current >= deadline:
        return False
    for record in manifest.platforms.values():
        if record.status == MacosNotarizeStatus.PENDING:
            return True
    return False


def poll_submission_once(submission_id: str) -> NotaryPollResult:
    normalized_submission_id = normalize_submission_id(submission_id)
    apple_id = _require_env("APPLE_ID")
    apple_id_password = _require_env("APPLE_ID_PASSWORD")
    apple_team_id = _require_env("APPLE_TEAM_ID")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as temp_file:
        info_json_path = Path(temp_file.name)
    try:
        command = [
            "xcrun",
            "notarytool",
            "info",
            normalized_submission_id,
            "--apple-id",
            apple_id,
            "--password",
            apple_id_password,
            "--team-id",
            apple_team_id,
            "--output-format",
            "json",
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr_text = completed.stderr.strip()
            raise RuntimeError(
                f"notarytool info failed for {normalized_submission_id}: {stderr_text}"
            )
        info_json_path.write_text(completed.stdout, encoding="utf-8")
        payload = json.loads(info_json_path.read_text(encoding="utf-8"))
        status_raw = payload.get("status")
        if not isinstance(status_raw, str) or not status_raw:
            raise ValueError(
                f"notarytool info missing status for {normalized_submission_id}"
            )
        return NotaryPollResult(submission_id=normalized_submission_id, status=status_raw)
    finally:
        info_json_path.unlink(missing_ok=True)


def fetch_notary_submission_log(submission_id: str) -> str:
    normalized_submission_id = normalize_submission_id(submission_id)
    apple_id = _require_env("APPLE_ID")
    apple_id_password = _require_env("APPLE_ID_PASSWORD")
    apple_team_id = _require_env("APPLE_TEAM_ID")
    command = [
        "xcrun",
        "notarytool",
        "log",
        normalized_submission_id,
        "--apple-id",
        apple_id,
        "--password",
        apple_id_password,
        "--team-id",
        apple_team_id,
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        raise RuntimeError(f"notarytool log failed for {normalized_submission_id}: {stderr_text}")
    return completed.stdout


def staple_app_bundle(app_bundle_path: Path) -> None:
    if not app_bundle_path.is_dir():
        raise FileNotFoundError(f"App bundle missing for stapler: {app_bundle_path}")
    command = ["xcrun", "stapler", "staple", str(app_bundle_path)]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        stdout_text = completed.stdout.strip()
        raise RuntimeError(
            f"stapler failed for {app_bundle_path}: {stderr_text} {stdout_text}"
        )


def rebuild_dmg(*, app_bundle_path: Path, dmg_path: Path, volume_name: str) -> None:
    if shutil.which("hdiutil") is None:
        raise RuntimeError("hdiutil is required to rebuild macOS DMG")
    dmg_path.parent.mkdir(parents=True, exist_ok=True)
    if dmg_path.is_file():
        dmg_path.unlink()
    staging_dir = Path(tempfile.mkdtemp(prefix="humanitec-dmg-staging-"))
    try:
        shutil.copytree(app_bundle_path, staging_dir / app_bundle_path.name)
        applications_link = staging_dir / "Applications"
        applications_link.symlink_to("/Applications")
        command = [
            "hdiutil",
            "create",
            "-volname",
            volume_name,
            "-srcfolder",
            str(staging_dir),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            stderr_text = completed.stderr.strip()
            raise RuntimeError(f"hdiutil create failed: {stderr_text}")
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def update_checksums_for_dmg(
    *,
    checksums_path: Path,
    dmg_asset_name: str,
    dmg_path: Path,
) -> None:
    digest = sha256_file(dmg_path)
    lines: list[str] = []
    if checksums_path.is_file():
        lines = checksums_path.read_text(encoding="utf-8").splitlines()
    replaced = False
    updated_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            updated_lines.append(stripped)
            continue
        existing_digest, asset_name = parts
        if asset_name == dmg_asset_name:
            updated_lines.append(f"{digest}  {asset_name}")
            replaced = True
        else:
            updated_lines.append(f"{existing_digest}  {asset_name}")
    if not replaced:
        updated_lines.append(f"{digest}  {dmg_asset_name}")
    checksums_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def extract_app_bundle_from_zip(
    *,
    app_bundle_zip_path: Path,
    extract_dir: Path,
    bundle_name: str,
) -> Path:
    if shutil.which("ditto") is None:
        raise RuntimeError("ditto is required to extract macOS app bundle zip")
    extract_dir.mkdir(parents=True, exist_ok=True)
    command = ["ditto", "-x", "-k", str(app_bundle_zip_path), str(extract_dir)]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        raise RuntimeError(f"ditto extract failed: {stderr_text}")
    app_bundle_path = extract_dir / f"{bundle_name}.app"
    if not app_bundle_path.is_dir():
        matches = list(extract_dir.rglob(f"{bundle_name}.app"))
        if not matches:
            raise FileNotFoundError(
                f"{bundle_name}.app not found after extracting {app_bundle_zip_path}"
            )
        app_bundle_path = matches[0]
    return app_bundle_path


def _github_repo_slug(repo: str) -> str:
    stripped = repo.strip()
    if not stripped:
        raise ValueError("repo is required")
    return stripped


def _run_gh_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    command = ["gh", *args]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    return completed


def list_release_asset_names(*, repo: str, release_tag: str) -> list[str]:
    repo_slug = _github_repo_slug(repo)
    view_command = [
        "release",
        "view",
        release_tag,
        "--repo",
        repo_slug,
        "--json",
        "assets",
    ]
    completed = _run_gh_command(view_command)
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        raise RuntimeError(f"gh release view failed for {release_tag}: {stderr_text}")
    payload = json.loads(completed.stdout)
    assets_raw = payload.get("assets")
    if not isinstance(assets_raw, list):
        raise ValueError(f"release {release_tag} assets payload invalid")
    asset_names: list[str] = []
    for asset_item in assets_raw:
        if not isinstance(asset_item, dict):
            continue
        asset_name = asset_item.get("name")
        if isinstance(asset_name, str) and asset_name:
            asset_names.append(asset_name)
    return asset_names


def resolve_manifest_asset_name(
    *,
    repo: str,
    release_tag: str,
    version_sha: str | None = None,
) -> str:
    asset_names = list_release_asset_names(repo=repo, release_tag=release_tag)
    manifest_assets = [
        asset_name
        for asset_name in asset_names
        if asset_name.startswith(MANIFEST_ASSET_NAME_PREFIX)
        and asset_name.endswith(MANIFEST_ASSET_NAME_SUFFIX)
    ]
    if not manifest_assets:
        raise FileNotFoundError(
            f"No macOS notarize manifest asset on release {release_tag!r}"
        )
    if version_sha is not None:
        expected_name = macos_notarize_manifest_filename(version_sha)
        if expected_name in manifest_assets:
            return expected_name
        raise FileNotFoundError(
            f"Manifest asset {expected_name!r} not found on release {release_tag!r}; "
            f"available: {', '.join(manifest_assets)}"
        )
    if len(manifest_assets) == 1:
        return manifest_assets[0]
    raise ValueError(
        f"Multiple macOS notarize manifest assets on release {release_tag!r}: "
        f"{', '.join(manifest_assets)}"
    )


def resolve_release_version_sha(*, repo: str, release_tag: str) -> str:
    repo_slug = _github_repo_slug(repo)
    view_command = [
        "release",
        "view",
        release_tag,
        "--repo",
        repo_slug,
        "--json",
        "targetCommitish",
    ]
    completed = _run_gh_command(view_command)
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        raise RuntimeError(f"gh release view failed for {release_tag}: {stderr_text}")
    payload = json.loads(completed.stdout)
    target_commitish = payload.get("targetCommitish")
    if not isinstance(target_commitish, str) or not target_commitish:
        raise ValueError(f"release {release_tag} missing targetCommitish")
    return target_commitish


def download_release_asset(
    *,
    repo: str,
    release_tag: str,
    asset_name: str,
    destination: Path,
) -> None:
    repo_slug = _github_repo_slug(repo)
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "release",
        "download",
        release_tag,
        "--repo",
        repo_slug,
        "--pattern",
        asset_name,
        "--dir",
        str(destination.parent),
        "--clobber",
    ]
    completed = _run_gh_command(command)
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        raise RuntimeError(
            f"gh release download failed for {asset_name} on {release_tag}: {stderr_text}"
        )
    downloaded_path = destination.parent / asset_name
    if not downloaded_path.is_file():
        raise FileNotFoundError(f"Downloaded asset missing: {downloaded_path}")
    if downloaded_path != destination:
        shutil.move(str(downloaded_path), str(destination))


def upload_release_assets(
    *,
    repo: str,
    release_tag: str,
    asset_paths: list[Path],
) -> None:
    repo_slug = _github_repo_slug(repo)
    path_strings = [str(path) for path in asset_paths]
    command = [
        "release",
        "upload",
        release_tag,
        "--repo",
        repo_slug,
        "--clobber",
        *path_strings,
    ]
    completed = _run_gh_command(command)
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        raise RuntimeError(f"gh release upload failed for {release_tag}: {stderr_text}")


def delete_release_assets(
    *,
    repo: str,
    release_tag: str,
    asset_names: list[str],
) -> None:
    repo_slug = _github_repo_slug(repo)
    view_command = [
        "release",
        "view",
        release_tag,
        "--repo",
        repo_slug,
        "--json",
        "assets",
    ]
    completed = _run_gh_command(view_command)
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        raise RuntimeError(f"gh release view failed for {release_tag}: {stderr_text}")
    payload = json.loads(completed.stdout)
    assets_raw = payload.get("assets")
    if not isinstance(assets_raw, list):
        raise ValueError(f"release {release_tag} assets payload invalid")
    asset_ids_by_name: dict[str, int] = {}
    for asset_item in assets_raw:
        if not isinstance(asset_item, dict):
            continue
        asset_name = asset_item.get("name")
        asset_id = asset_item.get("id")
        if isinstance(asset_name, str) and isinstance(asset_id, int):
            asset_ids_by_name[asset_name] = asset_id
    for asset_name in asset_names:
        asset_id = asset_ids_by_name.get(asset_name)
        if asset_id is None:
            continue
        delete_command = [
            "api",
            f"repos/{repo_slug}/releases/assets/{asset_id}",
            "-X",
            "DELETE",
        ]
        delete_completed = _run_gh_command(delete_command)
        if delete_completed.returncode != 0:
            stderr_text = delete_completed.stderr.strip()
            raise RuntimeError(
                f"gh api delete asset failed for {asset_name}: {stderr_text}"
            )


def download_manifest_from_release(
    *,
    repo: str,
    release_tag: str,
    work_dir: Path,
    version_sha: str | None = None,
) -> MacosNotarizeManifest:
    manifest_name = resolve_manifest_asset_name(
        repo=repo,
        release_tag=release_tag,
        version_sha=version_sha,
    )
    manifest_path = work_dir / manifest_name
    download_release_asset(
        repo=repo,
        release_tag=release_tag,
        asset_name=manifest_name,
        destination=manifest_path,
    )
    return load_manifest(manifest_path)


def _process_pending_platform(
    *,
    manifest: MacosNotarizeManifest,
    platform_name: str,
    record: MacosNotarizePlatformRecord,
    repo: str,
    work_dir: Path,
    distro: HumanitecDistroConfig,
    now: datetime,
) -> MacosNotarizePlatformRecord:
    deadline = _parse_iso8601(manifest.deadline_utc)
    if now >= deadline:
        return record.model_copy(update={"status": MacosNotarizeStatus.EXPIRED})

    poll_result = poll_submission_once(record.submission_id)
    if poll_result.status == "In Progress":
        return record
    if poll_result.status in {"Invalid", "Rejected"}:
        _ = fetch_notary_submission_log(record.submission_id)
        return record.model_copy(update={"status": MacosNotarizeStatus.REJECTED})
    if poll_result.status != "Accepted":
        raise ValueError(
            f"Unexpected notary status {poll_result.status!r} for {record.submission_id}"
        )

    platform_work_dir = work_dir / platform_name
    platform_work_dir.mkdir(parents=True, exist_ok=True)
    app_bundle_zip_path = platform_work_dir / record.app_bundle_asset
    dmg_path = platform_work_dir / record.dmg_asset
    download_release_asset(
        repo=repo,
        release_tag=manifest.release_tag,
        asset_name=record.app_bundle_asset,
        destination=app_bundle_zip_path,
    )
    extract_dir = platform_work_dir / "extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    app_bundle_path = extract_app_bundle_from_zip(
        app_bundle_zip_path=app_bundle_zip_path,
        extract_dir=extract_dir,
        bundle_name=distro.bundle_name,
    )
    staple_app_bundle(app_bundle_path)
    rebuild_dmg(
        app_bundle_path=app_bundle_path,
        dmg_path=dmg_path,
        volume_name=distro.bundle_name,
    )
    checksums_path = platform_work_dir / "checksums.txt"
    download_release_asset(
        repo=repo,
        release_tag=manifest.release_tag,
        asset_name="checksums.txt",
        destination=checksums_path,
    )
    update_checksums_for_dmg(
        checksums_path=checksums_path,
        dmg_asset_name=record.dmg_asset,
        dmg_path=dmg_path,
    )
    upload_release_assets(
        repo=repo,
        release_tag=manifest.release_tag,
        asset_paths=[dmg_path, checksums_path],
    )
    delete_release_assets(
        repo=repo,
        release_tag=manifest.release_tag,
        asset_names=[record.app_bundle_asset],
    )
    return record.model_copy(update={"status": MacosNotarizeStatus.COMPLETED})


def supersede_release_manifest(
    *,
    repo: str,
    release_tag: str,
    work_dir: Path,
    version_sha: str | None = None,
) -> MacosNotarizeManifest:
    manifest = download_manifest_from_release(
        repo=repo,
        release_tag=release_tag,
        work_dir=work_dir,
        version_sha=version_sha,
    )
    updated_manifest = mark_superseded(manifest)
    manifest_path = work_dir / macos_notarize_manifest_filename(manifest.version_sha)
    write_manifest(manifest_path, updated_manifest)
    upload_release_assets(
        repo=repo,
        release_tag=release_tag,
        asset_paths=[manifest_path],
    )
    return updated_manifest


def followup_release(
    *,
    repo: str,
    release_tag: str,
    version_sha: str | None = None,
    work_dir: Path | None = None,
) -> MacosNotarizeFollowupSummary:
    resolved_work_dir = work_dir if work_dir is not None else Path(tempfile.mkdtemp(prefix="humanitec-notarize-"))
    resolved_work_dir.mkdir(parents=True, exist_ok=True)

    manifest = download_manifest_from_release(
        repo=repo,
        release_tag=release_tag,
        work_dir=resolved_work_dir,
        version_sha=version_sha,
    )
    version_sha = manifest.version_sha
    distro = load_default_distro_config()
    now = datetime.now(tz=UTC)
    updated_platforms: dict[str, MacosNotarizePlatformRecord] = {}
    summary = MacosNotarizeFollowupSummary(release_tag=release_tag)

    for platform_name, record in manifest.platforms.items():
        if record.status == MacosNotarizeStatus.SUPERSEDED:
            summary.platforms_superseded.append(platform_name)
            updated_platforms[platform_name] = record
            continue
        if record.status == MacosNotarizeStatus.COMPLETED:
            summary.platforms_completed.append(platform_name)
            updated_platforms[platform_name] = record
            continue
        if record.status == MacosNotarizeStatus.REJECTED:
            summary.platforms_rejected.append(platform_name)
            updated_platforms[platform_name] = record
            continue
        if record.status == MacosNotarizeStatus.EXPIRED:
            summary.platforms_expired.append(platform_name)
            updated_platforms[platform_name] = record
            continue
        if record.status != MacosNotarizeStatus.PENDING:
            raise ValueError(f"Unexpected platform status {record.status!r}")

        updated_record = _process_pending_platform(
            manifest=manifest,
            platform_name=platform_name,
            record=record,
            repo=repo,
            work_dir=resolved_work_dir,
            distro=distro,
            now=now,
        )
        updated_platforms[platform_name] = updated_record
        if updated_record.status == MacosNotarizeStatus.COMPLETED:
            summary.platforms_completed.append(platform_name)
        elif updated_record.status == MacosNotarizeStatus.REJECTED:
            summary.platforms_rejected.append(platform_name)
        elif updated_record.status == MacosNotarizeStatus.EXPIRED:
            summary.platforms_expired.append(platform_name)
        else:
            summary.platforms_pending.append(platform_name)

    updated_manifest = manifest.model_copy(update={"platforms": updated_platforms})
    manifest_path = resolved_work_dir / macos_notarize_manifest_filename(version_sha)
    write_manifest(manifest_path, updated_manifest)

    all_completed = all(
        record.status == MacosNotarizeStatus.COMPLETED
        for record in updated_platforms.values()
    )
    all_terminal = all(
        record.status
        in {
            MacosNotarizeStatus.COMPLETED,
            MacosNotarizeStatus.REJECTED,
            MacosNotarizeStatus.EXPIRED,
            MacosNotarizeStatus.SUPERSEDED,
        }
        for record in updated_platforms.values()
    )
    if all_completed or all_terminal:
        delete_release_assets(
            repo=repo,
            release_tag=release_tag,
            asset_names=[manifest_path.name],
        )
    else:
        upload_release_assets(
            repo=repo,
            release_tag=manifest.release_tag,
            asset_paths=[manifest_path],
        )

    if summary.platforms_rejected:
        rejected_ids = [
            updated_platforms[platform_name].submission_id
            for platform_name in summary.platforms_rejected
        ]
        raise RuntimeError(
            f"macOS notarization rejected for {release_tag}: {', '.join(rejected_ids)}"
        )
    return summary


def discover_pending_release_tags(*, repo: str) -> list[str]:
    repo_slug = _github_repo_slug(repo)
    command = [
        "release",
        "list",
        "--repo",
        repo_slug,
        "--limit",
        "20",
        "--json",
        "tagName,isDraft,isPrerelease",
    ]
    completed = _run_gh_command(command)
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        raise RuntimeError(f"gh release list failed: {stderr_text}")
    releases_raw = json.loads(completed.stdout)
    if not isinstance(releases_raw, list):
        raise ValueError("gh release list returned unexpected payload")
    pending_tags: list[str] = []
    for release_item in releases_raw:
        if not isinstance(release_item, dict):
            continue
        tag_name = release_item.get("tagName")
        is_draft = release_item.get("isDraft")
        if not isinstance(tag_name, str) or not tag_name:
            continue
        if is_draft is True:
            continue
        if not tag_name.startswith("humanitec-agent-"):
            continue
        try:
            release_work_dir = Path(tempfile.mkdtemp(prefix="humanitec-notarize-discover-"))
            manifest = download_manifest_from_release(
                repo=repo,
                release_tag=tag_name,
                work_dir=release_work_dir,
            )
        except (FileNotFoundError, RuntimeError, ValueError):
            continue
        if is_followup_active(manifest):
            pending_tags.append(tag_name)
    return pending_tags


def fetch_release_body_note(*, repo: str, release_tag: str) -> str:
    repo_slug = _github_repo_slug(repo)
    command = ["release", "view", release_tag, "--repo", repo_slug, "--json", "body"]
    completed = _run_gh_command(command)
    if completed.returncode != 0:
        stderr_text = completed.stderr.strip()
        raise RuntimeError(f"gh release view failed for {release_tag}: {stderr_text}")
    payload = json.loads(completed.stdout)
    body = payload.get("body")
    if isinstance(body, str):
        return body
    return ""


def http_download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)
