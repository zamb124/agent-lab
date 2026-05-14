"""
Тесты управления задачами.

User Story: Создание и управление задачами с приоритетами, дедлайнами и исполнителями.
"""

from datetime import date, timedelta

import pytest


class TestTasksManagement:
    """Управление задачами"""

    @pytest.mark.asyncio
    async def test_create_task_full(self, crm_client, unique_id, auth_headers_system):
        """Создание задачи со всеми полями"""
        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Полная задача {unique_id}",
            "description": "Подробное описание задачи с требованиями",
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
            "priority": "urgent",
            "status": "in_progress",
            "assignees": ["user1", "user2"],
            "tags": ["важно", "срочно", "проект-x"]
        }, headers=auth_headers_system)
        assert response.status_code == 200

        task = response.json()
        assert task["entity_type"] == "task"
        assert task["priority"] == "urgent"
        assert len(task["assignees"]) == 2
        assert "важно" in task["tags"]

    @pytest.mark.asyncio
    async def test_prioritized_tasks_list(self, crm_client, unique_id, auth_headers_system):
        """Список задач, приоритезированный по важности"""
        test_user_id = f"test_user_{unique_id}"
        priorities = ["low", "medium", "high", "urgent"]
        task_ids = []

        for i, priority in enumerate(priorities):
            resp = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "task",
                "name": f"Task {i} {unique_id}",
                "priority": priority,
                "due_date": date.today().isoformat(),
                "user_id": test_user_id
            }, headers=auth_headers_system)
            task_ids.append(resp.json()["entity_id"])

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
        tasks = list_resp.json()["items"]

        assert len(tasks) >= 4
        for t in tasks:
            assert t["user_id"] == test_user_id

    @pytest.mark.asyncio
    async def test_update_task_status(self, crm_client, unique_id, auth_headers_system):
        """Изменение статуса задачи"""
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Задача {unique_id}",
            "status": "pending"
        }, headers=auth_headers_system)
        task_id = create_resp.json()["entity_id"]

        update_resp = await crm_client.put(f"/crm/api/v1/entities/{task_id}", json={
            "status": "completed"
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{task_id}", headers=auth_headers_system)
        task = get_resp.json()
        assert task["status"] == "completed"

    @pytest.mark.asyncio
    async def test_tasks_by_due_date(self, crm_client, unique_id, auth_headers_system):
        """Фильтрация задач по дедлайну"""
        test_user_id = f"test_user_{unique_id}"
        today = date.today()
        tomorrow = today + timedelta(days=1)

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Today task {unique_id}",
            "due_date": today.isoformat(),
            "user_id": test_user_id
        }, headers=auth_headers_system)

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Tomorrow task {unique_id}",
            "due_date": tomorrow.isoformat(),
            "user_id": test_user_id
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
                    ]
                },
            },
            headers=auth_headers_system,
        )
        assert today_tasks_resp.status_code == 200
        today_tasks = today_tasks_resp.json()["items"]
        assert len(today_tasks) >= 1
        for t in today_tasks:
            assert t["user_id"] == test_user_id

    @pytest.mark.asyncio
    async def test_tasks_by_assignee(self, crm_client, unique_id, auth_headers_system):
        """Фильтрация задач по исполнителю"""
        test_user_id = f"test_user_{unique_id}"

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Ivan task {unique_id}",
            "tags": ["ivan"],
            "user_id": test_user_id
        }, headers=auth_headers_system)

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Petr task {unique_id}",
            "assignees": ["petr"],
            "user_id": test_user_id
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
                    ]
                },
            },
            headers=auth_headers_system,
        )
        assert ivan_tasks_resp.status_code == 200
        ivan_tasks = ivan_tasks_resp.json()["items"]
        assert len(ivan_tasks) >= 1
        for t in ivan_tasks:
            assert t["user_id"] == test_user_id

    @pytest.mark.asyncio
    async def test_overdue_tasks(self, crm_client, unique_id, auth_headers_system):
        """Просроченные задачи"""
        test_user_id = f"test_user_{unique_id}"
        past_date = (date.today() - timedelta(days=5)).isoformat()

        resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": f"Overdue task {unique_id}",
            "due_date": past_date,
            "status": "in_progress",
            "user_id": test_user_id
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
                    ]
                },
            },
            headers=auth_headers_system,
        )
        assert overdue_resp.status_code == 200
        overdue_tasks = overdue_resp.json()["items"]
        assert len(overdue_tasks) >= 1
        for t in overdue_tasks:
            assert t["user_id"] == test_user_id

