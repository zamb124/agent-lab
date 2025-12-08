"""
API тесты для Tasks.
"""

import pytest
from datetime import date, timedelta


@pytest.mark.asyncio
async def test_list_tasks(crm_client):
    """Тест получения списка задач"""
    response = await crm_client.get("/crm/api/v1/tasks")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_task(crm_client, unique_id):
    """Тест создания задачи"""
    payload = {
        "title": "API Test Task",
        "description": "Created via API test",
        "priority": "high",
        "due_date": str(date.today() + timedelta(days=7)),
    }
    
    response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "API Test Task"
    assert data["priority"] == "high"
    assert data["status"] == "pending"
    
    await crm_client.delete(f"/crm/api/v1/tasks/{data['task_id']}")


@pytest.mark.asyncio
async def test_get_task(crm_client, unique_id):
    """Тест получения задачи по ID"""
    payload = {
        "title": "Get Test Task",
        "description": "Task for get test",
        "priority": "medium",
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.get(f"/crm/api/v1/tasks/{task_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Get Test Task"
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_get_nonexistent_task(crm_client, unique_id):
    """Тест получения несуществующей задачи"""
    fake_id = unique_id("fake")
    
    response = await crm_client.get(f"/crm/api/v1/tasks/{fake_id}")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_task(crm_client, unique_id):
    """Тест обновления задачи"""
    payload = {
        "title": "Original Task",
        "priority": "low",
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    update_payload = {
        "title": "Updated Task",
        "priority": "urgent",
        "status": "in_progress",
    }
    response = await crm_client.put(f"/crm/api/v1/tasks/{task_id}", json=update_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Task"
    assert data["priority"] == "urgent"
    assert data["status"] == "in_progress"
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_delete_task(crm_client, unique_id):
    """Тест удаления задачи"""
    payload = {
        "title": "To Delete",
        "priority": "low",
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")
    
    assert response.status_code == 200
    
    get_response = await crm_client.get(f"/crm/api/v1/tasks/{task_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_get_my_tasks(crm_client, unique_id):
    """Тест получения моих задач"""
    payload = {
        "title": "My Task",
        "priority": "high",
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.get("/crm/api/v1/tasks/my")
    
    assert response.status_code == 200
    data = response.json()
    
    task_ids = [t["task_id"] for t in data]
    assert task_id in task_ids
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_get_overdue_tasks(crm_client, unique_id):
    """Тест получения просроченных задач"""
    payload = {
        "title": "Overdue Task",
        "priority": "high",
        "due_date": str(date.today() - timedelta(days=1)),
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.get("/crm/api/v1/tasks/overdue")
    
    assert response.status_code == 200
    data = response.json()
    
    task_ids = [t["task_id"] for t in data]
    assert task_id in task_ids
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_complete_task(crm_client, unique_id):
    """Тест завершения задачи"""
    payload = {
        "title": "To Complete",
        "priority": "medium",
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.post(f"/crm/api/v1/tasks/{task_id}/complete")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_list_tasks_with_status_filter(crm_client, unique_id):
    """Тест фильтрации задач по статусу"""
    payload = {
        "title": "Pending Task",
        "priority": "low",
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.get("/crm/api/v1/tasks?status=pending")
    
    assert response.status_code == 200
    data = response.json()
    
    for task in data:
        assert task["status"] == "pending"
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_list_tasks_with_priority_filter(crm_client, unique_id):
    """Тест фильтрации задач по приоритету"""
    payload = {
        "title": "Urgent Task",
        "priority": "urgent",
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.get("/crm/api/v1/tasks?priority=urgent")
    
    assert response.status_code == 200
    data = response.json()
    
    for task in data:
        assert task["priority"] == "urgent"
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_cancel_task(crm_client, unique_id):
    """Тест отмены задачи"""
    payload = {
        "title": f"To Cancel {unique_id('cancel')}",
        "priority": "medium",
        "status": "pending",
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.post(f"/crm/api/v1/tasks/{task_id}/cancel")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_cancel_nonexistent_task(crm_client, unique_id):
    """Тест отмены несуществующей задачи"""
    fake_id = unique_id("fake")
    
    response = await crm_client.post(f"/crm/api/v1/tasks/{fake_id}/cancel")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_tasks_by_entity(crm_client, unique_id):
    """Тест получения задач по связанной сущности"""
    entity_id = unique_id("entity")
    
    payload = {
        "title": f"Entity Task {unique_id('task')}",
        "description": "Task linked to entity",
        "priority": "high",
        "linked_entity_id": entity_id,
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.get(f"/crm/api/v1/tasks/entity/{entity_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    task_ids = [t["task_id"] for t in data]
    assert task_id in task_ids
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_get_tasks_by_entity_empty(crm_client, unique_id):
    """Тест получения задач для сущности без задач"""
    fake_entity_id = unique_id("fake_entity")
    
    response = await crm_client.get(f"/crm/api/v1/tasks/entity/{fake_entity_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_get_due_today(crm_client, unique_id):
    """Тест получения задач с дедлайном сегодня"""
    payload = {
        "title": f"Today Task {unique_id('today')}",
        "priority": "high",
        "due_date": str(date.today()),
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.get("/crm/api/v1/tasks/due-today")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    task_ids = [t["task_id"] for t in data]
    assert task_id in task_ids
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_get_due_this_week(crm_client, unique_id):
    """Тест получения задач на эту неделю"""
    # Задача на завтра (в пределах недели)
    payload = {
        "title": f"Week Task {unique_id('week')}",
        "priority": "medium",
        "due_date": str(date.today() + timedelta(days=1)),
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.get("/crm/api/v1/tasks/due-this-week")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_get_task_stats(crm_client, unique_id):
    """Тест получения статистики задач"""
    payload = {
        "title": f"Stats Task {unique_id('stats')}",
        "priority": "low",
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.get("/crm/api/v1/tasks/stats")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    
    # Должны быть поля статистики
    assert "pending" in data or "total" in data or len(data) > 0
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")
