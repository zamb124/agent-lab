"""Provision MCPCatalogEntry → MCPServerConfig per company."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from apps.flows.config import get_settings
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.mcp import MCPServerConfig, MCPServerSource, MCPTransportType
from apps.flows.src.models.mcp_catalog import MCPCatalogEntry, MCPCatalogVerifyStatus
from apps.flows.src.services.mcp_catalog_ids import server_id_from_catalog_id
from apps.flows.src.services.mcp_sync import sync_mcp_server_tools
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class MCPCatalogProvisionStats:
    added: int
    updated: int
    skipped_locked: int
    deprecated: int
    sync_ok: int
    sync_failed: int


def _catalog_entry_is_provisionable(entry: MCPCatalogEntry, auto_provision: str) -> bool:
    if auto_provision == "disabled":
        return False
    if entry.is_deprecated:
        return False
    if entry.verify_status not in (
        MCPCatalogVerifyStatus.VERIFIED,
        MCPCatalogVerifyStatus.AUTH_REQUIRED,
    ):
        return False
    if auto_provision == "approved_only":
        return entry.platform_approved
    if auto_provision == "all_verified":
        return True
    raise ValueError(f"Unknown mcp_catalog.auto_provision: {auto_provision!r}")


def catalog_entry_to_server_config(entry: MCPCatalogEntry) -> MCPServerConfig:
    server_id = server_id_from_catalog_id(entry.catalog_id)
    is_active = entry.verify_status != MCPCatalogVerifyStatus.UNREACHABLE
    return MCPServerConfig(
        server_id=server_id,
        name=entry.title,
        url=entry.upstream_url,
        transport_type=MCPTransportType(entry.transport_type),
        headers=dict(entry.auth_template),
        is_active=is_active,
        description=entry.description,
        source=MCPServerSource.CATALOG,
        catalog_id=entry.catalog_id,
        catalog_snapshot_hash=entry.catalog_snapshot_hash,
        override_locked=False,
        override_locked_at=None,
        override_locked_by_user_id=None,
    )


def apply_catalog_entry_to_server(
    *,
    server: MCPServerConfig,
    entry: MCPCatalogEntry,
) -> MCPServerConfig:
    if server.source != MCPServerSource.CATALOG:
        raise ValueError(f"reset_catalog_defaults requires source=catalog, got {server.source.value}")
    if server.catalog_id != entry.catalog_id:
        raise ValueError(
            f"catalog_id mismatch: server={server.catalog_id!r} entry={entry.catalog_id!r}"
        )
    return catalog_entry_to_server_config(entry)


async def provision_mcp_catalog_for_company(
    *,
    container: FlowRuntimeContainer,
) -> MCPCatalogProvisionStats:
    settings = get_settings()
    auto_provision = settings.mcp_catalog.auto_provision
    if auto_provision == "disabled":
        return MCPCatalogProvisionStats(
            added=0,
            updated=0,
            skipped_locked=0,
            deprecated=0,
            sync_ok=0,
            sync_failed=0,
        )

    entries = await container.mcp_catalog_repository.list_provision_candidates(limit=20_000)
    existing_servers = await container.mcp_server_repository.list(limit=5000)
    existing_by_catalog_id: dict[str, MCPServerConfig] = {}
    for server in existing_servers:
        if server.catalog_id is not None:
            existing_by_catalog_id[server.catalog_id] = server

    added = 0
    updated = 0
    skipped_locked = 0
    deprecated = 0
    sync_ok = 0
    sync_failed = 0
    provisionable_ids: set[str] = set()

    for entry in entries:
        if not _catalog_entry_is_provisionable(entry, auto_provision):
            continue
        provisionable_ids.add(entry.catalog_id)
        desired = catalog_entry_to_server_config(entry)
        existing = existing_by_catalog_id.get(entry.catalog_id)
        if existing is None:
            _ = await container.mcp_server_repository.set(desired)
            added += 1
            try:
                _ = await sync_mcp_server_tools(
                    container=container,
                    server_config=desired,
                )
                sync_ok += 1
            except Exception as exc:
                sync_failed += 1
                logger.warning(
                    "MCP catalog sync failed on add: catalog_id=%s error=%s",
                    entry.catalog_id,
                    exc,
                    exc_info=True,
                )
            continue

        if existing.source != MCPServerSource.CATALOG:
            continue
        if existing.override_locked:
            skipped_locked += 1
            continue

        merged = existing.model_copy(
            update={
                "name": desired.name,
                "url": desired.url,
                "transport_type": desired.transport_type,
                "headers": desired.headers,
                "description": desired.description,
                "is_active": desired.is_active,
                "catalog_snapshot_hash": desired.catalog_snapshot_hash,
            }
        )
        changed = (
            merged.name != existing.name
            or merged.url != existing.url
            or merged.transport_type != existing.transport_type
            or merged.headers != existing.headers
            or merged.description != existing.description
            or merged.is_active != existing.is_active
            or merged.catalog_snapshot_hash != existing.catalog_snapshot_hash
        )
        if not changed:
            continue
        _ = await container.mcp_server_repository.set(merged)
        updated += 1
        try:
            _ = await sync_mcp_server_tools(
                container=container,
                server_config=merged,
            )
            sync_ok += 1
        except Exception as exc:
            sync_failed += 1
            logger.warning(
                "MCP catalog sync failed on update: catalog_id=%s error=%s",
                entry.catalog_id,
                exc,
                exc_info=True,
            )

    for server in existing_servers:
        if server.source != MCPServerSource.CATALOG:
            continue
        if server.catalog_id is None:
            continue
        if server.catalog_id in provisionable_ids:
            continue
        if server.override_locked:
            skipped_locked += 1
            continue
        if not server.is_active:
            continue
        inactive = server.model_copy(update={"is_active": False})
        _ = await container.mcp_server_repository.set(inactive)
        deprecated += 1

    return MCPCatalogProvisionStats(
        added=added,
        updated=updated,
        skipped_locked=skipped_locked,
        deprecated=deprecated,
        sync_ok=sync_ok,
        sync_failed=sync_failed,
    )


async def resync_catalog_tools_for_company(
    *,
    container: FlowRuntimeContainer,
) -> tuple[int, int]:
    servers = await container.mcp_server_repository.list(limit=5000)
    sync_ok = 0
    sync_failed = 0
    for server in servers:
        if server.source != MCPServerSource.CATALOG:
            continue
        if server.override_locked:
            continue
        if not server.is_active:
            continue
        try:
            _ = await sync_mcp_server_tools(
                container=container,
                server_config=server,
            )
            sync_ok += 1
        except Exception as exc:
            sync_failed += 1
            logger.warning(
                "MCP catalog resync failed: server_id=%s error=%s",
                server.server_id,
                exc,
                exc_info=True,
            )
    return sync_ok, sync_failed


def mark_server_override_locked(
    *,
    server: MCPServerConfig,
    user_id: str,
) -> MCPServerConfig:
    locked_at = datetime.now(tz=timezone.utc)
    return server.model_copy(
        update={
            "override_locked": True,
            "override_locked_at": locked_at,
            "override_locked_by_user_id": user_id,
        }
    )


def mcp_server_update_triggers_override(
    *,
    server: MCPServerConfig,
    name: str | None,
    url: str | None,
    transport_type: MCPTransportType | None,
    headers: dict[str, str] | None,
    description: str | None,
    is_active: bool | None,
) -> bool:
    if server.source != MCPServerSource.CATALOG:
        return False
    if name is not None and name != server.name:
        return True
    if url is not None and url != server.url:
        return True
    if transport_type is not None and transport_type != server.transport_type:
        return True
    if headers is not None and headers != server.headers:
        return True
    if description is not None and description != server.description:
        return True
    if is_active is not None and is_active != server.is_active:
        return True
    return False
