"""
API тесты для расширенного функционала Tasks.
Тестируем: tags, assignees.
"""

import pytest
from datetime import date, timedelta


@pytest.mark.asyncio
async def test_create_task_with_tags(crm_client, unique_id):
    """Тест создания задачи с тегами через API"""
    payload = {
        "title": "Tagged Task",
        "description": "Task with tags",
        "priority": "high",
        "due_date": str(date.today() + timedelta(days=7)),
        "tags": ["urgent", "client", "follow-up"],
    }
    
    response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "urgent" in data["tags"]
    assert "client" in data["tags"]
    assert "follow-up" in data["tags"]
    
    await crm_client.delete(f"/crm/api/v1/tasks/{data['task_id']}")


@pytest.mark.asyncio
async def test_create_task_with_assignees(crm_client, unique_id):
    """Тест создания задачи с соучастниками через API"""
    assignee_1 = unique_id("user1")
    assignee_2 = unique_id("user2")
    
    payload = {
        "title": "Shared Task",
        "description": "Task with assignees",
        "priority": "medium",
        "due_date": str(date.today() + timedelta(days=3)),
        "assignees": [assignee_1, assignee_2],
    }
    
    response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert assignee_1 in data["assignees"]
    assert assignee_2 in data["assignees"]
    
    await crm_client.delete(f"/crm/api/v1/tasks/{data['task_id']}")


