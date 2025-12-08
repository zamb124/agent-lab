"""
Тесты для расширенного функционала NoteRepository.
Тестируем: filter_notes, get_templates, visibility, attachments.
"""

import pytest
from datetime import date, datetime, timezone, timedelta

from apps.crm.db.models import Note


@pytest.mark.asyncio
async def test_filter_notes_by_user(note_repo, test_context, unique_id):
    """Тест фильтрации заметок по пользователю"""
    user_id = test_context.user.user_id
    company_id = test_context.active_company.company_id
    created_ids = []
    
    for i in range(3):
        note_id = unique_id(f"note_{i}")
        note = Note(
            note_id=note_id,
            company_id=company_id,
            user_id=user_id,
            title=f"Filter User Note {i}",
            content="Content",
            note_type="freeform",
            note_date=date.today(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await note_repo.create(note)
        created_ids.append(note_id)
    
    notes = await note_repo.filter_notes(
        company_id=company_id,
        user_id=user_id
    )
    
    assert len(notes) >= 3
    for note in notes:
        assert note.user_id == user_id
    
    for note_id in created_ids:
        await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_filter_notes_by_date_range(note_repo, test_context, unique_id):
    """Тест фильтрации заметок по диапазону дат"""
    company_id = test_context.active_company.company_id
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    note_id = unique_id("note")
    note = Note(
        note_id=note_id,
        company_id=company_id,
        user_id=test_context.user.user_id,
        title="Date Range Note",
        content="Content",
        note_type="freeform",
        note_date=today,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(note)
    
    notes = await note_repo.filter_notes(
        company_id=company_id,
        start_date=yesterday,
        end_date=today
    )
    
    note_ids = [n.note_id for n in notes]
    assert note_id in note_ids
    
    await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_filter_notes_by_entity(note_repo, test_context, unique_id):
    """Тест фильтрации заметок по связанной сущности"""
    company_id = test_context.active_company.company_id
    entity_id = unique_id("entity")
    
    note_id = unique_id("note")
    note = Note(
        note_id=note_id,
        company_id=company_id,
        user_id=test_context.user.user_id,
        title="Entity Filter Note",
        content="Content",
        note_type="freeform",
        note_date=date.today(),
        linked_entity_ids=[entity_id],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(note)
    
    notes = await note_repo.filter_notes(
        company_id=company_id,
        entity_id=entity_id
    )
    
    note_ids = [n.note_id for n in notes]
    assert note_id in note_ids
    
    await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_filter_notes_combined(note_repo, test_context, unique_id):
    """Тест комбинированной фильтрации заметок"""
    company_id = test_context.active_company.company_id
    user_id = test_context.user.user_id
    today = date.today()
    unique_text = unique_id("unique_text")
    
    note_id = unique_id("note")
    note = Note(
        note_id=note_id,
        company_id=company_id,
        user_id=user_id,
        title="Combined Filter Note",
        content=f"Contains {unique_text}",
        note_type="meeting_minutes",
        note_date=today,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(note)
    
    notes = await note_repo.filter_notes(
        company_id=company_id,
        user_id=user_id,
        note_type="meeting_minutes",
        start_date=today,
        end_date=today,
        search_text=unique_text
    )
    
    note_ids = [n.note_id for n in notes]
    assert note_id in note_ids
    
    await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_filter_notes_by_template(note_repo, test_context, unique_id):
    """Тест фильтрации шаблонов заметок"""
    company_id = test_context.active_company.company_id
    
    template_id = unique_id("template")
    template = Note(
        note_id=template_id,
        company_id=company_id,
        user_id=test_context.user.user_id,
        title="Meeting Template",
        content="## Agenda\n\n## Decisions\n\n## Actions",
        note_type="meeting_minutes",
        note_date=date.today(),
        is_template=True,
        status="published",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(template)
    
    notes = await note_repo.filter_notes(
        company_id=company_id,
        is_template=True
    )
    
    note_ids = [n.note_id for n in notes]
    assert template_id in note_ids
    
    await note_repo.delete(template_id)


@pytest.mark.asyncio
async def test_get_templates(note_repo, test_context, unique_id):
    """Тест получения шаблонов заметок"""
    company_id = test_context.active_company.company_id
    created_ids = []
    
    for i in range(2):
        template_id = unique_id(f"template_{i}")
        template = Note(
            note_id=template_id,
            company_id=company_id,
            user_id=test_context.user.user_id,
            title=f"Template {i}",
            content=f"Template content {i}",
            note_type="freeform",
            note_date=date.today(),
            is_template=True,
            status="published",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await note_repo.create(template)
        created_ids.append(template_id)
    
    # Создаем обычную заметку
    note_id = unique_id("note")
    note = Note(
        note_id=note_id,
        company_id=company_id,
        user_id=test_context.user.user_id,
        title="Not a Template",
        content="Regular content",
        note_type="freeform",
        note_date=date.today(),
        is_template=False,
        status="published",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(note)
    created_ids.append(note_id)
    
    templates = await note_repo.get_templates(company_id)
    
    assert len(templates) >= 2
    for t in templates:
        assert t.is_template is True
    
    for nid in created_ids:
        await note_repo.delete(nid)


@pytest.mark.asyncio
async def test_filter_notes_by_status(note_repo, test_context, unique_id):
    """Тест фильтрации заметок по статусу (draft/published)"""
    company_id = test_context.active_company.company_id
    
    draft_id = unique_id("draft")
    draft = Note(
        note_id=draft_id,
        company_id=company_id,
        user_id=test_context.user.user_id,
        title="Draft Note",
        content="Work in progress",
        note_type="freeform",
        note_date=date.today(),
        status="draft",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(draft)
    
    published_id = unique_id("published")
    published = Note(
        note_id=published_id,
        company_id=company_id,
        user_id=test_context.user.user_id,
        title="Published Note",
        content="Final content",
        note_type="freeform",
        note_date=date.today(),
        status="published",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_repo.create(published)
    
    drafts = await note_repo.filter_notes(
        company_id=company_id,
        status="draft"
    )
    draft_ids = [n.note_id for n in drafts]
    assert draft_id in draft_ids
    assert published_id not in draft_ids
    
    await note_repo.delete(draft_id)
    await note_repo.delete(published_id)


@pytest.mark.asyncio
async def test_note_with_visibility(note_repo, test_context, unique_id):
    """Тест создания заметки с visibility"""
    note_id = unique_id("note")
    shared_with_user = unique_id("user")
    
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Private Note",
        content="Sensitive content",
        note_type="freeform",
        note_date=date.today(),
        visibility="shared",
        shared_with=[shared_with_user],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    created = await note_repo.create(note)
    
    assert created.visibility == "shared"
    assert shared_with_user in created.shared_with
    
    await note_repo.delete(note_id)


@pytest.mark.asyncio
async def test_note_with_attachments(note_repo, test_context, unique_id):
    """Тест создания заметки с прикрепленными файлами"""
    note_id = unique_id("note")
    file_id_1 = unique_id("file1")
    file_id_2 = unique_id("file2")
    
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Note with Files",
        content="Has attachments",
        note_type="meeting_minutes",
        note_date=date.today(),
        attachment_ids=[file_id_1, file_id_2],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    
    created = await note_repo.create(note)
    
    assert file_id_1 in created.attachment_ids
    assert file_id_2 in created.attachment_ids
    assert len(created.attachment_ids) == 2
    
    await note_repo.delete(note_id)

