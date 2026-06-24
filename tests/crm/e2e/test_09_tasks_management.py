"""
Тесты задач CRM как графовых узлов.

Cutover: CRM `entity_type=task` — графовый узел (имя/описание/атрибуты/связи/теги),
а work-семантика (state/priority/assignee/срок) живёт в парном WorkItem(crm_activity).
Здесь проверяется CRM-сторона (узел + фильтры графа + lifecycle status) и факт
наличия парного WorkItem. Полное покрытие пары — в test_crm_work_item_pairing.py.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from core.worktracker.models import WorkItemKind, WorkItemState
from tests.crm.e2e._json_helpers import json_object, object_list, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _query_items(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("items"))


def _crm_work_item_service():
    from apps.crm.container import get_crm_container

    return get_crm_container().work_item_service


class TestTasksManagement:
    """Задачи CRM (графовый узел + парный WorkItem)."""

    @pytest.mark.asyncio
    async def test_create_task_is_graph_node_without_work_fields(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Задача {unique_id}",
            "description": "Описание задачи",
            "tags": ["важно", "проект-x"],
        }, headers=auth_headers_system)
        assert response.status_code == 200
        task = _http_json(response)
        assert object_str(task.get("entity_type"), field="entity_type") == "task"
        # Work-полей на CRM-узле нет — они в WorkItem.
        assert "priority" not in task
        assert "due_date" not in task
        assert "assignees" not in task

    @pytest.mark.asyncio
    async def test_create_task_pairs_work_item(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Paired {unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(resp)
        item = await _crm_work_item_service().find_by_crm_entity("system", entity_id)
        assert item is not None
        assert item.kind is WorkItemKind.CRM_ACTIVITY
        assert item.state is WorkItemState.OPEN

    @pytest.mark.asyncio
    async def test_tasks_list_by_user(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        test_user_id = f"test_user_{unique_id}"
        for i in range(3):
            _ = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "task",
                "name": f"Task {i} {unique_id}",
                "user_id": test_user_id,
            }, headers=auth_headers_system)

        list_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "task",
                "limit": 100,
                "filters": {"field": "user_id", "op": "$eq", "value": test_user_id},
            },
            headers=auth_headers_system,
        )
        assert list_resp.status_code == 200
        tasks = _query_items(list_resp)
        assert len(tasks) >= 3
        for task_row in tasks:
            assert object_str(task_row.get("user_id"), field="user_id") == test_user_id

    @pytest.mark.asyncio
    async def test_tasks_filter_by_tag(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        test_user_id = f"test_user_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Tagged {unique_id}",
            "tags": ["ivan"],
            "user_id": test_user_id,
        }, headers=auth_headers_system)

        tagged_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "task",
                "limit": 100,
                "filters": {
                    "$and": [
                        {"field": "user_id", "op": "$eq", "value": test_user_id},
                        {"field": "tags", "op": "$contains", "value": "ivan"},
                    ],
                },
            },
            headers=auth_headers_system,
        )
        assert tagged_resp.status_code == 200
        tagged = _query_items(tagged_resp)
        assert len(tagged) >= 1

    @pytest.mark.asyncio
    async def test_update_task_lifecycle_status(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Задача {unique_id}",
        }, headers=auth_headers_system)
        task_id = _entity_id(create_resp)

        update_resp = await crm_client.put(f"/crm/api/v1/entities/{task_id}", json={
            "status": "completed",
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200

        get_resp = await crm_client.get(
            f"/crm/api/v1/entities/{task_id}", headers=auth_headers_system
        )
        task = _http_json(get_resp)
        assert object_str(task.get("status"), field="status") == "completed"
