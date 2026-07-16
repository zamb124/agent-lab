"""Unit tests for MCP server search helpers."""

from __future__ import annotations

import pytest

from apps.flows.src.models.mcp import MCPServerConfig, MCPServerSource, MCPTransportType
from apps.flows.src.services.mcp_server_search import (
    filter_mcp_servers_by_search,
    mcp_server_matches_search,
)


def _server(
    *,
    server_id: str,
    name: str = "Test Server",
    url: str = "https://example.test/mcp",
    description: str | None = None,
    catalog_id: str | None = None,
) -> MCPServerConfig:
    return MCPServerConfig(
        server_id=server_id,
        name=name,
        url=url,
        transport_type=MCPTransportType.HTTP,
        source=MCPServerSource.MANUAL,
        description=description,
        catalog_id=catalog_id,
    )


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ("", True),
        ("  ", True),
        ("alpha_srv", True),
        ("ALPHA", True),
        ("nomatch", False),
    ],
)
def test_mcp_server_matches_search_by_server_id(search: str, expected: bool) -> None:
    server = _server(server_id="alpha_srv")
    assert mcp_server_matches_search(server, search) is expected


def test_mcp_server_matches_search_by_name_url_description_and_catalog_id() -> None:
    server = _server(
        server_id="srv_one",
        name="Display Name",
        url="https://host.test/mcp",
        description="Catalog backed",
        catalog_id="catalog_demo",
    )
    assert mcp_server_matches_search(server, "display") is True
    assert mcp_server_matches_search(server, "host.test") is True
    assert mcp_server_matches_search(server, "catalog backed") is True
    assert mcp_server_matches_search(server, "catalog_demo") is True
    assert mcp_server_matches_search(server, "missing") is False


def test_mcp_server_matches_search_context7_alias_by_server_id() -> None:
    server = _server(server_id="context7_catalog", name="Context7")
    assert mcp_server_matches_search(server, "context7") is True


def test_mcp_server_matches_search_context7_alias_by_catalog_id() -> None:
    server = _server(
        server_id="mcp_context7_catalog",
        name="Context7",
        catalog_id="context7_catalog",
    )
    assert mcp_server_matches_search(server, "context7") is True


def test_filter_mcp_servers_by_search_preserves_order_and_filters() -> None:
    servers = [
        _server(server_id="alpha"),
        _server(server_id="beta", name="Other"),
        _server(server_id="gamma", description="alpha mention"),
    ]
    filtered = filter_mcp_servers_by_search(servers, "alpha")
    assert [server.server_id for server in filtered] == ["alpha", "gamma"]
