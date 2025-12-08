"""
Тесты для confirm_entities в NoteService.

Проверяем:
- Создание event сущности из заметки
- Создание сущностей при подтверждении
- Создание связей между сущностями
- Связывание автора с событием
- Линковка сущностей к заметке
"""

import pytest
import pytest_asyncio
from datetime import date, datetime, timezone

from apps.crm.db.models import Note
from apps.crm.models.note_models import (
    EntityConfirmItem,
    RelationshipConfirmItem,
    ConfirmEntitiesRequest,
)


@pytest_asyncio.fixture
async def meeting_note(test_context, note_repo, unique_id) -> Note:
    """Создает заметку типа meeting_minutes"""
    note_id = unique_id("meeting_note")
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Meeting with Client",
        content="Discussed project timeline. Attendees: John Smith (Tech Lead), Jane Doe (PM).",
        note_type="meeting_minutes",
        note_date=date.today(),
        ai_summary="Meeting about project timeline",
        linked_entity_ids=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await note_repo.create(note)
    yield note
    
    try:
        await note_repo.delete(note_id)
    except Exception:
        pass


@pytest_asyncio.fixture
async def call_note(test_context, note_repo, unique_id) -> Note:
    """Создает заметку типа call_log"""
    note_id = unique_id("call_note")
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Call with Investor",
        content="Discussed funding options.",
        note_type="call_log",
        note_date=date.today(),
        ai_summary="Call about funding",
        linked_entity_ids=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await note_repo.create(note)
    yield note
    
    try:
        await note_repo.delete(note_id)
    except Exception:
        pass


@pytest_asyncio.fixture
async def freeform_note(test_context, note_repo, unique_id) -> Note:
    """Создает заметку типа freeform"""
    note_id = unique_id("freeform_note")
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Random Notes",
        content="Some ideas and thoughts.",
        note_type="freeform",
        note_date=date.today(),
        linked_entity_ids=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    await note_repo.create(note)
    yield note
    
    try:
        await note_repo.delete(note_id)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_confirm_entities_creates_event_for_meeting(
    note_service,
    crm_container,
    meeting_note,
    test_context,
):
    """Тест: создается event сущность для meeting_minutes"""
    request = ConfirmEntitiesRequest(
        entities=[
            EntityConfirmItem(
                type="person",
                name="John Smith",
                description="Tech Lead",
                attributes={"position": "Tech Lead"},
            ),
        ],
        relationships=[],
        create_event=True,
        link_author=False,
    )
    
    result = await note_service.confirm_entities(
        meeting_note.note_id,
        request,
        company_id=test_context.active_company.company_id,
    )
    
    # Должен быть создан event
    assert result.event_entity is not None
    assert result.event_entity["type"] == "meeting"
    assert result.event_entity["name"] == meeting_note.title
    
    # Cleanup
    for entity in result.created_entities:
        await crm_container.entity_service.delete_entity(entity["entity_id"])


@pytest.mark.asyncio
async def test_confirm_entities_creates_event_for_call(
    note_service,
    crm_container,
    call_note,
    test_context,
):
    """Тест: создается event сущность для call_log"""
    request = ConfirmEntitiesRequest(
        entities=[],
        relationships=[],
        create_event=True,
        link_author=False,
    )
    
    result = await note_service.confirm_entities(
        call_note.note_id,
        request,
        company_id=test_context.active_company.company_id,
    )
    
    # Должен быть создан call event
    assert result.event_entity is not None
    assert result.event_entity["type"] == "call"
    
    # Cleanup
    if result.event_entity:
        await crm_container.entity_service.delete_entity(result.event_entity["entity_id"])


@pytest.mark.asyncio
async def test_confirm_entities_no_event_for_freeform(
    note_service,
    crm_container,
    freeform_note,
    test_context,
):
    """Тест: не создается event для freeform заметки"""
    request = ConfirmEntitiesRequest(
        entities=[
            EntityConfirmItem(
                type="person",
                name="Test Person",
                attributes={},
            ),
        ],
        relationships=[],
        create_event=True,
        link_author=False,
    )
    
    result = await note_service.confirm_entities(
        freeform_note.note_id,
        request,
        company_id=test_context.active_company.company_id,
    )
    
    # Event НЕ должен быть создан
    assert result.event_entity is None
    
    # Cleanup
    for entity in result.created_entities:
        await crm_container.entity_service.delete_entity(entity["entity_id"])


