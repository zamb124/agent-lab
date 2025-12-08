"""
Тесты для event типов сущностей (meeting, call, email).

Проверяем:
- Системные типы событий создаются при инициализации
- Поле is_event корректно установлено для event типов
- Кастомные event типы можно создавать
"""

import pytest

from apps.crm.models.entity_type_models import EntityTypeCreate, EntityTypeUpdate


@pytest.mark.asyncio
async def test_system_event_types_created(entity_type_service, test_context):
    """Тест: системные event типы создаются при инициализации"""
    await entity_type_service.init_system_types()
    
    all_types = await entity_type_service.get_all_types(
        company_id=test_context.active_company.company_id
    )
    
    type_ids = [t.type_id for t in all_types]
    
    # Проверяем что event типы созданы
    assert "meeting" in type_ids
    assert "call" in type_ids
    assert "email" in type_ids


@pytest.mark.asyncio
async def test_event_types_have_is_event_true(entity_type_service, test_context):
    """Тест: event типы имеют is_event=True"""
    await entity_type_service.init_system_types()
    
    meeting = await entity_type_service.get_type(
        "meeting",
        company_id=test_context.active_company.company_id
    )
    call = await entity_type_service.get_type(
        "call",
        company_id=test_context.active_company.company_id
    )
    email = await entity_type_service.get_type(
        "email",
        company_id=test_context.active_company.company_id
    )
    
    assert meeting.is_event is True
    assert call.is_event is True
    assert email.is_event is True


@pytest.mark.asyncio
async def test_regular_types_have_is_event_false(entity_type_service, test_context):
    """Тест: обычные типы имеют is_event=False"""
    await entity_type_service.init_system_types()
    
    person = await entity_type_service.get_type(
        "person",
        company_id=test_context.active_company.company_id
    )
    organization = await entity_type_service.get_type(
        "organization",
        company_id=test_context.active_company.company_id
    )
    project = await entity_type_service.get_type(
        "project",
        company_id=test_context.active_company.company_id
    )
    task = await entity_type_service.get_type(
        "task",
        company_id=test_context.active_company.company_id
    )
    
    assert person.is_event is False
    assert organization.is_event is False
    assert project.is_event is False
    assert task.is_event is False


@pytest.mark.asyncio
async def test_event_types_is_system(entity_type_service, test_context):
    """Тест: event типы являются системными"""
    await entity_type_service.init_system_types()
    
    meeting = await entity_type_service.get_type(
        "meeting",
        company_id=test_context.active_company.company_id
    )
    call = await entity_type_service.get_type(
        "call",
        company_id=test_context.active_company.company_id
    )
    email = await entity_type_service.get_type(
        "email",
        company_id=test_context.active_company.company_id
    )
    
    assert meeting.is_system is True
    assert call.is_system is True
    assert email.is_system is True


@pytest.mark.asyncio
async def test_event_types_is_filtered(entity_type_service, test_context):
    """Тест: event типы имеют is_filtered=True (второстепенные)"""
    await entity_type_service.init_system_types()
    
    meeting = await entity_type_service.get_type(
        "meeting",
        company_id=test_context.active_company.company_id
    )
    call = await entity_type_service.get_type(
        "call",
        company_id=test_context.active_company.company_id
    )
    email = await entity_type_service.get_type(
        "email",
        company_id=test_context.active_company.company_id
    )
    
    assert meeting.is_filtered is True
    assert call.is_filtered is True
    assert email.is_filtered is True


@pytest.mark.asyncio
async def test_meeting_type_has_correct_fields(entity_type_service, test_context):
    """Тест: тип meeting имеет правильные поля"""
    await entity_type_service.init_system_types()
    
    meeting = await entity_type_service.get_type(
        "meeting",
        company_id=test_context.active_company.company_id
    )
    
    # Проверяем required_fields
    assert "name" in meeting.required_fields
    
    # Проверяем optional_fields
    assert "date" in meeting.optional_fields
    assert "location" in meeting.optional_fields
    assert "duration" in meeting.optional_fields
    assert "summary" in meeting.optional_fields


