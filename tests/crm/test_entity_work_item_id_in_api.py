"""EntityResponse содержит work_item_id для CRM-задач."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_task_entity_response_includes_work_item_id(
    crm_client: AsyncClient,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    namespace = f"g_{unique_id}"
    create_resp = await crm_client.post(
        "/crm/api/v1/entities/",
        json={
            "entity_type": "task",
            "name": f"Task {unique_id}",
            "namespace": namespace,
        },
        headers=auth_headers_system,
    )
    assert create_resp.status_code == 200
    entity_id = create_resp.json()["entity_id"]

    get_resp = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_system,
    )
    assert get_resp.status_code == 200
    payload = get_resp.json()
    assert isinstance(payload.get("work_item_id"), str)
    assert payload["work_item_id"]

    list_resp = await crm_client.post(
        "/crm/api/v1/entities/query",
        json={
            "entity_type": "task",
            "namespace": namespace,
            "limit": 20,
        },
        headers=auth_headers_system,
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    matched = [item for item in items if item["entity_id"] == entity_id]
    assert len(matched) == 1
    assert isinstance(matched[0].get("work_item_id"), str)
