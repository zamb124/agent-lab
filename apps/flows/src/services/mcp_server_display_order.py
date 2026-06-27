"""Порядок MCP серверов в UI: platform/manual выше catalog."""

from __future__ import annotations

from apps.flows.src.models.mcp import MCPServerConfig, MCPServerSource

_SOURCE_DISPLAY_RANK: dict[MCPServerSource, int] = {
    MCPServerSource.PLATFORM: 0,
    MCPServerSource.MANUAL: 1,
    MCPServerSource.CATALOG: 2,
}


def mcp_server_display_rank(source: MCPServerSource) -> int:
    return _SOURCE_DISPLAY_RANK[source]


def sort_mcp_servers_for_display(servers: list[MCPServerConfig]) -> list[MCPServerConfig]:
    def sort_key(server: MCPServerConfig) -> tuple[int, str, str]:
        return (
            mcp_server_display_rank(server.source),
            server.name.casefold(),
            server.server_id.casefold(),
        )

    return sorted(servers, key=sort_key)
