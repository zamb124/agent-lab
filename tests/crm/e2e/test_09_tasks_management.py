"""
Тесты управления задачами.

User Story: Создание и управление задачами с приоритетами, дедлайнами и исполнителями.
"""

from datetime import date, timedelta
from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_list, object_str


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _query_items(response: Response) -> list[dict[str, object]]:
    return object_list(_http_json(response).get("items"))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            strings.append(item)
    return strings


class TestTasksManagement:
    """Управление задачами"""

    @pytest.mark.asyncio
    async def test_create_task_full(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Создание задачи со всеми полями"""
        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Полная задача {unique_id}",
            "description": "Подробное описание задачи с требованиями",
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
            "priority": "urgent",
            "status": "in_progress",
            "assignees": ["user1", "user2"],
            "tags": ["важно", "срочно", "проект-x"],
        }, headers=auth_headers_system)
        assert response.status_code == 200

        task = _http_json(response)
        assert object_str(task.get("entity_type"), field="entity_type") == "task"
        assert object_str(task.get("priority"), field="priority") == "urgent"
        assert len(_string_list(task.get("assignees"))) == 2
        assert "важно" in _string_list(task.get("tags"))

    @pytest.mark.asyncio
    async def test_prioritized_tasks_list(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Список задач, приоритезированный по важности"""
        test_user_id = f"test_user_{unique_id}"
        priorities = ["low", "medium", "high", "urgent"]
        task_ids: list[str] = []

        for i, priority in enumerate(priorities):
            resp = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "task",
                "name": f"Task {i} {unique_id}",
                "priority": priority,
                "due_date": date.today().isoformat(),
                "user_id": test_user_id,
            }, headers=auth_headers_system)
            task_ids.append(_entity_id(resp))

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

        assert len(tasks) >= 4
        for task_row in tasks:
            assert object_str(task_row.get("user_id"), field="user_id") == test_user_id

    @pytest.mark.asyncio
    async def test_update_task_status(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Изменение статуса задачи"""
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Задача {unique_id}",
            "status": "pending",
        }, headers=auth_headers_system)
        task_id = _entity_id(create_resp)

        update_resp = await crm_client.put(f"/crm/api/v1/entities/{task_id}", json={
            "status": "completed",
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{task_id}", headers=auth_headers_system)
        task = _http_json(get_resp)
        assert object_str(task.get("status"), field="status") == "completed"

    @pytest.mark.asyncio
    async def test_tasks_by_due_date(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Фильтрация задач по дедлайну"""
        test_user_id = f"test_user_{unique_id}"
        today = date.today()
        tomorrow = today + timedelta(days=1)

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Today task {unique_id}",
            "due_date": today.isoformat(),
            "user_id": test_user_id,
        }, headers=auth_headers_system)

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Tomorrow task {unique_id}",
            "due_date": tomorrow.isoformat(),
            "user_id": test_user_id,
        }, headers=auth_headers_system)

        today_tasks_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "task",
                "limit": 100,
                "filters": {
                    "$and": [
                        {"field": "user_id", "op": "$eq", "value": test_user_id},
                        {"field": "due_date", "op": "$eq", "value": today.isoformat()},
                    ],
                },
            },
            headers=auth_headers_system,
        )
        assert today_tasks_resp.status_code == 200
        today_tasks = _query_items(today_tasks_resp)
        assert len(today_tasks) >= 1
        for task_row in today_tasks:
            assert object_str(task_row.get("user_id"), field="user_id") == test_user_id

    @pytest.mark.asyncio
    async def test_tasks_by_assignee(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Фильтрация задач по исполнителю"""
        test_user_id = f"test_user_{unique_id}"

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Ivan task {unique_id}",
            "tags": ["ivan"],
            "user_id": test_user_id,
        }, headers=auth_headers_system)

        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Petr task {unique_id}",
            "assignees": ["petr"],
            "user_id": test_user_id,
        }, headers=auth_headers_system)

        ivan_tasks_resp = await crm_client.post(
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
        assert ivan_tasks_resp.status_code == 200
        ivan_tasks = _query_items(ivan_tasks_resp)
        assert len(ivan_tasks) >= 1
        for task_row in ivan_tasks:
            assert object_str(task_row.get("user_id"), field="user_id") == test_user_id

    @pytest.mark.asyncio
    async def test_overdue_tasks(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Просроченные задачи"""
        test_user_id = f"test_user_{unique_id}"
        past_date = (date.today() - timedelta(days=5)).isoformat()

        resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Overdue task {unique_id}",
            "due_date": past_date,
            "status": "in_progress",
            "user_id": test_user_id,
        }, headers=auth_headers_system)
        assert resp.status_code == 200

        overdue_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "task",
                "limit": 100,
                "filters": {
                    "$and": [
                        {"field": "user_id", "op": "$eq", "value": test_user_id},
                        {"field": "due_date", "op": "$lt", "value": date.today().isoformat()},
                        {"field": "status", "op": "$ne", "value": "completed"},
                    ],
                },
            },
            headers=auth_headers_system,
        )
        assert overdue_resp.status_code == 200
        overdue_tasks = _query_items(overdue_resp)
        assert len(overdue_tasks) >= 1
        for task_row in overdue_tasks:
            assert object_str(task_row.get("user_id"), field="user_id") == test_user_id
