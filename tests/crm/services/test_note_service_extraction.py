"""
Тесты для методов извлечения сущностей в NoteService.

Проверяем:
- _get_entity_types_for_extraction - получение типов для AI
- _get_author_info - получение информации об авторе
"""

import pytest
import pytest_asyncio
from datetime import date, datetime, timezone

from apps.crm.db.models import Note
from apps.crm.models.entity_models import EntityCreate


@pytest_asyncio.fixture
async def test_note(test_context, note_repo, unique_crm_id) -> Note:
    """Создает тестовую заметку"""
    note_id = unique_crm_id("note")
    note = Note(
        note_id=note_id,
        company_id=test_context.active_company.company_id,
        user_id=test_context.user.user_id,
        title="Test Note",
        content="Test content",
        note_type="meeting_minutes",
        note_date=date.today(),
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
async def user_person_entity(test_context, crm_container, unique_crm_id):
    """Создает person сущность связанную с user"""
    entity_service = crm_container.entity_service
    
    data = EntityCreate(
        type="person",
        name="Test User Person",
        description="Person entity for test user",
        attributes={
            "user_id": test_context.user.user_id,
            "email": "test@example.com",
        },
    )
    
    entity = await entity_service.create_entity(data)
    yield entity
    
    try:
        await entity_service.delete_entity(entity.entity_id)
    except Exception:
        pass


class TestGetEntityTypesForExtraction:
    """Тесты на _get_entity_types_for_extraction"""
    
    @pytest.mark.asyncio
    async def test_returns_all_entity_types(
        self,
        note_service,
        entity_type_service,
        test_context,
    ):
        """Тест: возвращает все типы сущностей"""
        await entity_type_service.init_system_types()
        
        types = await note_service._get_entity_types_for_extraction(
            company_id=test_context.active_company.company_id,
            note_type="meeting_minutes",
        )
        
        type_ids = [t["type_id"] for t in types]
        
        # Должны быть базовые типы
        assert "person" in type_ids
        assert "organization" in type_ids
        assert "project" in type_ids
        assert "task" in type_ids
        
        # Должны быть event типы
        assert "meeting" in type_ids
        assert "call" in type_ids
        assert "email" in type_ids
    
    @pytest.mark.asyncio
    async def test_includes_is_event_field(
        self,
        note_service,
        entity_type_service,
        test_context,
    ):
        """Тест: включает поле is_event"""
        await entity_type_service.init_system_types()
        
        types = await note_service._get_entity_types_for_extraction(
            company_id=test_context.active_company.company_id,
            note_type="freeform",
        )
        
        # Проверяем что is_event есть
        meeting_type = next(t for t in types if t["type_id"] == "meeting")
        person_type = next(t for t in types if t["type_id"] == "person")
        
        assert meeting_type["is_event"] is True
        assert person_type["is_event"] is False
    
    @pytest.mark.asyncio
    async def test_includes_required_and_optional_fields(
        self,
        note_service,
        entity_type_service,
        test_context,
    ):
        """Тест: включает required_fields и optional_fields"""
        await entity_type_service.init_system_types()
        
        types = await note_service._get_entity_types_for_extraction(
            company_id=test_context.active_company.company_id,
            note_type="meeting_minutes",
        )
        
        person_type = next(t for t in types if t["type_id"] == "person")
        
        assert "required_fields" in person_type
        assert "optional_fields" in person_type
        assert "name" in person_type["required_fields"]
    
    @pytest.mark.asyncio
    async def test_includes_prompt_and_description(
        self,
        note_service,
        entity_type_service,
        test_context,
    ):
        """Тест: включает prompt и description"""
        await entity_type_service.init_system_types()
        
        types = await note_service._get_entity_types_for_extraction(
            company_id=test_context.active_company.company_id,
            note_type="freeform",
        )
        
        person_type = next(t for t in types if t["type_id"] == "person")
        
        assert "prompt" in person_type
        assert "description" in person_type
        # Prompt не должен быть пустым
        assert person_type["prompt"] or person_type["description"]


class TestGetAuthorInfo:
    """Тесты на _get_author_info"""
    
    @pytest.mark.asyncio
    async def test_returns_user_id(
        self,
        note_service,
        test_context,
    ):
        """Тест: возвращает user_id"""
        result = await note_service._get_author_info(
            user_id=test_context.user.user_id,
            company_id=test_context.active_company.company_id,
        )
        
        assert result["user_id"] == test_context.user.user_id
    
    @pytest.mark.asyncio
    async def test_returns_name(
        self,
        note_service,
        test_context,
    ):
        """Тест: возвращает имя"""
        result = await note_service._get_author_info(
            user_id=test_context.user.user_id,
            company_id=test_context.active_company.company_id,
        )
        
        assert "name" in result
        assert result["name"]  # Не пустое
    
    @pytest.mark.asyncio
    async def test_uses_person_entity_if_exists(
        self,
        note_service,
        test_context,
        user_person_entity,
    ):
        """Тест: использует person сущность если существует"""
        result = await note_service._get_author_info(
            user_id=test_context.user.user_id,
            company_id=test_context.active_company.company_id,
        )
        
        # Должно вернуть данные из person entity
        assert result["name"] == user_person_entity.name
        assert result.get("entity_id") == user_person_entity.entity_id
    
    @pytest.mark.asyncio
    async def test_includes_entity_id_when_person_exists(
        self,
        note_service,
        test_context,
        user_person_entity,
    ):
        """Тест: включает entity_id когда есть person"""
        result = await note_service._get_author_info(
            user_id=test_context.user.user_id,
            company_id=test_context.active_company.company_id,
        )
        
        assert "entity_id" in result
        assert result["entity_id"] == user_person_entity.entity_id
    
    @pytest.mark.asyncio
    async def test_includes_attributes_when_person_exists(
        self,
        note_service,
        test_context,
        user_person_entity,
    ):
        """Тест: включает attributes когда есть person"""
        result = await note_service._get_author_info(
            user_id=test_context.user.user_id,
            company_id=test_context.active_company.company_id,
        )
        
        assert "attributes" in result
        # Проверяем что атрибуты содержат данные
        assert result["attributes"] is not None
    
    @pytest.mark.asyncio
    async def test_fallback_to_context_user(
        self,
        note_service,
        test_context,
    ):
        """Тест: fallback на данные из context.user"""
        # Без person entity
        result = await note_service._get_author_info(
            user_id=test_context.user.user_id,
            company_id=test_context.active_company.company_id,
        )
        
        assert result["user_id"] == test_context.user.user_id
        # Имя должно быть из context.user или user_id
        assert result["name"]
    
    @pytest.mark.asyncio
    async def test_fallback_to_user_id_as_name(
        self,
        note_service,
        test_context,
    ):
        """Тест: fallback на user_id как имя для unknown user"""
        result = await note_service._get_author_info(
            user_id="unknown_user_xyz",
            company_id=test_context.active_company.company_id,
        )
        
        # Для неизвестного user возвращает user_id как имя
        assert result["name"] == "unknown_user_xyz"
        assert result["user_id"] == "unknown_user_xyz"