@pytest.mark.asyncio
async def test_update_task_tags(crm_client, unique_id):
    """Тест обновления тегов задачи через API"""
    payload = {
        "title": "Update Tags Task",
        "priority": "low",
        "tags": ["initial"],
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    update_payload = {"tags": ["updated", "new-tag"]}
    response = await crm_client.put(f"/crm/api/v1/tasks/{task_id}", json=update_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "updated" in data["tags"]
    assert "new-tag" in data["tags"]
    assert "initial" not in data["tags"]
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_update_task_assignees(crm_client, unique_id):
    """Тест обновления соучастников задачи через API"""
    old_assignee = unique_id("old")
    new_assignee = unique_id("new")
    
    payload = {
        "title": "Update Assignees Task",
        "priority": "medium",
        "assignees": [old_assignee],
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    update_payload = {"assignees": [new_assignee]}
    response = await crm_client.put(f"/crm/api/v1/tasks/{task_id}", json=update_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert new_assignee in data["assignees"]
    assert old_assignee not in data["assignees"]
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_add_tag_to_task(crm_client, unique_id):
    """Тест добавления тега к задаче через API endpoint"""
    payload = {
        "title": "Add Tag API Test",
        "priority": "medium",
        "tags": ["existing"],
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.post(f"/crm/api/v1/tasks/{task_id}/tags/new-tag")
    
    assert response.status_code == 200
    data = response.json()
    assert "existing" in data["tags"]
    assert "new-tag" in data["tags"]
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_add_tag_idempotent(crm_client, unique_id):
    """Тест что добавление тега идемпотентно"""
    payload = {
        "title": "Idempotent Tag Test",
        "priority": "medium",
        "tags": ["existing"],
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    await crm_client.post(f"/crm/api/v1/tasks/{task_id}/tags/existing")
    response = await crm_client.post(f"/crm/api/v1/tasks/{task_id}/tags/existing")
    
    assert response.status_code == 200
    data = response.json()
    assert data["tags"].count("existing") == 1
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_remove_tag_from_task(crm_client, unique_id):
    """Тест удаления тега из задачи через API endpoint"""
    payload = {
        "title": "Remove Tag API Test",
        "priority": "medium",
        "tags": ["keep", "remove"],
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.delete(f"/crm/api/v1/tasks/{task_id}/tags/remove")
    
    assert response.status_code == 200
    data = response.json()
    assert "keep" in data["tags"]
    assert "remove" not in data["tags"]
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_add_assignee_to_task(crm_client, unique_id):
    """Тест добавления соучастника через API endpoint"""
    existing = unique_id("existing")
    new_user = unique_id("new")
    
    payload = {
        "title": "Add Assignee API Test",
        "priority": "medium",
        "assignees": [existing],
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.post(f"/crm/api/v1/tasks/{task_id}/assignees/{new_user}")
    
    assert response.status_code == 200
    data = response.json()
    assert existing in data["assignees"]
    assert new_user in data["assignees"]
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_remove_assignee_from_task(crm_client, unique_id):
    """Тест удаления соучастника через API endpoint"""
    keep_user = unique_id("keep")
    remove_user = unique_id("remove")
    
    payload = {
        "title": "Remove Assignee API Test",
        "priority": "medium",
        "assignees": [keep_user, remove_user],
    }
    
    create_response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    task_id = create_response.json()["task_id"]
    
    response = await crm_client.delete(f"/crm/api/v1/tasks/{task_id}/assignees/{remove_user}")
    
    assert response.status_code == 200
    data = response.json()
    assert keep_user in data["assignees"]
    assert remove_user not in data["assignees"]
    
    await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_get_tasks_by_tag(crm_client, unique_id):
    """Тест получения задач по тегу через API"""
    unique_tag = unique_id("tag")
    created_ids = []
    
    for i in range(2):
        payload = {
            "title": f"Tagged Task {i}",
            "priority": "medium",
            "tags": [unique_tag, "common"],
        }
        response = await crm_client.post("/crm/api/v1/tasks", json=payload)
        created_ids.append(response.json()["task_id"])
    
    response = await crm_client.get(f"/crm/api/v1/tasks/tag/{unique_tag}")
    
    assert response.status_code == 200
    data = response.json()
    
    task_ids = [t["task_id"] for t in data]
    for created_id in created_ids:
        assert created_id in task_ids
    
    for task_id in created_ids:
        await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_get_tasks_by_assignee(crm_client, unique_id):
    """Тест получения задач по соучастнику через API"""
    assignee = unique_id("assignee")
    created_ids = []
    
    for i in range(2):
        payload = {
            "title": f"Assigned Task {i}",
            "priority": "medium",
            "assignees": [assignee],
        }
        response = await crm_client.post("/crm/api/v1/tasks", json=payload)
        created_ids.append(response.json()["task_id"])
    
    response = await crm_client.get(f"/crm/api/v1/tasks/assignee/{assignee}")
    
    assert response.status_code == 200
    data = response.json()
    
    task_ids = [t["task_id"] for t in data]
    for created_id in created_ids:
        assert created_id in task_ids
    
    for task_id in created_ids:
        await crm_client.delete(f"/crm/api/v1/tasks/{task_id}")


@pytest.mark.asyncio
async def test_task_with_tags_and_assignees(crm_client, unique_id):
    """Тест создания задачи с тегами и соучастниками одновременно"""
    assignee = unique_id("assignee")
    
    payload = {
        "title": "Full Task",
        "priority": "urgent",
        "due_date": str(date.today() + timedelta(days=1)),
        "tags": ["important", "meeting"],
        "assignees": [assignee],
    }
    
    response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "important" in data["tags"]
    assert "meeting" in data["tags"]
    assert assignee in data["assignees"]
    
    await crm_client.delete(f"/crm/api/v1/tasks/{data['task_id']}")


@pytest.mark.asyncio
async def test_empty_tags_default(crm_client, unique_id):
    """Тест что tags по умолчанию пустой список"""
    payload = {
        "title": "No Tags Task",
        "priority": "low",
    }
    
    response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["tags"] == []
    
    await crm_client.delete(f"/crm/api/v1/tasks/{data['task_id']}")


@pytest.mark.asyncio
async def test_empty_assignees_default(crm_client, unique_id):
    """Тест что assignees по умолчанию пустой список"""
    payload = {
        "title": "No Assignees Task",
        "priority": "low",
    }
    
    response = await crm_client.post("/crm/api/v1/tasks", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["assignees"] == []
    
    await crm_client.delete(f"/crm/api/v1/tasks/{data['task_id']}")

