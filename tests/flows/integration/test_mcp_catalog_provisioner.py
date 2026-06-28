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

from apps.flows.src.container import get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.models.mcp_catalog import MCPCatalogVerifyStatus
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
from apps.idle_worker.tasks.mcp_catalog_tasks import mcp_catalog_provision_companies_task
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
    container = as_flow_runtime_container(get_container())
    with mcp_catalog_settings(
        registry_base_url=registry_base_url,
        max_verify_per_crawl=10,
        auto_provision="disabled",
    ):
        stats = await crawl_mcp_registry(container=container)

    assert stats.fetched == 1
    assert stats.upserted == 1
    assert stats.verify_failed == 1

    unreachable_entry = await container.mcp_catalog_repository.get(unreachable_catalog_id)
    assert unreachable_entry is not None
    assert unreachable_entry.verify_status == MCPCatalogVerifyStatus.UNREACHABLE
    assert unreachable_entry.is_deprecated is False

    stdio_entry = await container.mcp_catalog_repository.get(
        catalog_id_from_registry_name(f"test.local/stdio_{unique_id}")
    )
    http_only_entry = await container.mcp_catalog_repository.get(
        catalog_id_from_registry_name(f"test.local/http_only_{unique_id}")
    )
    assert stdio_entry is None
    assert http_only_entry is None

    _ = await container.mcp_catalog_repository.delete(unreachable_catalog_id)


@pytest.mark.asyncio
async def test_crawl_deprecates_catalog_entries_missing_from_registry(
    local_mcp_registry_stub,
    unique_id: str,
) -> None:
    """Запись, исчезнувшая из registry snapshot, помечается `is_deprecated=true`."""
    registry_base_url, state = local_mcp_registry_stub
    catalog_id = f"crawl_dep_{unique_id}"
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url="https://127.0.0.1:9/mcp",
    )
    _ = await persist_catalog_entry(container=container, entry=entry)

    state.pages = [{"servers": [], "metadata": {}}]
    with mcp_catalog_settings(
        registry_base_url=registry_base_url,
        max_verify_per_crawl=0,
        auto_provision="disabled",
    ):
        stats = await crawl_mcp_registry(container=container)

    assert stats.deprecated == 1
    stored = await container.mcp_catalog_repository.get(catalog_id)
    assert stored is not None
    assert stored.is_deprecated is True

    _ = await container.mcp_catalog_repository.delete(catalog_id)


@pytest.mark.asyncio
async def test_crawl_preserves_verify_status_when_upstream_unchanged(
    local_mcp_registry_stub,
    unique_id: str,
) -> None:
    """Повторный crawl с тем же upstream не сбрасывает verified статус."""
    registry_base_url, state = local_mcp_registry_stub
    registry_name = f"test.local/preserve_{unique_id}"
    catalog_id = catalog_id_from_registry_name(registry_name)
    upstream_url = "https://127.0.0.1:9/mcp"
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=upstream_url,
        registry_name=registry_name,
        title="Preserve Verify Title",
    )
    _ = await persist_catalog_entry(container=container, entry=entry)

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
        stats = await crawl_mcp_registry(container=container)

    assert stats.fetched == 1
    assert stats.upserted == 1
    assert stats.verify_failed == 0
    assert stats.verified == 0

    stored = await container.mcp_catalog_repository.get(catalog_id)
    assert stored is not None
    assert stored.verify_status == MCPCatalogVerifyStatus.VERIFIED
    assert stored.tool_count_snapshot == entry.tool_count_snapshot

    _ = await container.mcp_catalog_repository.delete(catalog_id)


