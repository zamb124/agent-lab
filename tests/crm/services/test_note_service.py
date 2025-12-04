"""
Тесты для NoteService.
"""

import pytest
from datetime import date, timedelta

from apps.crm.models.note_models import NoteCreate, NoteUpdate, NoteType


@pytest.mark.asyncio
async def test_create_note(note_service, test_context, unique_crm_id):
    """Тест создания заметки через сервис"""
    data = NoteCreate(
        title="Service Test Note",
        content="Created via NoteService",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    
    result = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert result.title == "Service Test Note"
    assert result.note_type == "freeform"
    assert result.company_id == test_context.active_company.company_id
    
    await note_service.delete_note(result.note_id)


@pytest.mark.asyncio
async def test_get_note(note_service, test_context, unique_crm_id):
    """Тест получения заметки"""
    data = NoteCreate(
        title="Get Test Note",
        content="Content for get test",
        note_type=NoteType.MEETING_MINUTES,
        note_date=date.today(),
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    fetched = await note_service.get_note(created.note_id)
    
    assert fetched is not None
    assert fetched.note_id == created.note_id
    assert fetched.title == "Get Test Note"
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_update_note(note_service, test_context, unique_crm_id):
    """Тест обновления заметки"""
    data = NoteCreate(
        title="Update Test Note",
        content="Original content",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    update_data = NoteUpdate(
        title="Updated Title",
        content="Updated content",
    )
    
    updated = await note_service.update_note(created.note_id, update_data)
    
    assert updated.title == "Updated Title"
    assert updated.content == "Updated content"
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_delete_note(note_service, test_context, unique_crm_id):
    """Тест удаления заметки"""
    data = NoteCreate(
        title="Delete Test Note",
        content="Will be deleted",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    success = await note_service.delete_note(created.note_id)
    assert success is True
    
    fetched = await note_service.get_note(created.note_id)
    assert fetched is None


@pytest.mark.asyncio
async def test_get_daily_notes(note_service, test_context, unique_crm_id):
    """Тест получения заметок за день"""
    today = date.today()
    created_ids = []
    
    for i in range(3):
        data = NoteCreate(
            title=f"Daily Note {i}",
            content=f"Content {i}",
            note_type=NoteType.FREEFORM,
            note_date=today,
        )
        result = await note_service.create_note(
            data,
            company_id=test_context.active_company.company_id,
            user_id=test_context.user.user_id
        )
        created_ids.append(result.note_id)
    
    daily_notes = await note_service.get_daily_notes(
        today,
        company_id=test_context.active_company.company_id
    )
    
    assert len(daily_notes) >= 3
    
    for note_id in created_ids:
        await note_service.delete_note(note_id)


@pytest.mark.asyncio
async def test_get_notes_in_range(note_service, test_context, unique_crm_id):
    """Тест получения заметок за диапазон дат"""
    today = date.today()
    created_ids = []
    
    data = NoteCreate(
        title="Range Test Note",
        content="Content",
        note_type=NoteType.FREEFORM,
        note_date=today,
    )
    result = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    created_ids.append(result.note_id)
    
    start = today - timedelta(days=1)
    end = today + timedelta(days=1)
    
    notes = await note_service.get_notes_in_range(
        start,
        end,
        company_id=test_context.active_company.company_id
    )
    
    note_ids = [n.note_id for n in notes]
    assert result.note_id in note_ids
    
    for note_id in created_ids:
        await note_service.delete_note(note_id)


@pytest.mark.asyncio
async def test_list_notes(note_service, test_context, unique_crm_id):
    """Тест получения списка заметок"""
    created_ids = []
    
    for i in range(5):
        data = NoteCreate(
            title=f"List Note {i}",
            content=f"Content {i}",
            note_type=NoteType.FREEFORM,
            note_date=date.today(),
        )
        result = await note_service.create_note(
            data,
            company_id=test_context.active_company.company_id,
            user_id=test_context.user.user_id
        )
        created_ids.append(result.note_id)
    
    notes = await note_service.list_notes(
        limit=10,
        company_id=test_context.active_company.company_id
    )
    
    assert len(notes) >= 5
    
    for note_id in created_ids:
        await note_service.delete_note(note_id)


@pytest.mark.asyncio
async def test_list_notes_by_type(note_service, test_context, unique_crm_id):
    """Тест фильтрации заметок по типу"""
    data = NoteCreate(
        title="Call Log Note",
        content="Called client",
        note_type=NoteType.CALL_LOG,
        note_date=date.today(),
    )
    
    result = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    notes = await note_service.list_notes(
        note_type="call_log",
        company_id=test_context.active_company.company_id
    )
    
    note_ids = [n.note_id for n in notes]
    assert result.note_id in note_ids
    
    await note_service.delete_note(result.note_id)


@pytest.mark.asyncio
async def test_search_notes(note_service, test_context, unique_crm_id):
    """Тест поиска заметок"""
    unique_text = f"unique_search_{unique_crm_id('text')}"
    
    data = NoteCreate(
        title="Search Test",
        content=f"This contains {unique_text} for testing",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    
    result = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    found = await note_service.search_notes(
        unique_text,
        company_id=test_context.active_company.company_id
    )
    
    note_ids = [n.note_id for n in found]
    assert result.note_id in note_ids
    
    await note_service.delete_note(result.note_id)


@pytest.mark.asyncio
async def test_link_entity_to_note(note_service, test_context, unique_crm_id):
    """Тест связывания сущности с заметкой"""
    data = NoteCreate(
        title="Link Test Note",
        content="Will link entity",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    
    note = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    entity_id = unique_crm_id("entity")
    
    updated = await note_service.link_entity_to_note(note.note_id, entity_id)
    
    assert entity_id in updated.linked_entity_ids
    
    await note_service.delete_note(note.note_id)


@pytest.mark.asyncio
async def test_unlink_entity_from_note(note_service, test_context, unique_crm_id):
    """Тест удаления связи сущности с заметкой"""
    entity_id = unique_crm_id("entity")
    
    data = NoteCreate(
        title="Unlink Test Note",
        content="Will unlink entity",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
        linked_entity_ids=[entity_id],
    )
    
    note = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    updated = await note_service.unlink_entity_from_note(note.note_id, entity_id)
    
    assert entity_id not in updated.linked_entity_ids
    
    await note_service.delete_note(note.note_id)


@pytest.mark.asyncio
async def test_get_notes_by_entity(note_service, test_context, unique_crm_id):
    """Тест получения заметок по связанной сущности"""
    entity_id = unique_crm_id("entity")
    
    data = NoteCreate(
        title="Entity Note",
        content="Linked to entity",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
        linked_entity_ids=[entity_id],
    )
    
    result = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    notes = await note_service.get_notes_by_entity(
        entity_id,
        company_id=test_context.active_company.company_id
    )
    
    note_ids = [n.note_id for n in notes]
    assert result.note_id in note_ids
    
    await note_service.delete_note(result.note_id)