@pytest.mark.asyncio
async def test_call_type_has_correct_fields(entity_type_service, test_context):
    """Тест: тип call имеет правильные поля"""
    await entity_type_service.init_system_types()
    
    call = await entity_type_service.get_type(
        "call",
        company_id=test_context.active_company.company_id
    )
    
    assert "name" in call.required_fields
    assert "date" in call.optional_fields
    assert "duration" in call.optional_fields
    assert "summary" in call.optional_fields


@pytest.mark.asyncio
async def test_email_type_has_correct_fields(entity_type_service, test_context):
    """Тест: тип email имеет правильные поля"""
    await entity_type_service.init_system_types()
    
    email = await entity_type_service.get_type(
        "email",
        company_id=test_context.active_company.company_id
    )
    
    assert "name" in email.required_fields
    assert "date" in email.optional_fields
    assert "summary" in email.optional_fields


@pytest.mark.asyncio
async def test_create_custom_event_type(entity_type_service, test_context, unique_id):
    """Тест: можно создать кастомный event тип"""
    type_id = unique_id("event")
    
    data = EntityTypeCreate(
        type_id=type_id,
        name="Custom Event",
        description="Custom event type for testing",
        prompt="Extract custom events",
        icon="ti-calendar-event",
        color="#9C27B0",
        is_event=True,
        check_duplicates=False,
        is_filtered=True,
    )
    
    created = await entity_type_service.create_type(
        data=data,
        company_id=test_context.active_company.company_id
    )
    
    assert created.type_id == type_id
    assert created.is_event is True
    assert created.is_system is False
    
    await entity_type_service.delete_type(
        type_id,
        company_id=test_context.active_company.company_id
    )


@pytest.mark.asyncio
async def test_update_is_event_field(entity_type_service, test_context, unique_id):
    """Тест: можно обновить поле is_event"""
    type_id = unique_id("type")
    
    data = EntityTypeCreate(
        type_id=type_id,
        name="Test Type",
        prompt="Test",
        is_event=False,
    )
    
    await entity_type_service.create_type(
        data=data,
        company_id=test_context.active_company.company_id
    )
    
    # Обновляем is_event
    update_data = EntityTypeUpdate(is_event=True)
    updated = await entity_type_service.update_type(
        type_id,
        update_data,
        company_id=test_context.active_company.company_id
    )
    
    assert updated.is_event is True
    
    await entity_type_service.delete_type(
        type_id,
        company_id=test_context.active_company.company_id
    )


@pytest.mark.asyncio
async def test_event_types_have_unique_colors(entity_type_service, test_context):
    """Тест: event типы имеют уникальные цвета"""
    await entity_type_service.init_system_types()
    
    meeting = await entity_type_service.get_type(
        "meeting",
        company_id=test_context.active_company.company_id
    )
    call = await entity_type_service.get_type(
        "call",
        company_id=test_context.active_company.company_id
    )
    email = await entity_type_service.get_type(
        "email",
        company_id=test_context.active_company.company_id
    )
    
    colors = [meeting.color, call.color, email.color]
    
    # Все цвета должны быть разными
    assert len(colors) == len(set(colors))
    
    # Все цвета должны быть HEX формата
    for color in colors:
        assert color.startswith("#")
        assert len(color) == 7


@pytest.mark.asyncio
async def test_event_types_have_unique_icons(entity_type_service, test_context):
    """Тест: event типы имеют уникальные иконки"""
    await entity_type_service.init_system_types()
    
    meeting = await entity_type_service.get_type(
        "meeting",
        company_id=test_context.active_company.company_id
    )
    call = await entity_type_service.get_type(
        "call",
        company_id=test_context.active_company.company_id
    )
    email = await entity_type_service.get_type(
        "email",
        company_id=test_context.active_company.company_id
    )
    
    icons = [meeting.icon, call.icon, email.icon]
    
    # Все иконки должны быть разными
    assert len(icons) == len(set(icons))
    
    # Все иконки должны начинаться с ti-
    for icon in icons:
        assert icon.startswith("ti-")

