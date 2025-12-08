"""
API тесты для confirm-entities endpoint.

Тестируем:
- POST /crm/api/v1/notes/{note_id}/confirm-entities
"""

import pytest
import pytest_asyncio
from datetime import date

from apps.crm.db.models import Note


@pytest_asyncio.fixture
async def api_meeting_note(crm_container, session_test_data):
    """Создает meeting_minutes заметку для API тестов"""
    import uuid
    from datetime import datetime, timezone
    
    user = session_test_data["user"]
    company = session_test_data["company"]
    
    note = Note(
        note_id=f"api_meeting_{uuid.uuid4().hex[:8]}",
        company_id=company.company_id,
        user_id=user.user_id,
        title="API Test Meeting",
        content="Meeting with team members: Alice, Bob from TechCorp.",
        note_type="meeting_minutes",
        note_date=date.today(),
        ai_summary="Team sync meeting",
        visibility="public",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await crm_container.note_repository.create(note)
    yield note
    
    try:
        await crm_container.note_repository.delete(note.note_id)
    except Exception:
        pass


@pytest_asyncio.fixture
async def api_freeform_note(crm_container, session_test_data):
    """Создает freeform заметку для API тестов"""
    import uuid
    from datetime import datetime, timezone
    
    user = session_test_data["user"]
    company = session_test_data["company"]
    
    note = Note(
        note_id=f"api_freeform_{uuid.uuid4().hex[:8]}",
        company_id=company.company_id,
        user_id=user.user_id,
        title="API Test Freeform Note",
        content="Random thoughts and ideas.",
        note_type="freeform",
        note_date=date.today(),
        visibility="public",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await crm_container.note_repository.create(note)
    yield note
    
    try:
        await crm_container.note_repository.delete(note.note_id)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_confirm_entities_success(crm_client, api_meeting_note, crm_container):
    """Тест успешного подтверждения сущностей"""
    payload = {
        "entities": [
            {
                "type": "person",
                "name": "Alice",
                "description": "Team member",
                "attributes": {"position": "Developer"},
            },
        ],
        "relationships": [],
        "create_event": True,
        "link_author": False,
    }
    
    response = await crm_client.post(
        f"/crm/api/v1/notes/{api_meeting_note.note_id}/confirm-entities",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "created_entities" in data
    assert "created_relationships" in data
    assert "event_entity" in data
    assert "linked_entity_ids" in data
    
    # Должен быть создан event для meeting_minutes
    assert data["event_entity"] is not None
    assert data["event_entity"]["type"] == "meeting"
    
    # Cleanup
    for rel in data.get("created_relationships", []):
        try:
            await crm_container.relationship_service.delete_relationship(rel["relationship_id"])
        except Exception:
            pass
    for entity in data.get("created_entities", []):
        try:
            await crm_container.entity_service.delete_entity(entity["entity_id"])
        except Exception:
            pass


@pytest.mark.asyncio
async def test_confirm_entities_with_relationships(crm_client, api_meeting_note, crm_container):
    """Тест подтверждения с созданием связей"""
    payload = {
        "entities": [
            {
                "type": "person",
                "name": "Alice",
                "attributes": {},
            },
            {
                "type": "organization",
                "name": "TechCorp",
                "attributes": {},
            },
        ],
        "relationships": [
            {
                "source_index": 0,
                "target_index": 1,
                "relationship_type": "works_for",
                "weight": 1.0,
                "attributes": {},
            },
        ],
        "create_event": False,
        "link_author": False,
    }
    
    response = await crm_client.post(
        f"/crm/api/v1/notes/{api_meeting_note.note_id}/confirm-entities",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["created_entities"]) == 2
    assert len(data["created_relationships"]) == 1
    
    rel = data["created_relationships"][0]
    assert rel["relationship_type"] == "works_for"
    
    # Cleanup
    for rel in data.get("created_relationships", []):
        try:
            await crm_container.relationship_service.delete_relationship(rel["relationship_id"])
        except Exception:
            pass
    for entity in data.get("created_entities", []):
        try:
            await crm_container.entity_service.delete_entity(entity["entity_id"])
        except Exception:
            pass


@pytest.mark.asyncio
async def test_confirm_entities_no_event_for_freeform(crm_client, api_freeform_note, crm_container):
    """Тест: event не создается для freeform заметки"""
    payload = {
        "entities": [
            {
                "type": "person",
                "name": "Test Person",
                "attributes": {},
            },
        ],
        "relationships": [],
        "create_event": True,
        "link_author": False,
    }
    
    response = await crm_client.post(
        f"/crm/api/v1/notes/{api_freeform_note.note_id}/confirm-entities",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Event НЕ должен быть создан
    assert data["event_entity"] is None
    
    # Cleanup
    for entity in data.get("created_entities", []):
        try:
            await crm_container.entity_service.delete_entity(entity["entity_id"])
        except Exception:
            pass


@pytest.mark.asyncio
async def test_confirm_entities_empty_request(crm_client, api_meeting_note):
    """Тест пустого запроса"""
    payload = {
        "entities": [],
        "relationships": [],
        "create_event": False,
        "link_author": False,
    }
    
    response = await crm_client.post(
        f"/crm/api/v1/notes/{api_meeting_note.note_id}/confirm-entities",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["created_entities"]) == 0
    assert len(data["created_relationships"]) == 0
    assert data["event_entity"] is None


@pytest.mark.asyncio
async def test_confirm_entities_nonexistent_note(crm_client):
    """Тест ошибки для несуществующей заметки"""
    payload = {
        "entities": [],
        "relationships": [],
        "create_event": False,
        "link_author": False,
    }
    
    response = await crm_client.post(
        "/crm/api/v1/notes/nonexistent_note_id/confirm-entities",
        json=payload,
    )
    
    # Ожидаем ошибку (500 или 404)
    assert response.status_code in [404, 500, 422]


@pytest.mark.asyncio
async def test_confirm_entities_links_to_note(crm_client, api_meeting_note, crm_container):
    """Тест: сущности линкуются к заметке"""
    payload = {
        "entities": [
            {
                "type": "person",
                "name": "Alice",
                "attributes": {},
            },
            {
                "type": "person",
                "name": "Bob",
                "attributes": {},
            },
        ],
        "relationships": [],
        "create_event": True,
        "link_author": False,
    }
    
    response = await crm_client.post(
        f"/crm/api/v1/notes/{api_meeting_note.note_id}/confirm-entities",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Проверяем linked_entity_ids
    assert len(data["linked_entity_ids"]) > 0
    
    # Получаем заметку и проверяем linked_entity_ids
    note_response = await crm_client.get(f"/crm/api/v1/notes/{api_meeting_note.note_id}")
    assert note_response.status_code == 200
    note_data = note_response.json()
    
    # Все entity_ids должны быть в linked_entity_ids заметки
    for entity_id in data["linked_entity_ids"]:
        assert entity_id in note_data["linked_entity_ids"]
    
    # Cleanup
    for rel in data.get("created_relationships", []):
        try:
            await crm_container.relationship_service.delete_relationship(rel["relationship_id"])
        except Exception:
            pass
    for entity in data.get("created_entities", []):
        try:
            await crm_container.entity_service.delete_entity(entity["entity_id"])
        except Exception:
            pass


@pytest.mark.asyncio
async def test_confirm_entities_participates_in_event(crm_client, api_meeting_note, crm_container):
    """Тест: person связывается с event через participated_in"""
    payload = {
        "entities": [
            {
                "type": "person",
                "name": "Alice",
                "attributes": {},
            },
        ],
        "relationships": [],
        "create_event": True,
        "link_author": False,
    }
    
    response = await crm_client.post(
        f"/crm/api/v1/notes/{api_meeting_note.note_id}/confirm-entities",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Должна быть связь participated_in
    event_id = data["event_entity"]["entity_id"]
    participated_in_rels = [
        r for r in data["created_relationships"]
        if r["target_entity_id"] == event_id and r["relationship_type"] == "participated_in"
    ]
    
    assert len(participated_in_rels) == 1
    
    # Cleanup
    for rel in data.get("created_relationships", []):
        try:
            await crm_container.relationship_service.delete_relationship(rel["relationship_id"])
        except Exception:
            pass
    for entity in data.get("created_entities", []):
        try:
            await crm_container.entity_service.delete_entity(entity["entity_id"])
        except Exception:
            pass


@pytest.mark.asyncio
async def test_confirm_entities_response_structure(crm_client, api_meeting_note, crm_container):
    """Тест структуры ответа"""
    payload = {
        "entities": [
            {
                "type": "person",
                "name": "Test Person",
                "description": "Test description",
                "ai_description": "AI generated description",
                "attributes": {"email": "test@example.com"},
            },
        ],
        "relationships": [],
        "create_event": True,
        "link_author": False,
    }
    
    response = await crm_client.post(
        f"/crm/api/v1/notes/{api_meeting_note.note_id}/confirm-entities",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Проверяем структуру created_entities
    assert len(data["created_entities"]) >= 1
    entity = next(e for e in data["created_entities"] if e["type"] == "person")
    
    assert "entity_id" in entity
    assert entity["name"] == "Test Person"
    assert entity["type"] == "person"
    
    # Проверяем структуру event_entity
    assert data["event_entity"] is not None
    assert "entity_id" in data["event_entity"]
    assert data["event_entity"]["type"] == "meeting"
    
    # Cleanup
    for rel in data.get("created_relationships", []):
        try:
            await crm_container.relationship_service.delete_relationship(rel["relationship_id"])
        except Exception:
            pass
    for entity in data.get("created_entities", []):
        try:
            await crm_container.entity_service.delete_entity(entity["entity_id"])
        except Exception:
            pass

