"""Seed глобального MCP branding из git-бандла (S3 + MCPServerBrandingRepository)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from apps.flows.config import get_settings
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.mcp_branding import MCPBrandingManifestFilePayload
from apps.flows.src.services.mcp_branding_aliases import (
    BRANDING_SERVER_ID_ALIASES,
    resolve_branding_server_id,
)
from apps.flows.src.services.mcp_defaults import build_default_mcp_servers
from core.files.create_spec import FileCreateSpec
from core.logging import get_logger

logger = get_logger(__name__)

_SERVER_ID_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,63}$")

_CONTENT_TYPE_BY_SUFFIX: dict[str, str] = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@dataclass(frozen=True)
class MCPBrandingManifestEntry:
    server_id: str
    file: str
    source: str
    license: str


@dataclass(frozen=True)
class MCPBrandingManifest:
    bundle_dir: Path
    default_icon: Path
    entries: dict[str, MCPBrandingManifestEntry]


@dataclass(frozen=True)
class MCPBrandingSeedStats:
    targets: int
    seeded: int
    skipped_existing: int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _validate_server_id(server_id: str) -> str:
    stripped = server_id.strip()
    if not _SERVER_ID_PATTERN.match(stripped):
        raise ValueError(f"server_id {stripped!r} is not a valid MCP slug")
    return stripped


def _content_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    content_type = _CONTENT_TYPE_BY_SUFFIX.get(suffix)
    if content_type is None:
        raise ValueError(f"Unsupported icon extension for {path}")
    return content_type


def _platform_auxiliary_spec(*, is_public: bool) -> FileCreateSpec:
    return FileCreateSpec.model_validate(
        {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
            "post_create": {"is_public": is_public},
        }
    )


def load_mcp_branding_manifest(*, manifest_path: Path | None = None) -> MCPBrandingManifest:
    settings = get_settings()
    resolved_manifest_path = manifest_path if manifest_path is not None else _repo_root() / settings.mcp_branding.bundle_path
    if not resolved_manifest_path.is_file():
        raise FileNotFoundError(f"MCP branding manifest not found: {resolved_manifest_path}")

    bundle_dir = resolved_manifest_path.parent
    raw_text = resolved_manifest_path.read_text(encoding="utf-8")
    raw_payload: object = cast(object, yaml.safe_load(raw_text))
    manifest_payload = MCPBrandingManifestFilePayload.model_validate(raw_payload)

    default_icon = bundle_dir / manifest_payload.default_icon.strip()
    if not default_icon.is_file():
        raise FileNotFoundError(f"MCP branding default_icon not found: {default_icon}")

    entries: dict[str, MCPBrandingManifestEntry] = {}
    for row in manifest_payload.entries:
        server_id = _validate_server_id(row.server_id)
        icon_path = bundle_dir / row.file.strip()
        if not icon_path.is_file():
            raise FileNotFoundError(f"MCP branding icon not found for {server_id}: {icon_path}")

        entries[server_id] = MCPBrandingManifestEntry(
            server_id=server_id,
            file=row.file.strip(),
            source=row.source.strip(),
            license=row.license.strip(),
        )

    return MCPBrandingManifest(
        bundle_dir=bundle_dir,
        default_icon=default_icon,
        entries=entries,
    )


async def _collect_seed_targets(
    container: FlowRuntimeContainer,
    *,
    manifest: MCPBrandingManifest,
    server_ids: frozenset[str] | None,
) -> list[str]:
    platform_ids = [server.server_id for server in build_default_mcp_servers()]
    catalog_entries = await container.mcp_catalog_repository.list(limit=10_000)
    catalog_ids = [entry.catalog_id for entry in catalog_entries]
    manifest_ids = list(manifest.entries.keys())
    alias_ids = list(BRANDING_SERVER_ID_ALIASES.keys())

    merged: list[str] = []
    seen: set[str] = set()
    for server_id in [*platform_ids, *catalog_ids, *manifest_ids, *alias_ids]:
        normalized = _validate_server_id(server_id)
        if normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)

    if server_ids is not None:
        filtered: list[str] = []
        for server_id in merged:
            if server_id in server_ids:
                filtered.append(server_id)
        return filtered

    return merged


async def _upload_icon_file(
    container: FlowRuntimeContainer,
    *,
    icon_path: Path,
    original_name: str,
) -> str:
    payload = icon_path.read_bytes()
    content_type = _content_type_for_path(icon_path)
    record = await container.files_service.create(
        _platform_auxiliary_spec(is_public=True),
        payload,
        original_name=original_name,
        content_type=content_type,
    )
    return record.file_id


async def seed_mcp_branding_from_bundle(
    container: FlowRuntimeContainer,
    *,
    force: bool = False,
    server_ids: frozenset[str] | None = None,
    dry_run: bool = False,
    manifest_path: Path | None = None,
) -> MCPBrandingSeedStats:
    manifest = load_mcp_branding_manifest(manifest_path=manifest_path)
    targets = await _collect_seed_targets(container, manifest=manifest, server_ids=server_ids)

    seeded = 0
    skipped_existing = 0
    generic_file_id: str | None = None

    for server_id in targets:
        existing_icon_url = await container.mcp_branding_service.get_icon_url(server_id)
        if existing_icon_url is not None and not force:
            skipped_existing += 1
            continue

        manifest_entry = manifest.entries.get(server_id)
        if manifest_entry is None:
            canonical_server_id = resolve_branding_server_id(server_id)
            if canonical_server_id != server_id:
                manifest_entry = manifest.entries.get(canonical_server_id)
        if manifest_entry is not None:
            icon_path = manifest.bundle_dir / manifest_entry.file
        else:
            icon_path = manifest.default_icon

        if dry_run:
            seeded += 1
            continue

        if manifest_entry is None:
            if generic_file_id is None:
                generic_file_id = await _upload_icon_file(
                    container,
                    icon_path=icon_path,
                    original_name="_generic.svg",
                )
            icon_file_id = generic_file_id
        else:
            icon_file_id = await _upload_icon_file(
                container,
                icon_path=icon_path,
                original_name=icon_path.name,
            )

        _ = await container.mcp_branding_service.upsert_branding(server_id, icon_file_id)
        seeded += 1

    stats = MCPBrandingSeedStats(
        targets=len(targets),
        seeded=seeded,
        skipped_existing=skipped_existing,
    )
    logger.info(
        "MCP branding seed done: targets=%s seeded=%s skipped_existing=%s dry_run=%s",
        stats.targets,
        stats.seeded,
        stats.skipped_existing,
        dry_run,
    )
    return stats
