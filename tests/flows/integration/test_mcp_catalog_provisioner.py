"""
Strict integration tests: MCP catalog crawl, provision, override lock, reset.

Инварианты:
- без mocks и monkeypatch;
- реальный Postgres/Storage, HTTP ASGI client, локальные MCP/registry stubs;
- полные контракты ответов API и состояние репозиториев после каждого сценария.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.flows.src.models.mcp import MCPServerConfig, MCPServerSource, MCPTransportType
from apps.flows.src.models.mcp_catalog import MCPCatalogEntry, MCPCatalogVerifyStatus
from apps.flows.src.services.mcp_catalog_crawler import (
    crawl_mcp_registry,
    load_mcp_catalog_allowlist,
)
from apps.flows.src.services.mcp_catalog_ids import (
    catalog_id_from_registry_name,
    server_id_from_catalog_id,
)
from apps.flows.src.services.mcp_catalog_provisioner import (
    provision_mcp_catalog_for_company,
    resync_catalog_tools_for_company,
)
from apps.flows.src.tasks.mcp_catalog_tasks import mcp_catalog_provision_companies_task
from core.integrations.mcp import MCP_PROTOCOL_VERSION
from tests.fixtures.mcp_registry_stub import build_registry_server_item
from tests.flows.integration.mcp_catalog_helpers import (
    build_verified_catalog_entry,
    cleanup_catalog_and_server,
    mcp_catalog_settings,
    persist_catalog_entry,
    write_allowlist_yaml,
)


def test_catalog_id_from_registry_name_slug_contract() -> None:
    """Registry `name` → стабильный `catalog_id` для provision."""
    assert catalog_id_from_registry_name("io.github.foo/my-mcp") == "io_github_foo_my_mcp"
    assert catalog_id_from_registry_name("123/bad") == "mcp_123_bad"


@pytest.mark.asyncio
async def test_allowlist_yaml_loads_auth_template_from_real_file(tmp_path: Path) -> None:
    """Allowlist читается с диска; auth_template попадает в typed entry."""
    allowlist_path = tmp_path / "allowlist.yaml"
    write_allowlist_yaml(
        path=allowlist_path,
        entries=[
            {
                "catalog_id": "allowlisted_server",
                "platform_approved": True,
                "auth_template": {"Authorization": "Bearer @var:mcp_token"},
                "required_variables": ["mcp_token"],
                "auth_policy": "api_key",
            }
        ],
    )
    with mcp_catalog_settings(allowlist_path=str(allowlist_path)):
        allowlist = load_mcp_catalog_allowlist()
    assert set(allowlist.keys()) == {"allowlisted_server"}
    entry = allowlist["allowlisted_server"]
    assert entry.platform_approved is True
    assert entry.auth_template == {"Authorization": "Bearer @var:mcp_token"}
    assert entry.required_variables == ["mcp_token"]
    assert entry.auth_policy.value == "api_key"


@pytest.mark.asyncio
async def test_crawl_skips_stdio_and_http_only_remotes(
    local_mcp_registry_stub,
    unique_id: str,
    di,
) -> None:
    """
    Crawl не создаёт catalog entries для stdio/npm и non-HTTPS remotes.
    HTTPS unreachable endpoint всё же попадает в catalog как UNREACHABLE.
    """
    registry_base_url, state = local_mcp_registry_stub
    unreachable_name = f"test.local/unreachable_{unique_id}"
    unreachable_catalog_id = catalog_id_from_registry_name(unreachable_name)
    state.pages = [
        {
            "servers": [
                build_registry_server_item(
                    registry_name=f"test.local/stdio_{unique_id}",
                    upstream_url="stdio://local",
                    remote_type="stdio",
                ),
                build_registry_server_item(
                    registry_name=f"test.local/http_only_{unique_id}",
                    upstream_url="http://127.0.0.1:9/mcp",
                    remote_type="streamable-http",
                ),
                build_registry_server_item(
                    registry_name=unreachable_name,
                    upstream_url="https://127.0.0.1:9/mcp",
                    remote_type="streamable-http",
                ),
            ],
            "metadata": {},
        }
    ]
    with mcp_catalog_settings(
        registry_base_url=registry_base_url,
        max_verify_per_crawl=10,
        auto_provision="disabled",
    ):
        stats = await crawl_mcp_registry(di=di)

    assert stats.fetched == 1
    assert stats.upserted == 1
    assert stats.verify_failed == 1

    unreachable_entry = await MCPCatalogEntry.get(unreachable_catalog_id)
    assert unreachable_entry is not None
    assert unreachable_entry.verify_status == MCPCatalogVerifyStatus.UNREACHABLE
    assert unreachable_entry.is_deprecated is False

    stdio_entry = await MCPCatalogEntry.get(
        catalog_id_from_registry_name(f"test.local/stdio_{unique_id}")
    )
    http_only_entry = await MCPCatalogEntry.get(
        catalog_id_from_registry_name(f"test.local/http_only_{unique_id}")
    )
    assert stdio_entry is None
    assert http_only_entry is None

    _ = await MCPCatalogEntry.delete_by_id(unreachable_catalog_id)


@pytest.mark.asyncio
async def test_crawl_deprecates_catalog_entries_missing_from_registry(
    local_mcp_registry_stub,
    unique_id: str,
    di,
) -> None:
    """Запись, исчезнувшая из registry snapshot, помечается `is_deprecated=true`."""
    registry_base_url, state = local_mcp_registry_stub
    catalog_id = f"crawl_dep_{unique_id}"
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url="https://127.0.0.1:9/mcp",
    )
    _ = await persist_catalog_entry(entry=entry)

    state.pages = [{"servers": [], "metadata": {}}]
    with mcp_catalog_settings(
        registry_base_url=registry_base_url,
        max_verify_per_crawl=0,
        auto_provision="disabled",
    ):
        stats = await crawl_mcp_registry(di=di)

    assert stats.deprecated == 1
    stored = await MCPCatalogEntry.get(catalog_id)
    assert stored is not None
    assert stored.is_deprecated is True

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_crawl_preserves_verify_status_when_upstream_unchanged(
    local_mcp_registry_stub,
    unique_id: str,
    di,
) -> None:
    """Повторный crawl с тем же upstream не сбрасывает verified статус."""
    registry_base_url, state = local_mcp_registry_stub
    registry_name = f"test.local/preserve_{unique_id}"
    catalog_id = catalog_id_from_registry_name(registry_name)
    upstream_url = "https://127.0.0.1:9/mcp"
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=upstream_url,
        registry_name=registry_name,
        title="Preserve Verify Title",
    )
    _ = await persist_catalog_entry(entry=entry)

    state.pages = [
        {
            "servers": [
                build_registry_server_item(
                    registry_name=registry_name,
                    upstream_url=upstream_url,
                    title="Preserve Verify Title",
                )
            ],
            "metadata": {},
        }
    ]
    with mcp_catalog_settings(
        registry_base_url=registry_base_url,
        max_verify_per_crawl=5,
        auto_provision="disabled",
    ):
        stats = await crawl_mcp_registry(di=di)

    assert stats.fetched == 1
    assert stats.upserted == 1
    assert stats.verify_failed == 0
    assert stats.verified == 0

    stored = await MCPCatalogEntry.get(catalog_id)
    assert stored is not None
    assert stored.verify_status == MCPCatalogVerifyStatus.VERIFIED
    assert stored.tool_count_snapshot == entry.tool_count_snapshot

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_crawl_applies_allowlist_auth_template_to_catalog_entry(
    local_mcp_registry_stub,
    tmp_path: Path,
    unique_id: str,
    di,
) -> None:
    """Crawl мержит allowlist yaml в catalog entry до verify."""
    registry_base_url, state = local_mcp_registry_stub
    registry_name = f"test.local/crawl_allow_{unique_id}"
    catalog_id = catalog_id_from_registry_name(registry_name)
    allowlist_path = tmp_path / "allowlist.yaml"
    write_allowlist_yaml(
        path=allowlist_path,
        entries=[
            {
                "catalog_id": catalog_id,
                "platform_approved": True,
                "auth_template": {"Authorization": "Bearer @var:registry_token"},
                "required_variables": ["registry_token"],
                "auth_policy": "api_key",
            }
        ],
    )
    state.pages = [
        {
            "servers": [
                build_registry_server_item(
                    registry_name=registry_name,
                    upstream_url="https://127.0.0.1:9/mcp",
                    title=f"Crawl Allow Title {unique_id}",
                )
            ],
            "metadata": {},
        }
    ]
    with mcp_catalog_settings(
        registry_base_url=registry_base_url,
        allowlist_path=str(allowlist_path),
        max_verify_per_crawl=0,
        auto_provision="disabled",
    ):
        stats = await crawl_mcp_registry(di=di)

    assert stats.fetched == 1
    assert stats.upserted == 1
    stored = await MCPCatalogEntry.get(catalog_id)
    assert stored is not None
    assert stored.platform_approved is True
    assert stored.auth_template == {"Authorization": "Bearer @var:registry_token"}
    assert stored.required_variables == ["registry_token"]
    assert stored.title == f"Crawl Allow Title {unique_id}"
    assert stored.verify_status == MCPCatalogVerifyStatus.PENDING

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_provision_all_verified_adds_server_with_full_http_contract(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """Provision создаёт catalog-сервер, синкает tools, GET отражает полный контракт."""
    catalog_id = f"prov_add_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        stats = await provision_mcp_catalog_for_company(di=di)

    assert stats.added == 1
    assert stats.sync_ok == 1
    assert stats.sync_failed == 0

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200, get_response.text
    body = get_response.json()
    assert body["server_id"] == server_id
    assert body["name"] == entry.title
    assert body["url"] == local_mcp_http_url
    assert body["transport_type"] == "http"
    assert body["headers"] == {}
    assert body["is_active"] is True
    assert body["description"] == entry.description
    assert body["source"] == "catalog"
    assert body["catalog_id"] == catalog_id
    assert body["catalog_snapshot_hash"] == entry.catalog_snapshot_hash
    assert body["override_locked"] is False
    assert body["override_locked_at"] is None
    assert body["override_locked_by_user_id"] is None
    assert len(body["cached_tools"]) == 1
    assert body["last_sync_at"] is not None

    tools_response = await client.get("/flows/api/v1/tools/all?picker_category=mcp")
    assert tools_response.status_code == 200
    all_tools = tools_response.json()["items"]
    mcp_tools = [tool for tool in all_tools if tool.get("mcp_server_id") == server_id]
    assert len(mcp_tools) == 1
    assert mcp_tools[0]["tool_id"] == body["cached_tools"][0]
    assert mcp_tools[0]["parameters_schema"]["type"] == "object"
    assert mcp_tools[0]["mcp_schema_version"] == MCP_PROTOCOL_VERSION

    await cleanup_catalog_and_server(
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_provision_approved_only_skips_unapproved_entry(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """При `approved_only` запись без `platform_approved` не provision'ится."""
    catalog_id = f"prov_skip_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=False,
    )
    _ = await persist_catalog_entry(entry=entry)

    with mcp_catalog_settings(auto_provision="approved_only"):
        stats = await provision_mcp_catalog_for_company(di=di)

    assert stats.added == 0
    assert stats.updated == 0

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 404

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_provision_approved_only_provisions_platform_approved_entry(
    client,
    local_mcp_http_url: str,
    tmp_path: Path,
    unique_id: str,
    di,
) -> None:
    """При `approved_only` provision создаёт только `platform_approved=true` entries."""
    catalog_id = f"prov_allow_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    allowlist_path = tmp_path / "allowlist.yaml"
    write_allowlist_yaml(
        path=allowlist_path,
        entries=[
            {
                "catalog_id": catalog_id,
                "platform_approved": True,
                "auth_template": {"Authorization": "Bearer @var:mcp_token"},
                "required_variables": ["mcp_token"],
                "auth_policy": "api_key",
            }
        ],
    )
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=True,
        auth_template={"Authorization": "Bearer @var:mcp_token"},
    )
    _ = await persist_catalog_entry(entry=entry)

    with mcp_catalog_settings(
        allowlist_path=str(allowlist_path),
        auto_provision="approved_only",
    ):
        allowlist = load_mcp_catalog_allowlist()
        assert catalog_id in allowlist
        stats = await provision_mcp_catalog_for_company(di=di)

    assert stats.added == 1
    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["source"] == "catalog"
    assert body["headers"] == {"Authorization": "Bearer @var:mcp_token"}
    assert body["catalog_auto_provisioned"] is True

    await cleanup_catalog_and_server(
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_provision_updates_unlocked_server_when_catalog_snapshot_changes(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """Unlocked catalog-сервер получает managed fields из обновлённого catalog snapshot."""
    catalog_id = f"prov_upd_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        first_stats = await provision_mcp_catalog_for_company(di=di)
        assert first_stats.added == 1

        updated_entry = entry.model_copy(update={"title": f"Updated Title {unique_id}"})
        updated_entry.catalog_snapshot_hash = updated_entry.recompute_snapshot_hash()
        _ = await persist_catalog_entry(entry=updated_entry)

        second_stats = await provision_mcp_catalog_for_company(di=di)

    assert second_stats.updated == 1
    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == f"Updated Title {unique_id}"
    assert get_response.json()["catalog_snapshot_hash"] == updated_entry.catalog_snapshot_hash

    await cleanup_catalog_and_server(
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_provision_skips_override_locked_server(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """Provisioner не перезаписывает managed fields у `override_locked=true`."""
    catalog_id = f"prov_lock_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        _ = await provision_mcp_catalog_for_company(di=di)

    put_response = await client.put(
        f"/flows/api/v1/mcp/servers/{server_id}",
        json={"headers": {"Authorization": "Bearer tenant-secret"}},
    )
    assert put_response.status_code == 200, put_response.text
    locked_body = put_response.json()
    assert locked_body["override_locked"] is True
    assert locked_body["override_locked_by_user_id"] is not None
    assert locked_body["headers"] == {"Authorization": "Bearer tenant-secret"}

    updated_entry = entry.model_copy(update={"title": f"Catalog New Title {unique_id}"})
    updated_entry.catalog_snapshot_hash = updated_entry.recompute_snapshot_hash()
    _ = await persist_catalog_entry(entry=updated_entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        stats = await provision_mcp_catalog_for_company(di=di)

    assert stats.skipped_locked == 1

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["name"] != f"Catalog New Title {unique_id}"
    assert body["headers"] == {"Authorization": "Bearer tenant-secret"}
    assert body["override_locked"] is True

    await cleanup_catalog_and_server(
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_provision_deprecates_active_catalog_server_when_entry_removed_from_policy(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """Если catalog entry больше не provisionable, активный unlocked сервер деактивируется."""
    catalog_id = f"prov_dep_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        _ = await provision_mcp_catalog_for_company(di=di)

    deprecated_entry = entry.model_copy(update={"is_deprecated": True})
    deprecated_entry.catalog_snapshot_hash = deprecated_entry.recompute_snapshot_hash()
    _ = await persist_catalog_entry(entry=deprecated_entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        stats = await provision_mcp_catalog_for_company(di=di)

    assert stats.deprecated == 1

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200
    assert get_response.json()["is_active"] is False

    await cleanup_catalog_and_server(
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_provision_does_not_touch_manual_server(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """Manual MCP сервер не изменяется catalog provisioner."""
    manual_server_id = f"manual_{unique_id}"
    create_response = await client.post(
        "/flows/api/v1/mcp/servers",
        json={
            "server_id": manual_server_id,
            "name": "Manual MCP",
            "url": local_mcp_http_url,
            "transport_type": "http",
            "description": "manual strict test",
        },
    )
    assert create_response.status_code == 200, create_response.text
    manual_before = create_response.json()
    assert manual_before["source"] == "manual"

    with mcp_catalog_settings(auto_provision="all_verified"):
        _ = await provision_mcp_catalog_for_company(di=di)

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{manual_server_id}")
    assert get_response.status_code == 200
    manual_after = get_response.json()
    assert manual_after["name"] == manual_before["name"]
    assert manual_after["url"] == manual_before["url"]
    assert manual_after["source"] == "manual"

    _ = await client.delete(f"/flows/api/v1/mcp/servers/{manual_server_id}")


@pytest.mark.asyncio
async def test_reset_catalog_defaults_restores_snapshot_and_resyncs_tools(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """POST reset восстанавливает catalog snapshot и пересинкает tools."""
    catalog_id = f"reset_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    variable_key = f"mcp_token_{unique_id}"
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        auth_template={"Authorization": f"Bearer @var:{variable_key}"},
    )
    _ = await persist_catalog_entry(entry=entry)

    from tests.fixtures.variables_helpers import upsert_static_variable_via_service

    await upsert_static_variable_via_service(
        di,
        variable_key,
        "catalog-reset-secret",
        secret=True,
        shared_for_execution=True,
    )

    with mcp_catalog_settings(auto_provision="all_verified"):
        _ = await provision_mcp_catalog_for_company(di=di)

    put_response = await client.put(
        f"/flows/api/v1/mcp/servers/{server_id}",
        json={
            "name": "Tenant override name",
            "headers": {"Authorization": "Bearer tenant-secret"},
        },
    )
    assert put_response.status_code == 200
    assert put_response.json()["override_locked"] is True

    reset_response = await client.post(
        f"/flows/api/v1/mcp/servers/{server_id}/reset_catalog_defaults",
    )
    assert reset_response.status_code == 200, reset_response.text
    body = reset_response.json()
    assert body["source"] == "catalog"
    assert body["catalog_id"] == catalog_id
    assert body["name"] == entry.title
    assert body["url"] == local_mcp_http_url
    assert body["headers"] == entry.auth_template
    assert body["override_locked"] is False
    assert body["override_locked_at"] is None
    assert body["override_locked_by_user_id"] is None
    assert len(body["cached_tools"]) == 1
    assert body["last_sync_at"] is not None

    stored = await MCPServerConfig.get(MCPServerConfig.server_row_id_for_active_company(server_id))
    assert stored is not None
    assert stored.catalog_snapshot_hash == entry.catalog_snapshot_hash

    await cleanup_catalog_and_server(
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_reset_catalog_defaults_rejects_manual_source(
    client,
    local_mcp_http_url: str,
    unique_id: str,
) -> None:
    """Reset API fail-closed для `source=manual`."""
    manual_server_id = f"manual_reset_{unique_id}"
    create_response = await client.post(
        "/flows/api/v1/mcp/servers",
        json={
            "server_id": manual_server_id,
            "name": "Manual Reset",
            "url": local_mcp_http_url,
            "transport_type": "http",
        },
    )
    assert create_response.status_code == 200

    reset_response = await client.post(
        f"/flows/api/v1/mcp/servers/{manual_server_id}/reset_catalog_defaults",
    )
    assert reset_response.status_code == 400
    assert reset_response.json()["detail"] == "reset_catalog_defaults requires source=catalog"

    _ = await client.delete(f"/flows/api/v1/mcp/servers/{manual_server_id}")


@pytest.mark.asyncio
async def test_resync_catalog_tools_for_company_refreshes_cached_tools(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """Resync job обновляет cached_tools у unlocked catalog сервера."""
    catalog_id = f"resync_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        _ = await provision_mcp_catalog_for_company(di=di)

    before = await MCPServerConfig.get(MCPServerConfig.server_row_id_for_active_company(server_id))
    assert before is not None
    assert len(before.cached_tools) == 1
    before_sync_at = before.last_sync_at

    sync_ok, _sync_failed = await resync_catalog_tools_for_company(di=di)
    assert sync_ok >= 1

    after = await MCPServerConfig.get(MCPServerConfig.server_row_id_for_active_company(server_id))
    assert after is not None
    assert len(after.cached_tools) == 1
    assert after.last_sync_at is not None
    if before_sync_at is not None:
        assert after.last_sync_at >= before_sync_at

    await cleanup_catalog_and_server(
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_mcp_catalog_provision_companies_task_aggregates_stats(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """TaskIQ provision task обходит компании и агрегирует stats без mocks."""
    catalog_id = f"task_prov_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified", enabled=True):
        result = await mcp_catalog_provision_companies_task(
            schedule_task_id=f"test-{unique_id}",
            company_id="system",
        )

    assert result["companies"] == 1
    assert result["added"] == 1
    assert result["sync_ok"] == 1
    assert result["sync_failed"] == 0

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["source"] == "catalog"
    assert get_response.json()["catalog_id"] == catalog_id

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)
    delete_response = await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")
    assert delete_response.status_code == 200


@pytest.mark.asyncio
async def test_mcp_catalog_auto_provision_disabled_is_noop(
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """`auto_provision=disabled` — provisioner и task не создают серверы."""
    catalog_id = f"disabled_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(entry=entry)

    with mcp_catalog_settings(auto_provision="disabled"):
        stats = await provision_mcp_catalog_for_company(di=di)
        task_result = await mcp_catalog_provision_companies_task(schedule_task_id=f"disabled-{unique_id}")

    assert stats.added == 0
    assert stats.updated == 0
    assert task_result["added"] == 0

    stored = await MCPServerConfig.get(MCPServerConfig.server_row_id_for_active_company(server_id))
    assert stored is None

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


def test_mcp_catalog_config_model_default_auto_provision() -> None:
    """Pydantic-default policy: opt-in Store only (disabled auto-provision)."""
    from core.config.models import MCPCatalogConfig

    assert MCPCatalogConfig().auto_provision == "disabled"


@pytest.mark.asyncio
async def test_provision_does_not_deactivate_opt_in_installed_server(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """Opt-in MCP Store сервер не деактивируется auto-provisioner при approved_only."""
    catalog_id = f"opt_in_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=False,
    )
    _ = await persist_catalog_entry(entry=entry)

    install_response = await client.post(f"/flows/api/v1/mcp/catalog/{catalog_id}/install")
    assert install_response.status_code == 200, install_response.text
    body = install_response.json()
    assert body["catalog_auto_provisioned"] is False

    deprecated_entry = entry.model_copy(update={"is_deprecated": True})
    deprecated_entry.catalog_snapshot_hash = deprecated_entry.recompute_snapshot_hash()
    _ = await persist_catalog_entry(entry=deprecated_entry)

    with mcp_catalog_settings(auto_provision="approved_only"):
        stats = await provision_mcp_catalog_for_company(di=di)

    assert stats.deprecated == 0
    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200
    assert get_response.json()["is_active"] is True

    uninstall_response = await client.delete(f"/flows/api/v1/mcp/catalog/{catalog_id}/install")
    assert uninstall_response.status_code == 200
    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_mcp_catalog_store_list_install_uninstall_api(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """MCP Store API: list tier=store, install, uninstall."""
    catalog_id = f"store_api_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=False,
        title=f"Store API {unique_id}",
    )
    _ = await persist_catalog_entry(entry=entry)

    list_response = await client.get(
        "/flows/api/v1/mcp/catalog",
        params={"tier": "store", "search": unique_id, "limit": 20, "offset": 0},
    )
    assert list_response.status_code == 200, list_response.text
    list_body = list_response.json()
    assert list_body["total"] == 1
    assert list_body["items"][0]["catalog_id"] == catalog_id
    assert list_body["items"][0]["installed"] is False

    install_response = await client.post(f"/flows/api/v1/mcp/catalog/{catalog_id}/install")
    assert install_response.status_code == 200, install_response.text
    assert install_response.json()["server_id"] == server_id

    list_after_install = await client.get(
        "/flows/api/v1/mcp/catalog",
        params={"tier": "store", "search": unique_id},
    )
    assert list_after_install.json()["items"][0]["installed"] is True

    tools_response = await client.get("/flows/api/v1/tools/all?picker_category=mcp")
    mcp_tools = [
        tool
        for tool in tools_response.json()["items"]
        if tool.get("mcp_server_id") == server_id
    ]
    assert len(mcp_tools) == 1

    uninstall_response = await client.delete(f"/flows/api/v1/mcp/catalog/{catalog_id}/install")
    assert uninstall_response.status_code == 200

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 404

    tools_after = await client.get("/flows/api/v1/tools/all?picker_category=mcp")
    mcp_tools_after = [
        tool
        for tool in tools_after.json()["items"]
        if tool.get("mcp_server_id") == server_id
    ]
    assert len(mcp_tools_after) == 0

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_mcp_servers_list_search_and_pagination(
    client,
    local_mcp_http_url: str,
    unique_id: str,
) -> None:
    first_server_id = f"search_one_{unique_id}"
    second_server_id = f"search_two_{unique_id}"
    first_response = await client.post(
        "/flows/api/v1/mcp/servers",
        json={
            "server_id": first_server_id,
            "name": f"Searchable Alpha {unique_id}",
            "url": f"{local_mcp_http_url}/alpha",
            "transport_type": "http",
            "description": "Installed search strict test",
        },
    )
    second_response = await client.post(
        "/flows/api/v1/mcp/servers",
        json={
            "server_id": second_server_id,
            "name": f"Searchable Beta {unique_id}",
            "url": f"{local_mcp_http_url}/beta",
            "transport_type": "http",
            "description": "Installed search strict test",
        },
    )
    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text

    search_response = await client.get(
        "/flows/api/v1/mcp/servers",
        params={"search": unique_id, "limit": 1, "offset": 1},
    )
    assert search_response.status_code == 200, search_response.text
    body = search_response.json()
    assert body["total"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["server_id"] in {first_server_id, second_server_id}

    _ = await client.delete(f"/flows/api/v1/mcp/servers/{first_server_id}")
    _ = await client.delete(f"/flows/api/v1/mcp/servers/{second_server_id}")


@pytest.mark.asyncio
async def test_mcp_catalog_lists_platform_curated_without_search(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    catalog_id = f"context7_catalog_{unique_id}"
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=True,
        title=f"Context7 {unique_id}",
        description="Up-to-date library documentation for LLM",
    )
    _ = await persist_catalog_entry(entry=entry)

    empty_search_response = await client.get(
        "/flows/api/v1/mcp/catalog",
        params={"tier": "store", "search": "", "limit": 50, "offset": 0},
    )
    assert empty_search_response.status_code == 200, empty_search_response.text
    empty_catalog_ids = [item["catalog_id"] for item in empty_search_response.json()["items"]]
    assert catalog_id in empty_catalog_ids

    curated_item = next(
        item
        for item in empty_search_response.json()["items"]
        if item["catalog_id"] == catalog_id
    )
    assert curated_item["platform_curated"] is True
    assert curated_item["installed"] is False

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_auto_provisioned_catalog_entry_allows_store_uninstall(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """Даже legacy auto-tier catalog сервер снимается через MCP Store uninstall."""
    catalog_id = f"auto_tier_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=True,
    )
    _ = await persist_catalog_entry(entry=entry)

    with mcp_catalog_settings(auto_provision="approved_only"):
        _ = await provision_mcp_catalog_for_company(di=di)

    stored = await MCPServerConfig.get(MCPServerConfig.server_row_id_for_active_company(server_id))
    assert stored is not None
    assert stored.catalog_auto_provisioned is True

    uninstall_response = await client.delete(f"/flows/api/v1/mcp/catalog/{catalog_id}/install")
    assert uninstall_response.status_code == 200, uninstall_response.text
    assert await MCPServerConfig.get(MCPServerConfig.server_row_id_for_active_company(server_id)) is None

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_mcp_catalog_install_is_idempotent(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    """Повторный POST install возвращает тот же server без дублей."""
    catalog_id = f"idempotent_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=False,
    )
    _ = await persist_catalog_entry(entry=entry)

    first = await client.post(f"/flows/api/v1/mcp/catalog/{catalog_id}/install")
    second = await client.post(f"/flows/api/v1/mcp/catalog/{catalog_id}/install")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["server_id"] == server_id
    assert second.json()["server_id"] == server_id

    list_response = await client.get("/flows/api/v1/mcp/servers", params={"limit": 500})
    server_ids = [item["server_id"] for item in list_response.json()["items"]]
    assert server_ids.count(server_id) == 1

    _ = await client.delete(f"/flows/api/v1/mcp/catalog/{catalog_id}/install")
    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_mcp_catalog_list_rejects_unknown_tier(client) -> None:
    response = await client.get("/flows/api/v1/mcp/catalog", params={"tier": "unknown"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Only tier=store is supported"


@pytest.mark.asyncio
async def test_mcp_catalog_store_pagination_offset(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    catalog_ids: list[str] = []
    for index in range(3):
        catalog_id = f"store_page_{index}_{unique_id}"
        catalog_ids.append(catalog_id)
        entry = build_verified_catalog_entry(
            catalog_id=catalog_id,
            upstream_url=local_mcp_http_url,
            platform_approved=False,
            title=f"Store Page {index} {unique_id}",
        )
        _ = await persist_catalog_entry(entry=entry)

    first_page = await client.get(
        "/flows/api/v1/mcp/catalog",
        params={"tier": "store", "search": unique_id, "limit": 1, "offset": 0},
    )
    second_page = await client.get(
        "/flows/api/v1/mcp/catalog",
        params={"tier": "store", "search": unique_id, "limit": 1, "offset": 1},
    )
    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text
    first_body = first_page.json()
    second_body = second_page.json()
    assert first_body["total"] == 3
    assert second_body["total"] == 3
    assert len(first_body["items"]) == 1
    assert len(second_body["items"]) == 1
    assert first_body["items"][0]["catalog_id"] != second_body["items"][0]["catalog_id"]

    for catalog_id in catalog_ids:
        _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_mcp_catalog_search_matches_registry_name_and_description(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    catalog_id = f"registry_search_{unique_id}"
    registry_name = f"registry.search.{unique_id}/tool"
    description = f"Description marker {unique_id}"
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=False,
        registry_name=registry_name,
        title=f"Title {unique_id}",
        description=description,
    )
    _ = await persist_catalog_entry(entry=entry)

    registry_response = await client.get(
        "/flows/api/v1/mcp/catalog",
        params={"tier": "store", "search": registry_name, "limit": 20, "offset": 0},
    )
    description_response = await client.get(
        "/flows/api/v1/mcp/catalog",
        params={"tier": "store", "search": description, "limit": 20, "offset": 0},
    )
    assert registry_response.status_code == 200, registry_response.text
    assert description_response.status_code == 200, description_response.text
    assert registry_response.json()["total"] == 1
    assert description_response.json()["total"] == 1
    assert registry_response.json()["items"][0]["catalog_id"] == catalog_id
    assert description_response.json()["items"][0]["catalog_id"] == catalog_id

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_mcp_catalog_install_and_uninstall_platform_curated(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    catalog_id = f"curated_install_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=True,
        title=f"Curated {unique_id}",
    )
    _ = await persist_catalog_entry(entry=entry)

    list_response = await client.get(
        "/flows/api/v1/mcp/catalog",
        params={"tier": "store", "limit": 50, "offset": 0},
    )
    assert list_response.status_code == 200, list_response.text
    curated_items = [
        item
        for item in list_response.json()["items"]
        if item["catalog_id"] == catalog_id
    ]
    assert len(curated_items) == 1
    assert curated_items[0]["platform_curated"] is True
    assert curated_items[0]["installed"] is False

    install_response = await client.post(f"/flows/api/v1/mcp/catalog/{catalog_id}/install")
    assert install_response.status_code == 200, install_response.text
    assert install_response.json()["server_id"] == server_id
    assert install_response.json()["catalog_auto_provisioned"] is False

    uninstall_response = await client.delete(f"/flows/api/v1/mcp/catalog/{catalog_id}/install")
    assert uninstall_response.status_code == 200, uninstall_response.text
    assert await MCPServerConfig.get(MCPServerConfig.server_row_id_for_active_company(server_id)) is None

    _ = await MCPCatalogEntry.delete_by_id(catalog_id)


@pytest.mark.asyncio
async def test_mcp_servers_search_matches_context7_alias(
    client,
    local_mcp_http_url: str,
    unique_id: str,
    di,
) -> None:
    server_id = f"alias_ctx7_{unique_id}"
    server = MCPServerConfig(
        server_id=server_id,
        name=f"Context7 manual {unique_id}",
        url=f"{local_mcp_http_url}/context7",
        transport_type=MCPTransportType.HTTP,
        source=MCPServerSource.MANUAL,
        catalog_id="context7_catalog",
    )
    _ = await MCPServerConfig.set(server)

    search_response = await client.get(
        "/flows/api/v1/mcp/servers",
        params={"search": "context7", "limit": 200, "offset": 0},
    )
    assert search_response.status_code == 200, search_response.text
    matched_ids = [item["server_id"] for item in search_response.json()["items"]]
    assert server_id in matched_ids

    _ = await MCPServerConfig.delete_by_id(MCPServerConfig.server_row_id_for_active_company(server_id))
