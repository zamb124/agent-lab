"""
Интеграционные тесты seed MCP branding из git-бандла.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.services.mcp_branding_seed import seed_mcp_branding_from_bundle
from core.context import Context, clear_context, set_context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from tests.flows.integration.mcp_catalog_helpers import (
    build_verified_catalog_entry,
    persist_catalog_entry,
)


def _write_test_bundle(bundle_dir: Path) -> Path:
    icons_dir = bundle_dir / "icons"
    icons_dir.mkdir(parents=True)
    generic_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
        '<circle cx="24" cy="24" r="12" fill="#6366F1"/></svg>'
    )
    brand_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
        '<rect x="8" y="8" width="32" height="32" fill="#22C55E"/></svg>'
    )
    _ = (icons_dir / "_generic.svg").write_text(generic_svg, encoding="utf-8")
    _ = (icons_dir / "brand.svg").write_text(brand_svg, encoding="utf-8")

    manifest_path = bundle_dir / "manifest.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "default_icon: icons/_generic.svg",
                "entries:",
                "  - server_id: browser",
                "    file: icons/brand.svg",
                "    source: test",
                "    license: internal",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _system_context() -> Context:
    return Context(
        user=User(user_id="system", name="System", groups=["admin"]),
        host="system",
        session_id="test:mcp_branding_seed",
        channel="system",
        language=Language.RU,
        active_company=Company(company_id="system", name="System", subdomain="system"),
        user_companies=[],
        trace_id="test:mcp_branding_seed",
    )


@pytest.mark.asyncio
async def test_mcp_branding_seed_catalog_generic_reuse_and_skip(
    tmp_path: Path,
    unique_id: str,
    app,
):
    _ = app
    manifest_path = _write_test_bundle(tmp_path)
    catalog_id_a = f"seedGenA{unique_id}"
    catalog_id_b = f"seedGenB{unique_id}"

    container = get_container()
    runtime = as_flow_runtime_container(container)
    branding_repo = container.mcp_server_branding_repository

    entry_a = build_verified_catalog_entry(
        catalog_id=catalog_id_a,
        upstream_url="https://example.test/mcp-a",
    )
    entry_b = build_verified_catalog_entry(
        catalog_id=catalog_id_b,
        upstream_url="https://example.test/mcp-b",
    )
    _ = await persist_catalog_entry(container=runtime, entry=entry_a)
    _ = await persist_catalog_entry(container=runtime, entry=entry_b)

    for server_id in ("browser", "search", catalog_id_a, catalog_id_b):
        existing = await branding_repo.get(server_id)
        if existing is not None:
            _ = await branding_repo.delete(server_id)

    target_server_ids = frozenset({"browser", "search", catalog_id_a, catalog_id_b})

    set_context(_system_context())
    try:
        stats = await seed_mcp_branding_from_bundle(
            runtime,
            manifest_path=manifest_path,
            server_ids=target_server_ids,
        )
    finally:
        clear_context()

    assert stats.targets == 4
    assert stats.seeded == 4
    assert stats.skipped_existing == 0

    browser_row = await branding_repo.get("browser")
    row_a = await branding_repo.get(catalog_id_a)
    row_b = await branding_repo.get(catalog_id_b)
    assert browser_row is not None
    assert row_a is not None
    assert row_b is not None
    assert browser_row.icon_file_id != row_a.icon_file_id
    assert row_a.icon_file_id == row_b.icon_file_id

    set_context(_system_context())
    try:
        stats_second = await seed_mcp_branding_from_bundle(
            runtime,
            manifest_path=manifest_path,
            server_ids=target_server_ids,
        )
    finally:
        clear_context()

    assert stats_second.targets == 4
    assert stats_second.seeded == 0
    assert stats_second.skipped_existing == 4

    set_context(_system_context())
    try:
        stats_force = await seed_mcp_branding_from_bundle(
            runtime,
            force=True,
            server_ids=frozenset({"browser"}),
            manifest_path=manifest_path,
        )
    finally:
        clear_context()

    assert stats_force.targets == 1
    assert stats_force.seeded == 1

    for server_id in ("browser", "search", catalog_id_a, catalog_id_b):
        existing = await branding_repo.get(server_id)
        if existing is not None:
            _ = await branding_repo.delete(server_id)
