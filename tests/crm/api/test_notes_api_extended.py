"""
API тесты для расширенного функционала Notes.
Тестируем: templates, visibility, attachments, filtering.
"""

import pytest
from datetime import date, timedelta


@pytest.mark.asyncio
async def test_create_note_with_template_flag(crm_client, unique_id):
    """Тест создания заметки-шаблона через API"""
    payload = {
        "title": "Meeting Template",
        "content": "## Agenda\n\n## Participants\n\n## Actions",
        "note_type": "meeting_minutes",
        "note_date": str(date.today()),
        "is_template": True,
    }
    
    response = await crm_client.post("/crm/api/v1/notes", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_template"] is True
    assert data["title"] == "Meeting Template"
    
    await crm_client.delete(f"/crm/api/v1/notes/{data['note_id']}")


@pytest.mark.asyncio
async def test_get_templates(crm_client, unique_id):
    """Тест получения списка шаблонов"""
    payload = {
        "title": "API Template",
        "content": "Template content",
        "note_type": "freeform",
        "note_date": str(date.today()),
        "is_template": True,
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get("/crm/api/v1/notes/templates")
    
    assert response.status_code == 200
    data = response.json()
    
    for note in data:
        assert note["is_template"] is True
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_get_templates_by_type(crm_client, unique_id):
    """Тест получения шаблонов по типу"""
    payload = {
        "title": "Call Template",
        "content": "## Summary\n\n## Follow-up",
        "note_type": "call_log",
        "note_date": str(date.today()),
        "is_template": True,
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get("/crm/api/v1/notes/templates?note_type=call_log")
    
    assert response.status_code == 200
    data = response.json()
    
    for note in data:
        assert note["is_template"] is True
        assert note["note_type"] == "call_log"
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_create_from_template(crm_client, unique_id):
    """Тест создания заметки из шаблона"""
    template_payload = {
        "title": "Standup Template",
        "content": "## Done\n\n## Todo\n\n## Blockers",
        "note_type": "meeting_minutes",
        "note_date": str(date.today()),
        "is_template": True,
    }
    
    template_response = await crm_client.post("/crm/api/v1/notes", json=template_payload)
    template_id = template_response.json()["note_id"]
    
    response = await crm_client.post(f"/crm/api/v1/notes/from-template/{template_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Standup Template"
    assert data["content"] == "## Done\n\n## Todo\n\n## Blockers"
    assert data["is_template"] is False
    assert data["status"] == "draft"
    
    await crm_client.delete(f"/crm/api/v1/notes/{data['note_id']}")
    await crm_client.delete(f"/crm/api/v1/notes/{template_id}")


@pytest.mark.asyncio
async def test_create_note_with_status(crm_client, unique_id):
    """Тест создания заметки со статусом draft"""
    payload = {
        "title": "Draft Note",
        "content": "Work in progress",
        "note_type": "freeform",
        "note_date": str(date.today()),
        "status": "draft",
    }
    
    response = await crm_client.post("/crm/api/v1/notes", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "draft"
    
    await crm_client.delete(f"/crm/api/v1/notes/{data['note_id']}")


@pytest.mark.asyncio
async def test_update_note_status(crm_client, unique_id):
    """Тест обновления статуса заметки"""
    payload = {
        "title": "Status Update Test",
        "content": "Content",
        "note_type": "freeform",
        "note_date": str(date.today()),
        "status": "draft",
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    update_payload = {"status": "published"}
    response = await crm_client.put(f"/crm/api/v1/notes/{note_id}", json=update_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "published"
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_create_note_with_visibility(crm_client, unique_id):
    """Тест создания заметки с visibility"""
    shared_user = unique_id("user")
    
    payload = {
        "title": "Shared Note",
        "content": "Sensitive content",
        "note_type": "freeform",
        "note_date": str(date.today()),
        "visibility": "shared",
        "shared_with": [shared_user],
    }
    
    response = await crm_client.post("/crm/api/v1/notes", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["visibility"] == "shared"
    assert shared_user in data["shared_with"]
    
    await crm_client.delete(f"/crm/api/v1/notes/{data['note_id']}")


@pytest.mark.asyncio
async def test_create_note_with_attachments(crm_client, unique_id):
    """Тест создания заметки с прикрепленными файлами"""
    file_id = unique_id("file")
    
    payload = {
        "title": "Note with Files",
        "content": "Has attachments",
        "note_type": "meeting_minutes",
        "note_date": str(date.today()),
        "attachment_ids": [file_id],
    }
    
    response = await crm_client.post("/crm/api/v1/notes", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert file_id in data["attachment_ids"]
    
    await crm_client.delete(f"/crm/api/v1/notes/{data['note_id']}")


@pytest.mark.asyncio
async def test_filter_notes_by_user(crm_client, unique_id):
    """Тест фильтрации заметок по пользователю"""
    payload = {
        "title": "User Filter Test",
        "content": "Content",
        "note_type": "freeform",
        "note_date": str(date.today()),
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note = create_response.json()
    
    response = await crm_client.get(f"/crm/api/v1/notes?user_id={note['user_id']}")
    
    assert response.status_code == 200
    data = response.json()
    
    for n in data:
        assert n["user_id"] == note["user_id"]
    
    await crm_client.delete(f"/crm/api/v1/notes/{note['note_id']}")


@pytest.mark.asyncio
async def test_filter_notes_by_date_range(crm_client, unique_id):
    """Тест фильтрации заметок по диапазону дат"""
    today = date.today()
    start = today - timedelta(days=1)
    end = today + timedelta(days=1)
    
    payload = {
        "title": "Date Range Test",
        "content": "Content",
        "note_type": "freeform",
        "note_date": str(today),
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get(f"/crm/api/v1/notes?start_date={start}&end_date={end}")
    
    assert response.status_code == 200
    data = response.json()
    
    note_ids = [n["note_id"] for n in data]
    assert note_id in note_ids
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_filter_notes_by_entity(crm_client, unique_id):
    """Тест фильтрации заметок по связанной сущности"""
    entity_id = unique_id("entity")
    
    payload = {
        "title": "Entity Filter Test",
        "content": "Content",
        "note_type": "freeform",
        "note_date": str(date.today()),
        "linked_entity_ids": [entity_id],
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get(f"/crm/api/v1/notes?entity_id={entity_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    note_ids = [n["note_id"] for n in data]
    assert note_id in note_ids
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_filter_notes_by_search(crm_client, unique_id):
    """Тест поиска заметок по тексту"""
    unique_text = unique_id("search_text")
    
    payload = {
        "title": "Search Test",
        "content": f"Contains {unique_text} for search",
        "note_type": "freeform",
        "note_date": str(date.today()),
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get(f"/crm/api/v1/notes?q={unique_text}")
    
    assert response.status_code == 200
    data = response.json()
    
    note_ids = [n["note_id"] for n in data]
    assert note_id in note_ids
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_link_entity_to_note(crm_client, unique_id):
    """Тест связывания сущности с заметкой"""
    payload = {
        "title": "Link Test",
        "content": "Content",
        "note_type": "freeform",
        "note_date": str(date.today()),
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    entity_id = unique_id("entity")
    
    response = await crm_client.post(f"/crm/api/v1/notes/{note_id}/link/{entity_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert entity_id in data["linked_entity_ids"]
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_unlink_entity_from_note(crm_client, unique_id):
    """Тест отвязывания сущности от заметки"""
    entity_id = unique_id("entity")
    
    payload = {
        "title": "Unlink Test",
        "content": "Content",
        "note_type": "freeform",
        "note_date": str(date.today()),
        "linked_entity_ids": [entity_id],
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.delete(f"/crm/api/v1/notes/{note_id}/link/{entity_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert entity_id not in data["linked_entity_ids"]
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

