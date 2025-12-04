"""
API тесты для Notes.
"""

import pytest
from datetime import date


@pytest.mark.asyncio
async def test_list_notes(crm_client):
    """Тест получения списка заметок"""
    response = await crm_client.get("/crm/api/v1/notes")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_note(crm_client, unique_crm_id):
    """Тест создания заметки"""
    payload = {
        "title": "API Test Note",
        "content": "This is a test note created via API",
        "note_type": "freeform",
        "note_date": str(date.today()),
    }
    
    response = await crm_client.post("/crm/api/v1/notes", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "API Test Note"
    assert data["content"] == "This is a test note created via API"
    assert data["note_type"] == "freeform"
    
    await crm_client.delete(f"/crm/api/v1/notes/{data['note_id']}")


@pytest.mark.asyncio
async def test_get_note(crm_client, unique_crm_id):
    """Тест получения заметки по ID"""
    payload = {
        "title": "Get Test Note",
        "content": "Content for get test",
        "note_type": "meeting_minutes",
        "note_date": str(date.today()),
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get(f"/crm/api/v1/notes/{note_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Get Test Note"
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_get_nonexistent_note(crm_client, unique_crm_id):
    """Тест получения несуществующей заметки"""
    fake_id = unique_crm_id("fake")
    
    response = await crm_client.get(f"/crm/api/v1/notes/{fake_id}")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_note(crm_client, unique_crm_id):
    """Тест обновления заметки"""
    payload = {
        "title": "Original Title",
        "content": "Original content",
        "note_type": "freeform",
        "note_date": str(date.today()),
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    update_payload = {
        "title": "Updated Title",
        "content": "Updated content",
    }
    response = await crm_client.put(f"/crm/api/v1/notes/{note_id}", json=update_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["content"] == "Updated content"
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_delete_note(crm_client, unique_crm_id):
    """Тест удаления заметки"""
    payload = {
        "title": "To Delete",
        "content": "This will be deleted",
        "note_type": "freeform",
        "note_date": str(date.today()),
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.delete(f"/crm/api/v1/notes/{note_id}")
    
    assert response.status_code == 200
    
    get_response = await crm_client.get(f"/crm/api/v1/notes/{note_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_get_daily_notes(crm_client, unique_crm_id):
    """Тест получения заметок по дате"""
    today = str(date.today())
    
    payload = {
        "title": "Daily Note",
        "content": "Note for today",
        "note_type": "freeform",
        "note_date": today,
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get(f"/crm/api/v1/notes/daily/{today}")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    note_ids = [n["note_id"] for n in data]
    assert note_id in note_ids
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_list_notes_by_type(crm_client, unique_crm_id):
    """Тест фильтрации заметок по типу"""
    payload = {
        "title": "Call Log Note",
        "content": "Call log content",
        "note_type": "call_log",
        "note_date": str(date.today()),
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get("/crm/api/v1/notes?note_type=call_log")
    
    assert response.status_code == 200
    data = response.json()
    
    for note in data:
        assert note["note_type"] == "call_log"
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_search_notes(crm_client, unique_crm_id):
    """Тест поиска по заметкам"""
    unique_content = f"unique_search_term_{unique_crm_id('search')}"
    
    payload = {
        "title": "Searchable Note",
        "content": f"This note contains {unique_content}",
        "note_type": "freeform",
        "note_date": str(date.today()),
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get(f"/crm/api/v1/notes?search={unique_content}")
    
    assert response.status_code == 200
    data = response.json()
    
    note_ids = [n["note_id"] for n in data]
    assert note_id in note_ids
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

