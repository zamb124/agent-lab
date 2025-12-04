"""
Тесты для NoteRepository.
"""

import pytest
from datetime import date, datetime, timezone, timedelta

from apps.crm.db.models import Note


@pytest.mark.asyncio
async def test_create_note(note_repo, test_context, unique_crm_id):
    """Тест создания заметки"""
    note_id = unique_crm_id("note")
    
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Meeting Notes",
        content="Discussed project roadmap",
        note_type="meeting_minutes",
        note_date=date.today(),
        ai_summary=None,
        linked_entity_ids=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    created = await note_repo.create(note)
    
    assert created.note_id == note_id
    assert created.title == "Meeting Notes"
    assert created.note_type == "meeting_minutes"
    
    await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_get_note(note_repo, sample_note):
    """Тест получения заметки по ID"""
    fetched = await note_repo.get(sample_note.note_id)
    
    assert fetched is not None
    assert fetched.note_id == sample_note.note_id
    assert fetched.title == sample_note.title


@pytest.mark.asyncio
async def test_update_note(note_repo, sample_note):
    """Тест обновления заметки"""
    sample_note.title = "Updated Title"
    sample_note.content = "Updated content"
    sample_note.updated_at = datetime.now(timezone.utc)
    
    updated = await note_repo.update(sample_note)
    
    assert updated.title == "Updated Title"
    assert updated.content == "Updated content"


@pytest.mark.asyncio
async def test_delete_note(note_repo, test_context, unique_crm_id):
    """Тест удаления заметки"""
    note_id = unique_crm_id("note")
    
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="To Delete",
        content="Will be deleted",
        note_type="freeform",
        note_date=date.today(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(note)
    
    success = await note_repo.delete(note_id)
    assert success is True
    
    fetched = await note_repo.get(note_id)
    assert fetched is None


@pytest.mark.asyncio
async def test_get_by_date(note_repo, test_context, unique_crm_id):
    """Тест получения заметок по дате"""
    today = date.today()
    created_ids = []
    
    for i in range(3):
        note_id = unique_crm_id(f"note_{i}")
        note = Note(
            note_id=note_id,
            company_id=test_context.active_company.company_id,
            user_id=test_context.user.user_id,
            title=f"Today Note {i}",
            content="Content",
            note_type="freeform",
            note_date=today,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await note_repo.create(note)
        created_ids.append(note_id)
    
    notes = await note_repo.get_by_date(
        test_context.active_company.company_id,
        today
    )
    
    assert len(notes) >= 3
    
    for note_id in created_ids:
        await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_get_by_date_range(note_repo, test_context, unique_crm_id):
    """Тест получения заметок за диапазон дат"""
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    
    note_id = unique_crm_id("note")
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Range Test",
        content="Content",
        note_type="freeform",
        note_date=today,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(note)
    
    notes = await note_repo.get_by_date_range(
        test_context.active_company.company_id,
        yesterday,
        tomorrow
    )
    
    note_ids = [n.note_id for n in notes]
    assert note_id in note_ids
    
    await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_get_by_type(note_repo, test_context, unique_crm_id):
    """Тест получения заметок по типу"""
    note_id = unique_crm_id("note")
    
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Call Log",
        content="Called client",
        note_type="call_log",
        note_date=date.today(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(note)
    
    notes = await note_repo.get_by_type(
        test_context.active_company.company_id,
        "call_log"
    )
    
    note_ids = [n.note_id for n in notes]
    assert note_id in note_ids
    
    await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_search_by_content(note_repo, test_context, unique_crm_id):
    """Тест поиска по содержимому"""
    note_id = unique_crm_id("note")
    unique_text = f"unique_search_text_{unique_crm_id('text')}"
    
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Search Test",
        content=f"This note contains {unique_text} for testing",
        note_type="freeform",
        note_date=date.today(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(note)
    
    notes = await note_repo.search_by_content(
        test_context.active_company.company_id,
        unique_text
    )
    
    note_ids = [n.note_id for n in notes]
    assert note_id in note_ids
    
    await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_get_linked_to_entity(note_repo, test_context, unique_crm_id):
    """Тест получения заметок, связанных с сущностью"""
    note_id = unique_crm_id("note")
    entity_id = unique_crm_id("entity")
    
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Linked Note",
        content="Content",
        note_type="freeform",
        note_date=date.today(),
        linked_entity_ids=[entity_id],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(note)
    
    notes = await note_repo.get_linked_to_entity(
        test_context.active_company.company_id,
        entity_id
    )
    
    note_ids = [n.note_id for n in notes]
    assert note_id in note_ids
    
    await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_get_by_company(note_repo, test_context, unique_crm_id):
    """Тест получения заметок по компании"""
    created_ids = []
    
    for i in range(3):
        note_id = unique_crm_id(f"note_{i}")
        note = Note(
            note_id=note_id,
            company_id=test_context.active_company.company_id,
            user_id=test_context.user.user_id,
            title=f"Company Note {i}",
            content="Content",
            note_type="freeform",
            note_date=date.today(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await note_repo.create(note)
        created_ids.append(note_id)
    
    notes = await note_repo.get_by_company(
        test_context.active_company.company_id,
        limit=100
    )
    
    assert len(notes) >= 3
    
    for note_id in created_ids:
        await note_repo.delete(note_id)

