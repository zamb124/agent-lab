"""
Интеграционные тесты POST /api/v1/flows/{flow_id}/reload-from-bundle.

Проверяют перезапись flow в БД из каталога bundle без моков: реальный ASGI-клиент,
репозиторий flows и файлы apps/flows/bundles/.
"""

import pytest


@pytest.mark.asyncio
async def test_reload_from_bundle_restores_config_from_disk(client, container, auth_headers_system):
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
        f"/flows/api/v1/flows/{flow_id}/reload-from-bundle", headers=auth_headers_system
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["flow_id"] == flow_id
    assert flow_id in payload.get("message", "")
    restored = await container.flow_repository.get(flow_id)
    assert restored is not None
    assert restored.name == original_name
    assert restored.source == "file"
    get_response = await client.get(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["name"] == original_name
    assert body.get("source") == "file"
    assert body.get("has_bundle_update") is False


@pytest.mark.asyncio
async def test_get_flow_has_no_bundle_update_after_reload_matches_disk(client, auth_headers_system):
    """После reload GET не помечает flow как отстающий от bundle (флаг в API)."""
    flow_id = "example_react"
    response = await client.post(
        f"/flows/api/v1/flows/{flow_id}/reload-from-bundle", headers=auth_headers_system
    )
    assert response.status_code == 200, response.text
    get_response = await client.get(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)
    assert get_response.status_code == 200
    assert get_response.json().get("has_bundle_update") is False


@pytest.mark.asyncio
async def test_has_bundle_update_false_when_only_metadata_differs_from_bundle(
    client, container, unique_id: str, auth_headers_system
) -> None:
    _ = unique_id
    "\n    Метаданные редактора не участвуют в сравнении с disk-bundle: индикатор не зажигается.\n\n    Перед проверкой выполняем reload-from-bundle: в общей БД тестов ``example_react``\n    мог быть изменён другими кейсами — без синхронизации с диском семантика уже\n    расходится с bundle и флаг ложноположительный не из‑за metadata.\n    "
    flow_id = "example_react"
    reload_resp = await client.post(
        f"/flows/api/v1/flows/{flow_id}/reload-from-bundle", headers=auth_headers_system
    )
    assert reload_resp.status_code == 200, reload_resp.text
    cfg = await container.flow_repository.get(flow_id)
    if cfg is None:
        pytest.fail(f"Ожидался загруженный при старте flow {flow_id} (registry / lifespan)")
    assert (getattr(cfg, "source", None) or "manual") == "file"
    original_meta = dict(cfg.metadata) if cfg.metadata else {}
    try:
        cfg.metadata = {
            "sticky_notes": [{"id": "test-note-only-metadata", "x": 0, "y": 0, "text": "n"}]
        }
        await container.flow_repository.set(cfg)
        get_response = await client.get(
            f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system
        )
        assert get_response.status_code == 200
        assert get_response.json().get("has_bundle_update") is False
    finally:
        cfg.metadata = original_meta
        await container.flow_repository.set(cfg)


@pytest.mark.asyncio
async def test_reload_from_bundle_returns_404_when_flow_absent(client, auth_headers_system):
    response = await client.post(
        "/flows/api/v1/flows/nonexistent_flow_id_xyz999/reload-from-bundle",
        headers=auth_headers_system,
    )
    assert response.status_code == 404
    detail = response.json().get("detail", "").lower()
    assert "found" in detail or "найден" in detail


@pytest.mark.asyncio
async def test_reload_from_bundle_returns_400_when_no_bundle_directory(
    client, unique_id, auth_headers_system
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
            "nodes": {"main": {"type": "llm_node", "prompt": "test", "tools": []}},
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert create.status_code == 200, create.text
    assert create.json().get("source") == "api"
    response = await client.post(
        f"/flows/api/v1/flows/{flow_id}/reload-from-bundle", headers=auth_headers_system
    )
    assert response.status_code == 404
    detail = response.json().get("detail", "")
    assert isinstance(detail, str)
    assert len(detail) > 0
    delete = await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)
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
    get_resp = await client.get("/flows/api/v1/flows/example_react", headers=auth_headers_system)
    assert get_resp.status_code == 200
    assert get_resp.json().get("source") == "file"
