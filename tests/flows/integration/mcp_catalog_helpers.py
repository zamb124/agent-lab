"""Хелперы strict integration-тестов MCP catalog (без mocks)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

from httpx import AsyncClient

from apps.flows.config import get_settings, set_settings
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.mcp_catalog import (
    MCPAuthPolicy,
    MCPCatalogEntry,
    MCPCatalogHostClass,
    MCPCatalogVerifyStatus,
    compute_catalog_snapshot_hash,
)
from core.config.base import BaseSettings
from core.config.models import MCPCatalogConfig


class AllowlistYamlEntry(TypedDict):
    catalog_id: str
    platform_approved: NotRequired[bool]
    auth_template: NotRequired[dict[str, str]]
    required_variables: NotRequired[list[str]]
    auth_policy: NotRequired[str]


@contextmanager
def mcp_catalog_settings(**overrides: object) -> Generator[MCPCatalogConfig]:
    """Временно меняет `settings.mcp_catalog` через `set_settings`, без monkeypatch."""
    original_settings: BaseSettings = get_settings()
    effective_overrides = dict(overrides)
    temp_allowlist_path: Path | None = None
    if "allowlist_path" not in effective_overrides:
        fd, temp_path = tempfile.mkstemp(suffix=".yaml", prefix="mcp_catalog_allowlist_test_")
        os.close(fd)
        temp_allowlist_path = Path(temp_path)
        write_allowlist_yaml(path=temp_allowlist_path, entries=[])
        effective_overrides["allowlist_path"] = str(temp_allowlist_path)
    mcp_catalog_cfg = original_settings.mcp_catalog.model_copy(update=effective_overrides)
    updated_settings = original_settings.model_copy(update={"mcp_catalog": mcp_catalog_cfg})
    set_settings(updated_settings)
    try:
        yield mcp_catalog_cfg
    finally:
        set_settings(original_settings)
        if temp_allowlist_path is not None:
            temp_allowlist_path.unlink(missing_ok=True)


def build_verified_catalog_entry(
    *,
    catalog_id: str,
    upstream_url: str,
    registry_name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    platform_approved: bool = True,
    auth_template: dict[str, str] | None = None,
    is_deprecated: bool = False,
    transport_type: Literal["http", "sse"] = "http",
    verify_status: MCPCatalogVerifyStatus = MCPCatalogVerifyStatus.VERIFIED,
) -> MCPCatalogEntry:
    """Каноническая verified-запись catalog для strict provision-тестов."""
    resolved_title = title if title is not None else f"Test {catalog_id}"
    resolved_registry_name = registry_name if registry_name is not None else f"test.local/{catalog_id}"
    resolved_auth_template = auth_template if auth_template is not None else {}
    return MCPCatalogEntry(
        catalog_id=catalog_id,
        registry_name=resolved_registry_name,
        title=resolved_title,
        description=description if description is not None else "Catalog strict test entry",
        version="1.0.0",
        upstream_url=upstream_url,
        transport_type=transport_type,
        host_class=MCPCatalogHostClass.DIRECT,
        auth_policy=MCPAuthPolicy.NONE,
        auth_template=resolved_auth_template,
        required_variables=[],
        verify_status=verify_status,
        tool_count_snapshot=1,
        catalog_snapshot_hash=compute_catalog_snapshot_hash(
            title=resolved_title,
            description=description if description is not None else "Catalog strict test entry",
            upstream_url=upstream_url,
            transport_type=transport_type,
            auth_template=resolved_auth_template,
            is_deprecated=is_deprecated,
            verify_status=verify_status,
        ),
        platform_approved=platform_approved,
        is_deprecated=is_deprecated,
        last_crawled_at=datetime.now(tz=timezone.utc),
        last_verified_at=datetime.now(tz=timezone.utc),
    )


async def persist_catalog_entry(
    *,
    container: FlowRuntimeContainer,
    entry: MCPCatalogEntry,
) -> MCPCatalogEntry:
    stored = entry.model_copy(
        update={"catalog_snapshot_hash": entry.recompute_snapshot_hash()}
    )
    _ = await container.mcp_catalog_repository.set(stored)
    return stored


async def cleanup_catalog_and_server(
    *,
    container: FlowRuntimeContainer,
    client: AsyncClient,
    catalog_id: str,
    server_id: str,
) -> None:
    _ = await container.mcp_catalog_repository.delete(catalog_id)
    response = await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")
    if response.status_code not in (200, 404):
        raise AssertionError(
            f"cleanup delete server failed: status={response.status_code} body={response.text}"
        )


def write_allowlist_yaml(*, path: Path, entries: list[AllowlistYamlEntry]) -> None:
    lines: list[str] = []
    for entry in entries:
        catalog_id = entry["catalog_id"]
        lines.append(f"- catalog_id: {catalog_id}")
        platform_approved = entry.get("platform_approved")
        if platform_approved is not None:
            lines.append(f"  platform_approved: {str(platform_approved).lower()}")
        auth_template = entry.get("auth_template")
        if auth_template is not None:
            lines.append("  auth_template:")
            for key, value in auth_template.items():
                lines.append(f'    {key}: "{value}"')
        required_variables = entry.get("required_variables")
        if required_variables is not None:
            lines.append("  required_variables:")
            for variable_name in required_variables:
                lines.append(f"    - {variable_name}")
        auth_policy = entry.get("auth_policy")
        if auth_policy is not None:
            lines.append(f"  auth_policy: {auth_policy}")
    _ = path.write_text("\n".join(lines) + "\n", encoding="utf-8")