@pytest.mark.asyncio
async def test_confirm_entities_creates_entities(
    note_service,
    crm_container,
    meeting_note,
    test_context,
):
    """Тест: создаются подтвержденные сущности"""
    request = ConfirmEntitiesRequest(
        entities=[
            EntityConfirmItem(
                type="person",
                name="John Smith",
                description="Tech Lead from ACME",
                ai_description="Mentioned in meeting as tech lead",
                attributes={"position": "Tech Lead", "email": "john@acme.com"},
            ),
            EntityConfirmItem(
                type="organization",
                name="ACME Corp",
                description="Technology company",
                attributes={"industry": "tech"},
            ),
        ],
        relationships=[],
        create_event=False,
        link_author=False,
    )
    
    result = await note_service.confirm_entities(
        meeting_note.note_id,
        request,
        company_id=test_context.active_company.company_id,
    )
    
    # Должны быть созданы 2 сущности
    assert len(result.created_entities) == 2
    
    names = [e["name"] for e in result.created_entities]
    assert "John Smith" in names
    assert "ACME Corp" in names
    
    # Проверяем атрибуты
    john = next(e for e in result.created_entities if e["name"] == "John Smith")
    assert john["type"] == "person"
    assert john["attributes"]["position"] == "Tech Lead"
    
    # Cleanup
    for entity in result.created_entities:
        await crm_container.entity_service.delete_entity(entity["entity_id"])


@pytest.mark.asyncio
async def test_confirm_entities_creates_relationships(
    note_service,
    crm_container,
    meeting_note,
    test_context,
):
    """Тест: создаются связи между сущностями"""
    request = ConfirmEntitiesRequest(
        entities=[
            EntityConfirmItem(
                type="person",
                name="John Smith",
                attributes={},
            ),
            EntityConfirmItem(
                type="organization",
                name="ACME Corp",
                attributes={},
            ),
        ],
        relationships=[
            RelationshipConfirmItem(
                source_index=0,  # John Smith
                target_index=1,  # ACME Corp
                relationship_type="works_for",
                weight=1.0,
                attributes={"role": "employee"},
            ),
        ],
        create_event=False,
        link_author=False,
    )
    
    result = await note_service.confirm_entities(
        meeting_note.note_id,
        request,
        company_id=test_context.active_company.company_id,
    )
    
    # Должна быть создана 1 связь
    assert len(result.created_relationships) == 1
    
    rel = result.created_relationships[0]
    assert rel["relationship_type"] == "works_for"
    assert rel["weight"] == 1.0
    
    # Cleanup
    for rel in result.created_relationships:
        await crm_container.relationship_service.delete_relationship(rel["relationship_id"])
    for entity in result.created_entities:
        await crm_container.entity_service.delete_entity(entity["entity_id"])


@pytest.mark.asyncio
async def test_confirm_entities_links_to_event(
    note_service,
    crm_container,
    meeting_note,
    test_context,
):
    """Тест: сущности связываются с event через participated_in/mentioned_in"""
    request = ConfirmEntitiesRequest(
        entities=[
            EntityConfirmItem(
                type="person",
                name="John Smith",
                attributes={},
            ),
            EntityConfirmItem(
                type="organization",
                name="ACME Corp",
                attributes={},
            ),
        ],
        relationships=[],
        create_event=True,
        link_author=False,
    )
    
    result = await note_service.confirm_entities(
        meeting_note.note_id,
        request,
        company_id=test_context.active_company.company_id,
    )
    
    # Должны быть связи с event
    # 2 сущности + event = 2 связи (participated_in для person, mentioned_in для org)
    event_relationships = [
        r for r in result.created_relationships
        if r["target_entity_id"] == result.event_entity["entity_id"]
    ]
    
    assert len(event_relationships) == 2
    
    # person -> participated_in -> event
    person_rel = next(
        (r for r in event_relationships if r["relationship_type"] == "participated_in"),
        None
    )
    assert person_rel is not None
    
    # organization -> mentioned_in -> event
    org_rel = next(
        (r for r in event_relationships if r["relationship_type"] == "mentioned_in"),
        None
    )
    assert org_rel is not None
    
    # Cleanup
    for rel in result.created_relationships:
        await crm_container.relationship_service.delete_relationship(rel["relationship_id"])
    for entity in result.created_entities:
        await crm_container.entity_service.delete_entity(entity["entity_id"])


@pytest.mark.asyncio
async def test_confirm_entities_links_to_note(
    note_service,
    note_repo,
    crm_container,
    meeting_note,
    test_context,
):
    """Тест: созданные сущности линкуются к заметке"""
    request = ConfirmEntitiesRequest(
        entities=[
            EntityConfirmItem(
                type="person",
                name="John Smith",
                attributes={},
            ),
        ],
        relationships=[],
        create_event=True,
        link_author=False,
    )
    
    result = await note_service.confirm_entities(
        meeting_note.note_id,
        request,
        company_id=test_context.active_company.company_id,
    )
    
    # Проверяем что linked_entity_ids обновлены
    updated_note = await note_repo.get(meeting_note.note_id)
    
    assert len(updated_note.linked_entity_ids) > 0
    assert len(result.linked_entity_ids) > 0
    
    # Все созданные сущности должны быть в linked_entity_ids
    for entity_id in result.linked_entity_ids:
        assert entity_id in updated_note.linked_entity_ids
    
    # Cleanup
    for rel in result.created_relationships:
        await crm_container.relationship_service.delete_relationship(rel["relationship_id"])
    for entity in result.created_entities:
        await crm_container.entity_service.delete_entity(entity["entity_id"])


