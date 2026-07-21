"""Tests for MCP server and catalog display order."""

from __future__ import annotations

from pathlib import Path

from apps.flows.src.models.mcp import MCPServerConfig, MCPServerSource, MCPTransportType
from apps.flows.src.models.mcp_catalog import MCPCatalogEntry, MCPCatalogVerifyStatus
from apps.flows.src.services.mcp_server_display_order import (
    sort_mcp_catalog_entries_for_display,
    sort_mcp_servers_for_display,
)
from tests.flows.integration.mcp_catalog_helpers import (
    build_verified_catalog_entry,
    mcp_catalog_settings,
)


def _server(
    *,
    server_id: str,
    name: str,
    source: MCPServerSource,
    catalog_id: str | None = None,
    catalog_auto_provisioned: bool = False,
) -> MCPServerConfig:
    return MCPServerConfig(
        server_id=server_id,
        name=name,
        url="https://example.com/mcp",
        transport_type=MCPTransportType.HTTP,
        source=source,
        catalog_id=catalog_id,
        catalog_auto_provisioned=catalog_auto_provisioned,
    )


def _entry(
    *,
    catalog_id: str,
    title: str,
    platform_approved: bool = False,
) -> MCPCatalogEntry:
    return build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=f"https://example.test/{catalog_id}/mcp",
        platform_approved=platform_approved,
        verify_status=MCPCatalogVerifyStatus.VERIFIED,
        registry_name=f"demo/{catalog_id}",
        title=title,
        description=f"{title} description",
    )


def test_sort_mcp_servers_platform_allowlist_manual_before_store_catalog(
    tmp_path: Path,
) -> None:
    allowlist_path = tmp_path / "allowlist.yaml"
    _ = allowlist_path.write_text(
        "\n".join(
            [
                "- catalog_id: zebra_curated",
                "  platform_approved: true",
                "  auth_policy: none",
                "- catalog_id: alpha_curated",
                "  platform_approved: true",
                "  auth_policy: none",
                "",
            ]
        ),
        encoding="utf-8",
    )
    with mcp_catalog_settings(allowlist_path=str(allowlist_path)):
        servers = [
            _server(
                server_id="store_a",
                name="A Store",
                source=MCPServerSource.CATALOG,
                catalog_id="store_a",
            ),
            _server(server_id="manual", name="Manual", source=MCPServerSource.MANUAL),
            _server(
                server_id="alpha_curated",
                name="Alpha Curated",
                source=MCPServerSource.CATALOG,
                catalog_id="alpha_curated",
                catalog_auto_provisioned=True,
            ),
            _server(server_id="browser", name="Browser", source=MCPServerSource.PLATFORM),
            _server(
                server_id="zebra_curated",
                name="Zebra Curated",
                source=MCPServerSource.CATALOG,
                catalog_id="zebra_curated",
                catalog_auto_provisioned=True,
            ),
        ]
        ordered = sort_mcp_servers_for_display(servers)
        assert [s.server_id for s in ordered] == [
            "browser",
            "zebra_curated",
            "alpha_curated",
            "manual",
            "store_a",
        ]


def test_sort_mcp_catalog_entries_allowlist_first(tmp_path: Path) -> None:
    allowlist_path = tmp_path / "allowlist.yaml"
    _ = allowlist_path.write_text(
        "\n".join(
            [
                "- catalog_id: zebra_curated",
                "  platform_approved: true",
                "  auth_policy: none",
                "- catalog_id: alpha_curated",
                "  platform_approved: true",
                "  auth_policy: none",
                "",
            ]
        ),
        encoding="utf-8",
    )
    with mcp_catalog_settings(allowlist_path=str(allowlist_path)):
        entries = [
            _entry(catalog_id="store_beta", title="Beta Store"),
            _entry(catalog_id="alpha_curated", title="Alpha", platform_approved=True),
            _entry(catalog_id="store_alpha", title="Alpha Store"),
            _entry(catalog_id="zebra_curated", title="Zebra", platform_approved=True),
        ]
        ordered = sort_mcp_catalog_entries_for_display(entries)
        assert [entry.catalog_id for entry in ordered] == [
            "zebra_curated",
            "alpha_curated",
            "store_alpha",
            "store_beta",
        ]
