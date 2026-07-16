"""Unit tests for MCP catalog store visibility helpers."""

from __future__ import annotations

import pytest

from apps.flows.src.models.mcp_catalog import MCPCatalogEntry, MCPCatalogVerifyStatus
from apps.flows.src.services.mcp_catalog_store import (
    catalog_entry_is_search_visible,
    catalog_entry_is_store_installable,
    catalog_store_entry_matches_search,
)
from tests.flows.integration.mcp_catalog_helpers import build_verified_catalog_entry


def _entry(
    *,
    catalog_id: str = "store_demo",
    platform_approved: bool = False,
    is_deprecated: bool = False,
    verify_status: MCPCatalogVerifyStatus = MCPCatalogVerifyStatus.VERIFIED,
    registry_name: str = "demo/store",
    title: str = "Store Demo",
    description: str = "Demo description",
) -> MCPCatalogEntry:
    return build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url="https://example.test/mcp",
        platform_approved=platform_approved,
        is_deprecated=is_deprecated,
        verify_status=verify_status,
        registry_name=registry_name,
        title=title,
        description=description,
    )


@pytest.mark.parametrize(
    ("platform_approved", "is_deprecated", "verify_status", "expected"),
    [
        (True, False, MCPCatalogVerifyStatus.VERIFIED, False),
        (False, True, MCPCatalogVerifyStatus.VERIFIED, False),
        (False, False, MCPCatalogVerifyStatus.VERIFIED, True),
        (False, False, MCPCatalogVerifyStatus.AUTH_REQUIRED, True),
        (False, False, MCPCatalogVerifyStatus.PENDING, False),
        (False, False, MCPCatalogVerifyStatus.UNREACHABLE, False),
    ],
)
def test_catalog_entry_is_store_installable_matrix(
    platform_approved: bool,
    is_deprecated: bool,
    verify_status: MCPCatalogVerifyStatus,
    expected: bool,
) -> None:
    entry = _entry(
        platform_approved=platform_approved,
        is_deprecated=is_deprecated,
        verify_status=verify_status,
    )
    assert catalog_entry_is_store_installable(entry) is expected


@pytest.mark.parametrize(
    ("search", "field", "value", "expected"),
    [
        ("", "catalog_id", "ignored", True),
        ("store_demo", "catalog_id", "store_demo", True),
        ("demo/store", "registry_name", "demo/store", True),
        ("store demo", "title", "Store Demo", True),
        ("demo description", "description", "Demo description", True),
        ("missing", "title", "Store Demo", False),
    ],
)
def test_catalog_store_entry_matches_search(
    search: str,
    field: str,
    value: str,
    expected: bool,
) -> None:
    if field == "catalog_id":
        entry = _entry(catalog_id=value)
    elif field == "registry_name":
        entry = _entry(registry_name=value)
    elif field == "title":
        entry = _entry(title=value)
    else:
        entry = _entry(description=value)
    assert catalog_store_entry_matches_search(entry, search) is expected


@pytest.mark.parametrize(
    ("platform_approved", "is_deprecated", "search", "expected"),
    [
        (False, False, "", True),
        (True, False, "", False),
        (True, False, "context7", True),
        (True, True, "context7", False),
    ],
)
def test_catalog_entry_is_search_visible(
    platform_approved: bool,
    is_deprecated: bool,
    search: str,
    expected: bool,
) -> None:
    entry = _entry(
        catalog_id="context7_catalog",
        platform_approved=platform_approved,
        is_deprecated=is_deprecated,
        title="Context7",
    )
    assert catalog_entry_is_search_visible(entry, search) is expected
