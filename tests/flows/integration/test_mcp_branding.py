"""
Интеграционные тесты глобального branding иконок MCP по server_id.
"""

from __future__ import annotations

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.models.mcp import MCPServerConfig, MCPServerSource, MCPTransportType
from core.files.create_spec import FileCreateSpec
from tests.flows.integration.mcp_catalog_helpers import (
    build_verified_catalog_entry,
    persist_catalog_entry,
)


def _platform_auxiliary_spec(*, is_public: bool) -> FileCreateSpec:
    return FileCreateSpec.model_validate(
        {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
            "post_create": {"is_public": is_public},
        }
    )


@pytest.mark.asyncio
async def test_mcp_branding_non_system_put_forbidden(
    client,
    auth_headers_company2,
    unique_id: str,
    app,
):
    _ = app
    container = get_container()
    record = await container.files_service.create(
        _platform_auxiliary_spec(is_public=True),
        b"icon",
        original_name="icon.png",
        content_type="image/png",
    )
    server_id = f"brand403{unique_id}"
    resp = await client.put(
        f"/flows/api/v1/mcp/branding/{server_id}",
        json={"icon_file_id": record.file_id},
        headers=auth_headers_company2,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_mcp_branding_private_file_rejected(client, unique_id: str, app):
    _ = app
    container = get_container()
    record = await container.files_service.create(
        _platform_auxiliary_spec(is_public=False),
        b"icon",
        original_name="private.png",
        content_type="image/png",
    )
    server_id = f"brand400{unique_id}"
    resp = await client.put(
        f"/flows/api/v1/mcp/branding/{server_id}",
        json={"icon_file_id": record.file_id},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_mcp_branding_upsert_list_servers_and_delete(client, unique_id: str, app):
    _ = app
    container = get_container()
    record = await container.files_service.create(
        _platform_auxiliary_spec(is_public=True),
        b"icon-payload",
        original_name="mcp-icon.png",
        content_type="image/png",
    )
    server_id = f"brandOk{unique_id}"

    put_resp = await client.put(
        f"/flows/api/v1/mcp/branding/{server_id}",
        json={"icon_file_id": record.file_id},
    )
    assert put_resp.status_code == 200, put_resp.text
    put_data = put_resp.json()
    assert put_data["server_id"] == server_id
    assert put_data["icon_file_id"] == record.file_id
    assert put_data["icon_url"].startswith("/")
    assert "/api/v1/files/download/" in put_data["icon_url"]

    list_branding = await client.get(
        "/flows/api/v1/mcp/branding",
        params={"search": server_id, "limit": 1, "offset": 0},
    )
    assert list_branding.status_code == 200, list_branding.text
    branding_payload = list_branding.json()
    assert "catalog_slugs" not in branding_payload
    assert branding_payload["total"] == 1
    assert branding_payload["limit"] == 1
    assert branding_payload["offset"] == 0
    branding_ids = [row["server_id"] for row in branding_payload["items"]]
    assert server_id in branding_ids

    list_servers = await client.get("/flows/api/v1/mcp/servers")
    assert list_servers.status_code == 200
    server_rows = list_servers.json()["items"]
    matched = [row for row in server_rows if row.get("server_id") == server_id]
    if matched:
        assert matched[0]["icon_url"] == put_data["icon_url"]

    del_resp = await client.delete(f"/flows/api/v1/mcp/branding/{server_id}")
    assert del_resp.status_code == 204, del_resp.text

    list_after = await client.get("/flows/api/v1/mcp/branding")
    assert list_after.status_code == 200
    after_ids = [row["server_id"] for row in list_after.json()["items"]]
    assert server_id not in after_ids


@pytest.mark.asyncio
async def test_mcp_branding_slug_suggest_searches_catalog(client, local_mcp_http_url: str) -> None:
    container = as_flow_runtime_container(get_container())
    existing_entry = await container.mcp_catalog_repository.get("context7_catalog")
    if existing_entry is None:
        entry = build_verified_catalog_entry(
            catalog_id="context7_catalog",
            upstream_url=local_mcp_http_url,
            platform_approved=True,
            title="Context7",
            description="Up-to-date library documentation for LLM",
        )
        _ = await persist_catalog_entry(container=container, entry=entry)

    response = await client.get(
        "/flows/api/v1/mcp/branding/slug-suggest",
        params={"search": "context7", "limit": 8},
    )
    assert response.status_code == 200, response.text
    assert "context7_catalog" in response.json()["slugs"]

    if existing_entry is None:
        _ = await container.mcp_catalog_repository.delete("context7_catalog")


@pytest.mark.asyncio
async def test_mcp_branding_list_pagination_offset(client, unique_id: str, app) -> None:
    _ = app
    container = get_container()
    record = await container.files_service.create(
        _platform_auxiliary_spec(is_public=True),
        b"icon-payload",
        original_name="mcp-icon.png",
        content_type="image/png",
    )
    first_server_id = f"brandPageA{unique_id}"
    second_server_id = f"brandPageB{unique_id}"
    for server_id in (first_server_id, second_server_id):
        put_resp = await client.put(
            f"/flows/api/v1/mcp/branding/{server_id}",
            json={"icon_file_id": record.file_id},
        )
        assert put_resp.status_code == 200, put_resp.text

    list_response = await client.get(
        "/flows/api/v1/mcp/branding",
        params={"search": unique_id, "limit": 1, "offset": 1},
    )
    assert list_response.status_code == 200, list_response.text
    body = list_response.json()
    assert body["total"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["server_id"] in {first_server_id, second_server_id}

    for server_id in (first_server_id, second_server_id):
        del_resp = await client.delete(f"/flows/api/v1/mcp/branding/{server_id}")
        assert del_resp.status_code == 204, del_resp.text


@pytest.mark.asyncio
async def test_mcp_branding_put_invalid_server_id(client, unique_id: str, app) -> None:
    _ = app
    container = get_container()
    record = await container.files_service.create(
        _platform_auxiliary_spec(is_public=True),
        b"icon-payload",
        original_name="mcp-icon.png",
        content_type="image/png",
    )
    _ = unique_id
    response = await client.put(
        "/flows/api/v1/mcp/branding/Bad%20Slug%21",
        json={"icon_file_id": record.file_id},
    )
    assert response.status_code == 400, response.text
    assert "valid MCP slug" in response.json()["detail"]


@pytest.mark.asyncio
async def test_mcp_branding_slug_suggest_includes_default_platform_servers(client) -> None:
    empty_response = await client.get(
        "/flows/api/v1/mcp/branding/slug-suggest",
        params={"search": "", "limit": 50},
    )
    assert empty_response.status_code == 200, empty_response.text
    slugs = empty_response.json()["slugs"]
    assert "browser" in slugs
    assert "search" in slugs

    limited_response = await client.get(
        "/flows/api/v1/mcp/branding/slug-suggest",
        params={"search": "", "limit": 2},
    )
    assert limited_response.status_code == 200, limited_response.text
    assert len(limited_response.json()["slugs"]) == 2


@pytest.mark.asyncio
async def test_mcp_servers_list_includes_branding_icon_via_alias(
    client,
    unique_id: str,
    app,
) -> None:
    _ = app
    _ = unique_id
    container = get_container()
    record = await container.files_service.create(
        _platform_auxiliary_spec(is_public=True),
        b"icon-payload",
        original_name="mcp-icon.png",
        content_type="image/png",
    )
    canonical_server_id = "context7_catalog"
    alias_server_id = "context7"
    put_resp = await client.put(
        f"/flows/api/v1/mcp/branding/{canonical_server_id}",
        json={"icon_file_id": record.file_id},
    )
    assert put_resp.status_code == 200, put_resp.text
    icon_url = put_resp.json()["icon_url"]

    existing = await container.mcp_server_repository.get(alias_server_id)
    created_manual = existing is None
    if created_manual:
        manual_server = MCPServerConfig(
            server_id=alias_server_id,
            name="Context7 manual alias test",
            url="https://example.test/context7/mcp",
            transport_type=MCPTransportType.HTTP,
            source=MCPServerSource.MANUAL,
        )
        _ = await container.mcp_server_repository.set(manual_server)

    list_response = await client.get(
        "/flows/api/v1/mcp/servers",
        params={"search": alias_server_id, "limit": 20, "offset": 0},
    )
    assert list_response.status_code == 200, list_response.text
    matched = [row for row in list_response.json()["items"] if row["server_id"] == alias_server_id]
    assert len(matched) == 1
    assert matched[0]["icon_url"] == icon_url

    if created_manual:
        _ = await container.mcp_server_repository.delete(alias_server_id)
    del_resp = await client.delete(f"/flows/api/v1/mcp/branding/{canonical_server_id}")
    assert del_resp.status_code == 204, del_resp.text
