"""Порядок MCP серверов и catalog entries в UI: platform → yaml allowlist → остальное."""

from __future__ import annotations

from apps.flows.src.models.mcp import MCPServerConfig, MCPServerSource
from apps.flows.src.models.mcp_catalog import MCPCatalogEntry
from apps.flows.src.services.mcp_catalog_crawler import load_mcp_catalog_allowlist


def mcp_allowlist_catalog_id_ranks() -> dict[str, int]:
    """Индекс `catalog_id` из yaml allowlist (порядок строк в файле)."""
    return {
        catalog_id: index
        for index, catalog_id in enumerate(load_mcp_catalog_allowlist())
    }


def sort_mcp_catalog_entries_for_display(
    entries: list[MCPCatalogEntry],
) -> list[MCPCatalogEntry]:
    allowlist_ranks = mcp_allowlist_catalog_id_ranks()

    def sort_key(entry: MCPCatalogEntry) -> tuple[int, int, str, str]:
        allowlist_rank = allowlist_ranks.get(entry.catalog_id)
        if allowlist_rank is not None:
            return (0, allowlist_rank, entry.title.casefold(), entry.catalog_id.casefold())
        if entry.platform_approved:
            return (1, 0, entry.title.casefold(), entry.catalog_id.casefold())
        return (2, 0, entry.title.casefold(), entry.catalog_id.casefold())

    return sorted(entries, key=sort_key)


def sort_mcp_servers_for_display(servers: list[MCPServerConfig]) -> list[MCPServerConfig]:
    allowlist_ranks = mcp_allowlist_catalog_id_ranks()

    def sort_key(server: MCPServerConfig) -> tuple[int, int, str, str]:
        name = server.name.casefold()
        server_id = server.server_id.casefold()
        if server.source == MCPServerSource.PLATFORM:
            return (0, 0, name, server_id)
        catalog_id = server.catalog_id
        if catalog_id is not None:
            allowlist_rank = allowlist_ranks.get(catalog_id)
            if allowlist_rank is not None:
                return (1, allowlist_rank, name, server_id)
        if server.catalog_auto_provisioned:
            return (2, 0, name, server_id)
        if server.source == MCPServerSource.MANUAL:
            return (3, 0, name, server_id)
        return (4, 0, name, server_id)

    return sorted(servers, key=sort_key)
