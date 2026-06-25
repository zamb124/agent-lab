"""
Интеграционные тесты глобального branding иконок MCP по server_id.
"""

from __future__ import annotations

import pytest

from core.files.create_spec import FileCreateSpec


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
    from apps.flows.src.container import get_container

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
    from apps.flows.src.container import get_container

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
    from apps.flows.src.container import get_container

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
    assert put_data["icon_url"].startswith("/frontend/api/v1/files/download/")

    list_branding = await client.get("/flows/api/v1/mcp/branding")
    assert list_branding.status_code == 200, list_branding.text
    branding_payload = list_branding.json()
    assert isinstance(branding_payload["catalog_slugs"], list)
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
