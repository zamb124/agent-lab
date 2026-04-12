"""
Интеграционные тесты POST /api/v1/flows/{flow_id}/reload-from-bundle.

Проверяют перезапись flow в БД из каталога bundle без моков: реальный ASGI-клиент,
репозиторий flows и файлы apps/flows/bundles/.
"""

import pytest


@pytest.mark.asyncio
async def test_reload_from_bundle_restores_config_from_disk(
    client,
    container,
    auth_headers_system,
):
    """
    После порчи имени flow в БД reload подтягивает данные из bundle с диска обратно.
    """
    flow_id = "example_react"
    cfg = await container.flow_repository.get(flow_id)
    if cfg is None:
        pytest.fail(f"Ожидался загруженный при старте flow {flow_id} (registry / lifespan)")

    assert cfg.source == "file"
    original_name = cfg.name

    corrupted = "__CORRUPTED_BY_TEST_RELOAD__"
    cfg.name = corrupted
    await container.flow_repository.set(cfg)

    after_corrupt = await container.flow_repository.get(flow_id)
    assert after_corrupt is not None
    assert after_corrupt.name == corrupted

    response = await client.post(
        f"/flows/api/v1/flows/{flow_id}/reload-from-bundle",
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["flow_id"] == flow_id
    assert flow_id in payload.get("message", "")

    restored = await container.flow_repository.get(flow_id)
    assert restored is not None
    assert restored.name == original_name
    assert restored.source == "file"

    get_response = await client.get(
        f"/flows/api/v1/flows/{flow_id}",
        headers=auth_headers_system,
    )
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["name"] == original_name
    assert body.get("source") == "file"


@pytest.mark.asyncio
async def test_reload_from_bundle_returns_404_when_flow_absent(
    client,
    auth_headers_system,
):
    response = await client.post(
        "/flows/api/v1/flows/nonexistent_flow_id_xyz999/reload-from-bundle",
        headers=auth_headers_system,
    )
    assert response.status_code == 404
    assert "not found" in response.json().get("detail", "").lower()


@pytest.mark.asyncio
async def test_reload_from_bundle_returns_400_when_no_bundle_directory(
    client,
    unique_id,
    auth_headers_system,
):
    """
    Flow создан только через API (source=api); каталога bundle с таким id нет — 400.
    """
    flow_id = f"api_only_agent_{unique_id}"
    create = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": "API only",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "test",
                    "tools": [],
                }
            },
            "edges": [{"from": "main", "to": None}],
        },
    )
    assert create.status_code == 200, create.text
    assert create.json().get("source") == "api"

    response = await client.post(
        f"/flows/api/v1/flows/{flow_id}/reload-from-bundle",
        headers=auth_headers_system,
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert isinstance(detail, str)
    assert len(detail) > 0

    delete = await client.delete(
        f"/flows/api/v1/flows/{flow_id}",
        headers=auth_headers_system,
    )
    assert delete.status_code == 200


@pytest.mark.asyncio
async def test_get_flow_returns_source_for_listed_flows(client, auth_headers_system):
    """Список и GET отдают поле source для bundle-агента."""
    list_resp = await client.get("/flows/api/v1/flows/", headers=auth_headers_system)
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    example = next((x for x in items if x.get("flow_id") == "example_react"), None)
    assert example is not None, "example_react должен быть в списке после загрузки registry"
    assert example.get("source") == "file"

    get_resp = await client.get(
        "/flows/api/v1/flows/example_react",
        headers=auth_headers_system,
    )
    assert get_resp.status_code == 200
    assert get_resp.json().get("source") == "file"