@pytest.mark.asyncio
async def test_confirm_entities_source_note_id_in_attributes(
    note_service,
    crm_container,
    meeting_note,
    test_context,
):
    """Тест: source_note_id сохраняется в атрибутах сущностей и связей"""
    request = ConfirmEntitiesRequest(
        entities=[
            EntityConfirmItem(
                type="person",
                name="John Smith",
                attributes={},
            ),
            EntityConfirmItem(
                type="person",
                name="Jane Doe",
                attributes={},
            ),
        ],
        relationships=[
            RelationshipConfirmItem(
                source_index=0,
                target_index=1,
                relationship_type="knows",
                weight=0.8,
                attributes={},
            ),
        ],
        create_event=False,
        link_author=False,
    )
    
    result = await note_service.confirm_entities(
        meeting_note.note_id,
        request,
        company_id=test_context.active_company.company_id,
    )
    
    # Проверяем source_note_id в сущностях
    for entity in result.created_entities:
        assert entity.get("source_note_id") == meeting_note.note_id
    
    # Проверяем source_note_id в атрибутах связей
    for rel in result.created_relationships:
        assert rel["attributes"].get("source_note_id") == meeting_note.note_id
    
    # Cleanup
    for rel in result.created_relationships:
        await crm_container.relationship_service.delete_relationship(rel["relationship_id"])
    for entity in result.created_entities:
        await crm_container.entity_service.delete_entity(entity["entity_id"])


@pytest.mark.asyncio
async def test_confirm_entities_empty_request(
    note_service,
    meeting_note,
    test_context,
):
    """Тест: пустой запрос не создает ничего"""
    request = ConfirmEntitiesRequest(
        entities=[],
        relationships=[],
        create_event=False,
        link_author=False,
    )
    
    result = await note_service.confirm_entities(
        meeting_note.note_id,
        request,
        company_id=test_context.active_company.company_id,
    )
    
    assert len(result.created_entities) == 0
    assert len(result.created_relationships) == 0
    assert result.event_entity is None


@pytest.mark.asyncio
async def test_confirm_entities_nonexistent_note(
    note_service,
    test_context,
):
    """Тест: ошибка для несуществующей заметки"""
    request = ConfirmEntitiesRequest(
        entities=[],
        relationships=[],
        create_event=False,
        link_author=False,
    )
    
    with pytest.raises(ValueError, match="не найдена"):
        await note_service.confirm_entities(
            "nonexistent_note_id",
            request,
            company_id=test_context.active_company.company_id,
        )


@pytest.mark.asyncio
async def test_confirm_entities_multiple_relationships(
    note_service,
    crm_container,
    meeting_note,
    test_context,
):
    """Тест: создание нескольких связей между несколькими сущностями"""
    request = ConfirmEntitiesRequest(
        entities=[
            EntityConfirmItem(type="person", name="Person A", attributes={}),
            EntityConfirmItem(type="person", name="Person B", attributes={}),
            EntityConfirmItem(type="organization", name="Org X", attributes={}),
        ],
        relationships=[
            RelationshipConfirmItem(
                source_index=0, target_index=2,
                relationship_type="works_for", weight=1.0, attributes={},
            ),
            RelationshipConfirmItem(
                source_index=1, target_index=2,
                relationship_type="works_for", weight=1.0, attributes={},
            ),
            RelationshipConfirmItem(
                source_index=0, target_index=1,
                relationship_type="knows", weight=0.5, attributes={},
            ),
        ],
        create_event=False,
        link_author=False,
    )
    
    result = await note_service.confirm_entities(
        meeting_note.note_id,
        request,
        company_id=test_context.active_company.company_id,
    )
    
    assert len(result.created_entities) == 3
    assert len(result.created_relationships) == 3
    
    rel_types = [r["relationship_type"] for r in result.created_relationships]
    assert rel_types.count("works_for") == 2
    assert rel_types.count("knows") == 1
    
    # Cleanup
    for rel in result.created_relationships:
        await crm_container.relationship_service.delete_relationship(rel["relationship_id"])
    for entity in result.created_entities:
        await crm_container.entity_service.delete_entity(entity["entity_id"])

