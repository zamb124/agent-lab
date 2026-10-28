"""
Тесты задач CRM как графовых узлов + native activity-tasks workspace.

Cutover: CRM `entity_type=task` — графовый узел; work-семантика — WorkItem(crm_activity).
Primary create path Networkle — POST /crm/api/v1/activity-tasks.
Полное покрытие пары и cross-service мутаций — test_crm_work_item_pairing.py,
test_networkle_activity_tasks.py.
"""

from typing import cast

import pytest
from httpx import AsyncClient, Response

from core.worktracker.models import Board, WorkItem, WorkItemKind, WorkItemState
from tests.crm.e2e._json_helpers import json_object, object_list, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _query_items(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("items"))


class TestTasksManagement:
    """Задачи CRM (графовый узел + парный WorkItem + activity-tasks facade)."""

    @pytest.mark.asyncio
    async def test_create_task_is_graph_node_without_work_fields(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        response = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "task",
            "name": f"Задача {unique_id}",
            "description": "Описание задачи",
            "tags": ["важно", "проект-x"],
            "namespace": f"g_{unique_id}",
        }, headers=auth_headers_system)
        assert response.status_code == 200
        task = _http_json(response)
        assert object_str(task.get("entity_type"), field="entity_type") == "task"
        assert "priority" not in task
        assert "due_date" not in task
        assert "assignees" not in task
        assert isinstance(task.get("work_item_id"), str)
        assert task["work_item_id"]

    @pytest.mark.asyncio
    async def test_create_task_pairs_work_item(
        self,
        crm_client: AsyncClient,
        crm_di,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "task",
            "name": f"Paired {unique_id}",
            "namespace": f"g_{unique_id}",
        }, headers=auth_headers_system)
        entity_id = _entity_id(resp)
        item = await WorkItem.any_crm_activity_by_entity_id("system", entity_id)
        assert item is not None
        assert item.kind is WorkItemKind.CRM_ACTIVITY
        assert item.state is WorkItemState.OPEN
        assert item.board_id is not None
        board = await Board.require_in_company(
            company_id="system",
            board_id=item.board_id,
        )
        assert board.board_key == "task"

    @pytest.mark.asyncio
    async def test_activity_tasks_create_is_primary_pair_path(
        self,
        crm_client: AsyncClient,
        crm_di,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        namespace = f"g_{unique_id}"
        resp = await crm_client.post(
            "/crm/api/v1/activity-tasks",
            json={
                "title": f"Primary {unique_id}",
                "namespace": namespace,
                "priority": "high",
                "tags": ["workspace"],
            },
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        body = _http_json(resp)
        entity = body.get("entity")
        work_item = body.get("work_item")
        assert isinstance(entity, dict)
        assert isinstance(work_item, dict)
        assert object_str(entity.get("entity_type"), field="entity_type") == "task"
        assert object_str(work_item.get("kind"), field="kind") == "crm_activity"
        assert object_str(work_item.get("priority"), field="priority") == "high"
        assert entity.get("work_item_id") == work_item.get("work_item_id")

        listed = await crm_client.get(
            "/crm/api/v1/activity-tasks",
            params={"namespace": namespace, "limit": 20, "offset": 0},
            headers=auth_headers_system,
        )
        assert listed.status_code == 200
        items = object_list(_http_json(listed).get("items"))
        assert any(
            row.get("work_item_id") == work_item.get("work_item_id") for row in items
        )

        entity_id = object_str(entity.get("entity_id"), field="entity_id")
        persisted = await crm_di.crm_work_item_service.get_for_task(
            company_id="system",
            entity_id=entity_id,
        )
        assert persisted is not None
        assert persisted.work_item_id == work_item.get("work_item_id")

    @pytest.mark.asyncio
    async def test_tasks_list_by_user(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        test_user_id = f"test_user_{unique_id}"
        namespace = f"g_{unique_id}"
        for i in range(3):
            _ = await crm_client.post("/crm/api/v1/entities", json={
                "entity_type": "task",
                "name": f"Task {i} {unique_id}",
                "user_id": test_user_id,
                "namespace": namespace,
            }, headers=auth_headers_system)

        list_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "task",
                "namespace": namespace,
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
            assert isinstance(task_row.get("work_item_id"), str)

    @pytest.mark.asyncio
    async def test_tasks_filter_by_tag(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        test_user_id = f"test_user_{unique_id}"
        namespace = f"g_{unique_id}"
        _ = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "task",
            "name": f"Tagged {unique_id}",
            "tags": ["ivan"],
            "user_id": test_user_id,
            "namespace": namespace,
        }, headers=auth_headers_system)

        tagged_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "task",
                "namespace": namespace,
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
        crm_di,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Lifecycle status CRM-узла ≠ канбан WorkItem.state."""
        create_resp = await crm_client.post("/crm/api/v1/entities", json={
            "entity_type": "task",
            "name": f"Задача {unique_id}",
            "namespace": f"g_{unique_id}",
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

        item = await WorkItem.any_crm_activity_by_entity_id("system", task_id)
        assert item is not None
        # Lifecycle completed на CRM-узле не обязан переводить WorkItem в done.
        assert item.state is WorkItemState.OPEN