@pytest.mark.asyncio
async def test_crawl_applies_allowlist_auth_template_to_catalog_entry(
    local_mcp_registry_stub,
    tmp_path: Path,
    unique_id: str,
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
    container = as_flow_runtime_container(get_container())
    with mcp_catalog_settings(
        registry_base_url=registry_base_url,
        allowlist_path=str(allowlist_path),
        max_verify_per_crawl=0,
        auto_provision="disabled",
    ):
        stats = await crawl_mcp_registry(container=container)

    assert stats.fetched == 1
    assert stats.upserted == 1
    stored = await container.mcp_catalog_repository.get(catalog_id)
    assert stored is not None
    assert stored.platform_approved is True
    assert stored.auth_template == {"Authorization": "Bearer @var:registry_token"}
    assert stored.required_variables == ["registry_token"]
    assert stored.title == f"Crawl Allow Title {unique_id}"
    assert stored.verify_status == MCPCatalogVerifyStatus.PENDING

    _ = await container.mcp_catalog_repository.delete(catalog_id)


@pytest.mark.asyncio
async def test_provision_all_verified_adds_server_with_full_http_contract(
    client,
    local_mcp_http_url: str,
    unique_id: str,
) -> None:
    """Provision создаёт catalog-сервер, синкает tools, GET отражает полный контракт."""
    catalog_id = f"prov_add_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(container=container, entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        stats = await provision_mcp_catalog_for_company(container=container)

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

    tools_response = await client.get("/flows/api/v1/tools/all")
    assert tools_response.status_code == 200
    all_tools = tools_response.json()["items"]
    mcp_tools = [tool for tool in all_tools if tool.get("mcp_server_id") == server_id]
    assert len(mcp_tools) == 1
    assert mcp_tools[0]["tool_id"] == body["cached_tools"][0]
    assert mcp_tools[0]["parameters_schema"]["type"] == "object"
    assert mcp_tools[0]["mcp_schema_version"] == MCP_PROTOCOL_VERSION

    await cleanup_catalog_and_server(
        container=container,
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_provision_approved_only_skips_unapproved_entry(
    client,
    local_mcp_http_url: str,
    unique_id: str,
) -> None:
    """При `approved_only` запись без `platform_approved` не provision'ится."""
    catalog_id = f"prov_skip_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=False,
    )
    _ = await persist_catalog_entry(container=container, entry=entry)

    with mcp_catalog_settings(auto_provision="approved_only"):
        stats = await provision_mcp_catalog_for_company(container=container)

    assert stats.added == 0
    assert stats.updated == 0

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 404

    _ = await container.mcp_catalog_repository.delete(catalog_id)


@pytest.mark.asyncio
async def test_provision_approved_only_provisions_platform_approved_entry(
    client,
    local_mcp_http_url: str,
    tmp_path: Path,
    unique_id: str,
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
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        platform_approved=True,
        auth_template={"Authorization": "Bearer @var:mcp_token"},
    )
    _ = await persist_catalog_entry(container=container, entry=entry)

    with mcp_catalog_settings(
        allowlist_path=str(allowlist_path),
        auto_provision="approved_only",
    ):
        allowlist = load_mcp_catalog_allowlist()
        assert catalog_id in allowlist
        stats = await provision_mcp_catalog_for_company(container=container)

    assert stats.added == 1
    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["source"] == "catalog"
    assert body["headers"] == {"Authorization": "Bearer @var:mcp_token"}

    await cleanup_catalog_and_server(
        container=container,
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_provision_updates_unlocked_server_when_catalog_snapshot_changes(
    client,
    local_mcp_http_url: str,
    unique_id: str,
) -> None:
    """Unlocked catalog-сервер получает managed fields из обновлённого catalog snapshot."""
    catalog_id = f"prov_upd_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(container=container, entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        first_stats = await provision_mcp_catalog_for_company(container=container)
        assert first_stats.added == 1

        updated_entry = entry.model_copy(update={"title": f"Updated Title {unique_id}"})
        updated_entry.catalog_snapshot_hash = updated_entry.recompute_snapshot_hash()
        _ = await persist_catalog_entry(container=container, entry=updated_entry)

        second_stats = await provision_mcp_catalog_for_company(container=container)

    assert second_stats.updated == 1
    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == f"Updated Title {unique_id}"
    assert get_response.json()["catalog_snapshot_hash"] == updated_entry.catalog_snapshot_hash

    await cleanup_catalog_and_server(
        container=container,
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_provision_skips_override_locked_server(
    client,
    local_mcp_http_url: str,
    unique_id: str,
) -> None:
    """Provisioner не перезаписывает managed fields у `override_locked=true`."""
    catalog_id = f"prov_lock_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(container=container, entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        _ = await provision_mcp_catalog_for_company(container=container)

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
    _ = await persist_catalog_entry(container=container, entry=updated_entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        stats = await provision_mcp_catalog_for_company(container=container)

    assert stats.skipped_locked == 1

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["name"] != f"Catalog New Title {unique_id}"
    assert body["headers"] == {"Authorization": "Bearer tenant-secret"}
    assert body["override_locked"] is True

    await cleanup_catalog_and_server(
        container=container,
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_provision_deprecates_active_catalog_server_when_entry_removed_from_policy(
    client,
    local_mcp_http_url: str,
    unique_id: str,
) -> None:
    """Если catalog entry больше не provisionable, активный unlocked сервер деактивируется."""
    catalog_id = f"prov_dep_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(container=container, entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        _ = await provision_mcp_catalog_for_company(container=container)

    deprecated_entry = entry.model_copy(update={"is_deprecated": True})
    deprecated_entry.catalog_snapshot_hash = deprecated_entry.recompute_snapshot_hash()
    _ = await persist_catalog_entry(container=container, entry=deprecated_entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        stats = await provision_mcp_catalog_for_company(container=container)

    assert stats.deprecated == 1

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200
    assert get_response.json()["is_active"] is False

    await cleanup_catalog_and_server(
        container=container,
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_provision_does_not_touch_manual_server(
    client,
    local_mcp_http_url: str,
    unique_id: str,
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

    container = as_flow_runtime_container(get_container())
    with mcp_catalog_settings(auto_provision="all_verified"):
        _ = await provision_mcp_catalog_for_company(container=container)

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
) -> None:
    """POST reset восстанавливает catalog snapshot и пересинкает tools."""
    catalog_id = f"reset_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    variable_key = f"mcp_token_{unique_id}"
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        auth_template={"Authorization": f"Bearer @var:{variable_key}"},
    )
    _ = await persist_catalog_entry(container=container, entry=entry)

    from tests.fixtures.variables_helpers import upsert_static_variable_via_service

    await upsert_static_variable_via_service(
        get_container(),
        variable_key,
        "catalog-reset-secret",
        secret=True,
        shared_for_execution=True,
    )

    with mcp_catalog_settings(auto_provision="all_verified"):
        _ = await provision_mcp_catalog_for_company(container=container)

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

    stored = await container.mcp_server_repository.get(server_id)
    assert stored is not None
    assert stored.catalog_snapshot_hash == entry.catalog_snapshot_hash

    await cleanup_catalog_and_server(
        container=container,
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
) -> None:
    """Resync job обновляет cached_tools у unlocked catalog сервера."""
    catalog_id = f"resync_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(container=container, entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        _ = await provision_mcp_catalog_for_company(container=container)

    before = await container.mcp_server_repository.get(server_id)
    assert before is not None
    assert len(before.cached_tools) == 1
    before_sync_at = before.last_sync_at

    sync_ok, sync_failed = await resync_catalog_tools_for_company(container=container)
    assert sync_ok >= 1
    assert sync_failed == 0

    after = await container.mcp_server_repository.get(server_id)
    assert after is not None
    assert len(after.cached_tools) == 1
    assert after.last_sync_at is not None
    if before_sync_at is not None:
        assert after.last_sync_at >= before_sync_at

    await cleanup_catalog_and_server(
        container=container,
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_mcp_catalog_provision_companies_task_aggregates_stats(
    client,
    local_mcp_http_url: str,
    unique_id: str,
) -> None:
    """TaskIQ provision task обходит компании и агрегирует stats без mocks."""
    catalog_id = f"task_prov_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(container=container, entry=entry)

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

    _ = await container.mcp_catalog_repository.delete(catalog_id)
    delete_response = await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")
    assert delete_response.status_code == 200


@pytest.mark.asyncio
async def test_mcp_catalog_auto_provision_disabled_is_noop(
    local_mcp_http_url: str,
    unique_id: str,
) -> None:
    """`auto_provision=disabled` — provisioner и task не создают серверы."""
    catalog_id = f"disabled_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(catalog_id=catalog_id, upstream_url=local_mcp_http_url)
    _ = await persist_catalog_entry(container=container, entry=entry)

    with mcp_catalog_settings(auto_provision="disabled"):
        stats = await provision_mcp_catalog_for_company(container=container)
        task_result = await mcp_catalog_provision_companies_task(schedule_task_id=f"disabled-{unique_id}")

    assert stats.added == 0
    assert stats.updated == 0
    assert task_result["added"] == 0

    stored = await container.mcp_server_repository.get(server_id)
    assert stored is None

    _ = await container.mcp_catalog_repository.delete(catalog_id)


def test_mcp_catalog_config_model_default_auto_provision() -> None:
    """Pydantic-default policy: prod использует approved_only."""
    from core.config.models import MCPCatalogConfig

    assert MCPCatalogConfig().auto_provision == "approved_only"
