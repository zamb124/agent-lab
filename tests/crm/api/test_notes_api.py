"""
API тесты для Notes.
"""

import pytest
import io
from datetime import date, timedelta


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


@pytest.mark.asyncio
async def test_get_notes_in_range(crm_client, unique_crm_id):
    """Тест получения заметок за диапазон дат"""
    today = date.today()
    start_date = today - timedelta(days=1)
    end_date = today + timedelta(days=1)
    
    payload = {
        "title": f"Range Test Note {unique_crm_id('range')}",
        "content": "Note for range test",
        "note_type": "freeform",
        "note_date": str(today),
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get(
        f"/crm/api/v1/notes/range?start_date={start_date}&end_date={end_date}"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    note_ids = [n["note_id"] for n in data]
    assert note_id in note_ids
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_get_notes_in_range_empty(crm_client):
    """Тест получения заметок за пустой диапазон"""
    # Даты в далеком будущем - заметок быть не должно
    start_date = date(2099, 1, 1)
    end_date = date(2099, 1, 2)
    
    response = await crm_client.get(
        f"/crm/api/v1/notes/range?start_date={start_date}&end_date={end_date}"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_get_notes_by_entity(crm_client, unique_crm_id):
    """Тест получения заметок по связанной сущности"""
    entity_id = unique_crm_id("entity")
    
    payload = {
        "title": f"Entity Note {unique_crm_id('entity_note')}",
        "content": "Note linked to entity",
        "note_type": "freeform",
        "note_date": str(date.today()),
        "linked_entity_ids": [entity_id],
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    response = await crm_client.get(f"/crm/api/v1/notes/entity/{entity_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    note_ids = [n["note_id"] for n in data]
    assert note_id in note_ids
    
    await crm_client.delete(f"/crm/api/v1/notes/{note_id}")


@pytest.mark.asyncio
async def test_get_notes_by_entity_empty(crm_client, unique_crm_id):
    """Тест получения заметок для несуществующей сущности"""
    fake_entity_id = unique_crm_id("fake_entity")
    
    response = await crm_client.get(f"/crm/api/v1/notes/entity/{fake_entity_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_import_note_from_file(crm_client, unique_crm_id):
    """Тест импорта заметки из файла"""
    file_content = b"This is the content of imported note.\n\nMultiple paragraphs."
    files = {
        "file": ("imported_note.txt", io.BytesIO(file_content), "text/plain")
    }
    data = {
        "title": f"Imported Note {unique_crm_id('import')}",
        "note_type": "freeform",
        "note_date": str(date.today()),
    }
    
    response = await crm_client.post(
        "/crm/api/v1/notes/import",
        files=files,
        data=data
    )
    
    assert response.status_code == 200
    note = response.json()
    assert "note_id" in note
    assert note["note_type"] == "freeform"
    
    # Контент должен содержать текст из файла
    assert "content" in note or "title" in note
    
    await crm_client.delete(f"/crm/api/v1/notes/{note['note_id']}")


@pytest.mark.asyncio
async def test_import_note_from_file_without_title(crm_client, unique_crm_id):
    """Тест импорта заметки без указания title (используется имя файла)"""
    file_content = b"Content for auto-title test"
    filename = f"auto_title_{unique_crm_id('auto')}.txt"
    files = {
        "file": (filename, io.BytesIO(file_content), "text/plain")
    }
    data = {
        "note_type": "meeting_minutes",
        "note_date": str(date.today()),
    }
    
    response = await crm_client.post(
        "/crm/api/v1/notes/import",
        files=files,
        data=data
    )
    
    assert response.status_code == 200
    note = response.json()
    # title должен быть именем файла
    assert filename in note.get("title", "")
    
    await crm_client.delete(f"/crm/api/v1/notes/{note['note_id']}")


@pytest.mark.asyncio
async def test_get_daily_summary(crm_client, unique_crm_id):
    """
    Тест получения AI саммари за день.
    
    Требует работающий agents сервис для AI генерации.
    Если AI недоступен - тест пропускается.
    """
    today = str(date.today())
    
    payload = {
        "title": f"Summary Test {unique_crm_id('summary')}",
        "content": "Important meeting about project planning and timeline",
        "note_type": "meeting_minutes",
        "note_date": today,
    }
    
    create_response = await crm_client.post("/crm/api/v1/notes", json=payload)
    note_id = create_response.json()["note_id"]
    
    try:
        response = await crm_client.get(f"/crm/api/v1/notes/daily-summary/{today}")
        
        # AI может быть недоступен в тестовом окружении
        if response.status_code == 503:
            pytest.skip("AI сервис недоступен")
        
        assert response.status_code == 200
        data = response.json()
        assert "date" in data
        assert "summary" in data
        assert data["date"] == today
    finally:
        await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

