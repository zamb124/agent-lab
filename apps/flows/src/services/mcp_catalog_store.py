"""Opt-in MCP Store: install/uninstall catalog entries per company."""

from __future__ import annotations

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.mcp import MCPServerConfig, MCPServerSource
from apps.flows.src.models.mcp_catalog import MCPCatalogEntry, MCPCatalogVerifyStatus
from apps.flows.src.services.mcp_catalog_ids import server_id_from_catalog_id
from apps.flows.src.services.mcp_catalog_provisioner import catalog_entry_to_server_config
from apps.flows.src.services.mcp_sync import sync_mcp_server_tools
from core.logging import get_logger

logger = get_logger(__name__)

MCPCatalogStoreEntry = tuple[MCPCatalogEntry, bool, bool]


def catalog_entry_is_store_installable(entry: MCPCatalogEntry) -> bool:
    if entry.platform_approved:
        return False
    if entry.is_deprecated:
        return False
    return entry.verify_status in (
        MCPCatalogVerifyStatus.VERIFIED,
        MCPCatalogVerifyStatus.AUTH_REQUIRED,
    )


def catalog_store_entry_matches_search(entry: MCPCatalogEntry, search: str) -> bool:
    query = search.strip().lower()
    if not query:
        return True
    haystack = " ".join(
        part
        for part in (
            entry.catalog_id,
            entry.registry_name,
            entry.title,
            entry.description,
        )
        if part
    ).lower()
    return query in haystack


def catalog_entry_is_search_visible(entry: MCPCatalogEntry, search: str) -> bool:
    if not catalog_store_entry_matches_search(entry, search):
        return False
    if catalog_entry_is_store_installable(entry):
        return True
    return bool(search.strip()) and entry.platform_approved and not entry.is_deprecated


async def list_store_catalog_entries(
    *,
    container: FlowRuntimeContainer,
    search: str,
    limit: int,
    offset: int,
) -> tuple[list[MCPCatalogStoreEntry], int]:
    all_entries = await container.mcp_catalog_repository.list(limit=20_000)
    store_entries = [
        entry
        for entry in all_entries
        if catalog_entry_is_search_visible(entry, search)
    ]
    store_entries.sort(key=lambda entry: entry.title.lower())
    total = len(store_entries)
    page = store_entries[offset : offset + limit]

    existing_servers = await container.mcp_server_repository.list(limit=5000)
    installed_catalog_ids = {
        server.catalog_id
        for server in existing_servers
        if server.source == MCPServerSource.CATALOG and server.catalog_id is not None
    }
    return [
        (
            entry,
            entry.catalog_id in installed_catalog_ids,
            entry.platform_approved and not catalog_entry_is_store_installable(entry),
        )
        for entry in page
    ], total


async def install_catalog_entry_for_company(
    *,
    container: FlowRuntimeContainer,
    catalog_id: str,
) -> MCPServerConfig:
    entry = await container.mcp_catalog_repository.get(catalog_id)
    if entry is None:
        raise ValueError(f"Catalog entry {catalog_id!r} not found")
    if not catalog_entry_is_store_installable(entry):
        raise ValueError(f"Catalog entry {catalog_id!r} is not available in MCP Store")

    server_id = server_id_from_catalog_id(catalog_id)
    existing = await container.mcp_server_repository.get(server_id)
    if existing is not None:
        if (
            existing.source == MCPServerSource.CATALOG
            and existing.catalog_id == catalog_id
        ):
            return existing
        raise ValueError(f"MCP server {server_id!r} already exists with another source")

    server = catalog_entry_to_server_config(
        entry,
        catalog_auto_provisioned=False,
    )
    _ = await container.mcp_server_repository.set(server)
    _ = await sync_mcp_server_tools(container=container, server_config=server)
    logger.info("MCP Store install: catalog_id=%s server_id=%s", catalog_id, server_id)
    return server


async def uninstall_catalog_entry_from_company(
    *,
    container: FlowRuntimeContainer,
    catalog_id: str,
) -> None:
    entry = await container.mcp_catalog_repository.get(catalog_id)
    if entry is None:
        raise ValueError(f"Catalog entry {catalog_id!r} not found")

    server_id = server_id_from_catalog_id(catalog_id)
    server = await container.mcp_server_repository.get(server_id)
    if server is None:
        raise ValueError(f"MCP server {server_id!r} is not installed")
    if server.source != MCPServerSource.CATALOG:
        raise ValueError(f"MCP server {server_id!r} is not catalog-managed")
    if server.catalog_id != catalog_id:
        raise ValueError(f"MCP server {server_id!r} catalog_id mismatch")
    if server.catalog_auto_provisioned:
        raise ValueError(
            f"Catalog entry {catalog_id!r} is auto-provisioned; use server delete is not allowed"
        )

    for tool_id in server.cached_tools:
        _ = await container.tool_repository.delete(tool_id)
    _ = await container.mcp_server_repository.delete(server_id)
    logger.info("MCP Store uninstall: catalog_id=%s server_id=%s", catalog_id, server_id)
