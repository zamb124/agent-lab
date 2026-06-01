"""
Дефолтные MCP серверы компании.
"""

from __future__ import annotations

from apps.flows.config import get_settings
from apps.flows.src.models.mcp import MCPServerConfig, MCPTransportType


def build_default_mcp_servers() -> list[MCPServerConfig]:
    settings = get_settings()
    browser_base = settings.server.get_service_url("browser").rstrip("/")
    browser_mcp_url = f"{browser_base}/browser/api/v1/mcp"
    search_base = settings.server.get_service_url("search").rstrip("/")
    search_mcp_url = f"{search_base}/search/api/v1/mcp"

    return [
        MCPServerConfig(
            server_id="browser",
            name="Browser Runtime",
            url=browser_mcp_url,
            transport_type=MCPTransportType.HTTP,
            headers={},
            propagate_platform_context=True,
            is_active=True,
            description="Platform Browser Runtime MCP (JSON-RPC 2.0)",
        ),
        MCPServerConfig(
            server_id="search",
            name="Search",
            url=search_mcp_url,
            transport_type=MCPTransportType.HTTP,
            headers={},
            propagate_platform_context=True,
            is_active=True,
            description="Platform Search MCP (SERP providers, suggestions, result insights)",
        ),
    ]
