"""Search helpers for company MCP servers."""

from __future__ import annotations

from apps.flows.src.models.mcp import MCPServerConfig
from apps.flows.src.services.mcp_branding_aliases import BRANDING_SERVER_ID_ALIASES


def mcp_server_matches_search(server: MCPServerConfig, search: str) -> bool:
    query = search.strip().casefold()
    if not query:
        return True
    parts = [
        server.server_id,
        server.name,
        server.url,
        server.description,
        server.catalog_id,
    ]
    for alias_server_id, canonical_server_id in BRANDING_SERVER_ID_ALIASES.items():
        if server.server_id == canonical_server_id or server.catalog_id == canonical_server_id:
            parts.append(alias_server_id)
    haystack = " ".join(part for part in parts if part is not None).casefold()
    return query in haystack


def filter_mcp_servers_by_search(
    servers: list[MCPServerConfig],
    search: str,
) -> list[MCPServerConfig]:
    return [server for server in servers if mcp_server_matches_search(server, search)]
