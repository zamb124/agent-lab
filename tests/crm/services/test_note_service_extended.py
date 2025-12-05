"""
Тесты для расширенного функционала NoteService.
Тестируем: filter_notes, templates, visibility, attachments.
"""

import pytest
from datetime import date, timedelta

from apps.crm.models.note_models import (
    NoteCreate, NoteUpdate, NoteType, NoteStatus, NoteVisibility
)


@pytest.mark.asyncio
async def test_filter_notes_by_date_range(note_service, test_context, unique_crm_id):
    """Тест фильтрации заметок по диапазону дат"""
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    data = NoteCreate(
        title="Date Filter Note",
        content="Content for filter",
        note_type=NoteType.FREEFORM,
        note_date=today,
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    notes = await note_service.filter_notes(
        start_date=yesterday,
        end_date=today,
        company_id=test_context.active_company.company_id
    )
    
    note_ids = [n.note_id for n in notes]
    assert created.note_id in note_ids
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_filter_notes_by_user(note_service, test_context, unique_crm_id):
    """Тест фильтрации заметок по пользователю"""
    user_id = test_context.user.user_id
    
    data = NoteCreate(
        title="User Filter Note",
        content="Content",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=user_id
    )
    
    notes = await note_service.filter_notes(
        user_id=user_id,
        company_id=test_context.active_company.company_id
    )
    
    note_ids = [n.note_id for n in notes]
    assert created.note_id in note_ids
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_filter_notes_combined(note_service, test_context, unique_crm_id):
    """Тест комбинированной фильтрации"""
    today = date.today()
    unique_text = unique_crm_id("search_text")
    
    data = NoteCreate(
        title="Combined Filter",
        content=f"Contains {unique_text}",
        note_type=NoteType.MEETING_MINUTES,
        note_date=today,
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    notes = await note_service.filter_notes(
        note_type="meeting_minutes",
        start_date=today,
        search_text=unique_text,
        company_id=test_context.active_company.company_id
    )
    
    note_ids = [n.note_id for n in notes]
    assert created.note_id in note_ids
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_create_template(note_service, test_context, unique_crm_id):
    """Тест создания шаблона заметки"""
    data = NoteCreate(
        title="Meeting Template",
        content="## Agenda\n\n## Participants\n\n## Actions",
        note_type=NoteType.MEETING_MINUTES,
        note_date=date.today(),
        is_template=True,
    )
    
    template = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert template.is_template is True
    assert template.title == "Meeting Template"
    
    await note_service.delete_note(template.note_id)


@pytest.mark.asyncio
async def test_get_templates(note_service, test_context, unique_crm_id):
    """Тест получения списка шаблонов"""
    created_ids = []
    
    for i in range(2):
        data = NoteCreate(
            title=f"Template {i}",
            content=f"Template content {i}",
            note_type=NoteType.FREEFORM,
            note_date=date.today(),
            is_template=True,
        )
        result = await note_service.create_note(
            data,
            company_id=test_context.active_company.company_id,
            user_id=test_context.user.user_id
        )
        created_ids.append(result.note_id)
    
    templates = await note_service.get_templates(
        company_id=test_context.active_company.company_id
    )
    
    assert len(templates) >= 2
    for t in templates:
        assert t.is_template is True
    
    for note_id in created_ids:
        await note_service.delete_note(note_id)


@pytest.mark.asyncio
async def test_get_templates_by_type(note_service, test_context, unique_crm_id):
    """Тест получения шаблонов по типу"""
    data = NoteCreate(
        title="Call Template",
        content="## Call Summary\n\n## Follow-up",
        note_type=NoteType.CALL_LOG,
        note_date=date.today(),
        is_template=True,
    )
    
    template = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    templates = await note_service.get_templates(
        note_type="call_log",
        company_id=test_context.active_company.company_id
    )
    
    template_ids = [t.note_id for t in templates]
    assert template.note_id in template_ids
    
    await note_service.delete_note(template.note_id)


@pytest.mark.asyncio
async def test_create_from_template(note_service, test_context, unique_crm_id):
    """Тест создания заметки из шаблона"""
    # Создаем шаблон
    template_data = NoteCreate(
        title="Daily Standup Template",
        content="## What I did\n\n## What I will do\n\n## Blockers",
        note_type=NoteType.MEETING_MINUTES,
        note_date=date.today(),
        is_template=True,
    )
    
    template = await note_service.create_note(
        template_data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    # Создаем заметку из шаблона
    note = await note_service.create_from_template(
        template_id=template.note_id,
        note_date=date.today(),
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert note.title == template.title
    assert note.content == template.content
    assert note.note_type == template.note_type
    assert note.is_template is False
    assert note.status == "draft"
    
    await note_service.delete_note(note.note_id)
    await note_service.delete_note(template.note_id)


@pytest.mark.asyncio
async def test_create_note_with_draft_status(note_service, test_context, unique_crm_id):
    """Тест создания заметки со статусом draft"""
    data = NoteCreate(
        title="Draft Note",
        content="Work in progress",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
        status=NoteStatus.DRAFT,
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert created.status == "draft"
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_update_note_status(note_service, test_context, unique_crm_id):
    """Тест обновления статуса заметки"""
    data = NoteCreate(
        title="Status Test",
        content="Will update status",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
        status=NoteStatus.DRAFT,
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    update_data = NoteUpdate(status=NoteStatus.PUBLISHED)
    updated = await note_service.update_note(created.note_id, update_data)
    
    assert updated.status == "published"
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_create_note_with_visibility(note_service, test_context, unique_crm_id):
    """Тест создания заметки с visibility"""
    shared_user = unique_crm_id("user")
    
    data = NoteCreate(
        title="Private Note",
        content="Sensitive information",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
        visibility=NoteVisibility.SHARED,
        shared_with=[shared_user],
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert created.visibility == "shared"
    assert shared_user in created.shared_with
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_update_visibility(note_service, test_context, unique_crm_id):
    """Тест обновления visibility заметки"""
    data = NoteCreate(
        title="Public Note",
        content="Will become private",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
        visibility=NoteVisibility.PUBLIC,
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    update_data = NoteUpdate(visibility=NoteVisibility.PRIVATE)
    updated = await note_service.update_note(created.note_id, update_data)
    
    assert updated.visibility == "private"
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_create_note_with_attachments(note_service, test_context, unique_crm_id):
    """Тест создания заметки с прикрепленными файлами"""
    file_id_1 = unique_crm_id("file1")
    file_id_2 = unique_crm_id("file2")
    
    data = NoteCreate(
        title="Note with Attachments",
        content="Has files",
        note_type=NoteType.MEETING_MINUTES,
        note_date=date.today(),
        attachment_ids=[file_id_1, file_id_2],
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    assert file_id_1 in created.attachment_ids
    assert file_id_2 in created.attachment_ids
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_update_attachments(note_service, test_context, unique_crm_id):
    """Тест обновления прикрепленных файлов"""
    old_file = unique_crm_id("old_file")
    new_file = unique_crm_id("new_file")
    
    data = NoteCreate(
        title="Attachment Update",
        content="Will update files",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
        attachment_ids=[old_file],
    )
    
    created = await note_service.create_note(
        data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    update_data = NoteUpdate(attachment_ids=[new_file])
    updated = await note_service.update_note(created.note_id, update_data)
    
    assert new_file in updated.attachment_ids
    assert old_file not in updated.attachment_ids
    
    await note_service.delete_note(created.note_id)


@pytest.mark.asyncio
async def test_filter_templates_only(note_service, test_context, unique_crm_id):
    """Тест фильтрации только шаблонов через filter_notes"""
    created_ids = []
    
    # Создаем шаблон
    template_data = NoteCreate(
        title="Filter Template",
        content="Template content",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
        is_template=True,
    )
    template = await note_service.create_note(
        template_data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    created_ids.append(template.note_id)
    
    # Создаем обычную заметку
    note_data = NoteCreate(
        title="Regular Note",
        content="Not a template",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
        is_template=False,
    )
    regular = await note_service.create_note(
        note_data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    created_ids.append(regular.note_id)
    
    templates = await note_service.filter_notes(
        is_template=True,
        company_id=test_context.active_company.company_id
    )
    
    template_ids = [t.note_id for t in templates]
    assert template.note_id in template_ids
    assert regular.note_id not in template_ids
    
    for note_id in created_ids:
        await note_service.delete_note(note_id)


@pytest.mark.asyncio
async def test_filter_by_status(note_service, test_context, unique_crm_id):
    """Тест фильтрации по статусу через filter_notes"""
    # Создаем draft
    draft_data = NoteCreate(
        title="Draft for Filter",
        content="Draft content",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
        status=NoteStatus.DRAFT,
    )
    draft = await note_service.create_note(
        draft_data,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id
    )
    
    # Фильтруем по статусу draft
    drafts = await note_service.filter_notes(
        status="draft",
        company_id=test_context.active_company.company_id
    )
    
    draft_ids = [n.note_id for n in drafts]
    assert draft.note_id in draft_ids
    
    await note_service.delete_note(draft.note_id)

