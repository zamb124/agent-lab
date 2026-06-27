"""Tests for MCP server display order."""

from apps.flows.src.models.mcp import MCPServerConfig, MCPServerSource, MCPTransportType
from apps.flows.src.services.mcp_server_display_order import sort_mcp_servers_for_display


def _server(*, server_id: str, name: str, source: MCPServerSource) -> MCPServerConfig:
    return MCPServerConfig(
        server_id=server_id,
        name=name,
        url="https://example.com/mcp",
        transport_type=MCPTransportType.HTTP,
        source=source,
    )


def test_sort_mcp_servers_platform_manual_before_catalog() -> None:
    servers = [
        _server(server_id="z_catalog", name="Z Catalog", source=MCPServerSource.CATALOG),
        _server(server_id="manual", name="Manual", source=MCPServerSource.MANUAL),
        _server(server_id="browser", name="Browser", source=MCPServerSource.PLATFORM),
        _server(server_id="a_catalog", name="A Catalog", source=MCPServerSource.CATALOG),
    ]
    ordered = sort_mcp_servers_for_display(servers)
    assert [s.server_id for s in ordered] == [
        "browser",
        "manual",
        "a_catalog",
        "z_catalog",
    ]
