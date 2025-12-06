"""
Тесты на формирование промпта в AgentsClient.

Проверяем:
- Форматирование типов сущностей
- Разделение на обычные типы и event типы
- Инструкции по связям
- Контекст заметки с автором
- Динамические лейблы типов заметок
"""

import pytest

from apps.crm.services.agents_client import AgentsClient


@pytest.fixture
def agents_client():
    """AgentsClient для unit тестов"""
    return AgentsClient(agents_base_url="http://localhost:8001")


@pytest.fixture
def sample_entity_types():
    """Типы сущностей для тестов"""
    return [
        {
            "type_id": "person",
            "name": "People",
            "description": "Физическое лицо",
            "prompt": "Персона - физическое лицо",
            "is_event": False,
            "required_fields": {
                "name": {"label": "Имя", "prompt": "Извлекай имя человека"},
            },
            "optional_fields": {
                "email": {"label": "Email", "prompt": "Извлекай email"},
                "phone": {"label": "Телефон", "prompt": "Извлекай телефон"},
            },
        },
        {
            "type_id": "organization",
            "name": "Organizations",
            "description": "Компания",
            "prompt": "Организация - компания, фирма",
            "is_event": False,
            "required_fields": {
                "name": {"label": "Название", "prompt": "Извлекай название"},
            },
            "optional_fields": {},
        },
        {
            "type_id": "meeting",
            "name": "Meetings",
            "description": "Встреча",
            "prompt": "Встреча - запланированное мероприятие",
            "is_event": True,
            "required_fields": {
                "name": {"label": "Название", "prompt": "Извлекай название встречи"},
            },
            "optional_fields": {
                "date": {"label": "Дата", "prompt": "Извлекай дату"},
            },
        },
        {
            "type_id": "call",
            "name": "Calls",
            "description": "Звонок",
            "prompt": "Звонок - телефонный разговор",
            "is_event": True,
            "required_fields": {
                "name": {"label": "Тема", "prompt": "Извлекай тему звонка"},
            },
            "optional_fields": {},
        },
    ]


class TestFormatEntityTypesPrompt:
    """Тесты на _format_entity_types_prompt"""
    
    def test_separates_regular_and_event_types(self, agents_client, sample_entity_types):
        """Тест: разделяет обычные типы и event типы"""
        result = agents_client._format_entity_types_prompt(sample_entity_types)
        
        assert "**Обычные сущности:**" in result
        assert "**События (meeting, call, email):**" in result
    
    def test_includes_type_id_and_name(self, agents_client, sample_entity_types):
        """Тест: включает type_id и name"""
        result = agents_client._format_entity_types_prompt(sample_entity_types)
        
        assert "### person (People)" in result
        assert "### organization (Organizations)" in result
        assert "### meeting (Meetings)" in result
        assert "### call (Calls)" in result
    
    def test_marks_event_types(self, agents_client, sample_entity_types):
        """Тест: помечает event типы"""
        result = agents_client._format_entity_types_prompt(sample_entity_types)
        
        # Event типы должны быть помечены
        assert "*Это тип события*" in result
    
    def test_includes_prompt_description(self, agents_client, sample_entity_types):
        """Тест: включает prompt/description типа"""
        result = agents_client._format_entity_types_prompt(sample_entity_types)
        
        assert "Персона - физическое лицо" in result
        assert "Встреча - запланированное мероприятие" in result
    
    def test_includes_required_fields(self, agents_client, sample_entity_types):
        """Тест: включает обязательные поля"""
        result = agents_client._format_entity_types_prompt(sample_entity_types)
        
        assert "- name (обязательное):" in result
        assert "Извлекай имя человека" in result
    
    def test_includes_optional_fields(self, agents_client, sample_entity_types):
        """Тест: включает опциональные поля"""
        result = agents_client._format_entity_types_prompt(sample_entity_types)
        
        assert "- email:" in result
        assert "Извлекай email" in result
    
    def test_empty_entity_types(self, agents_client):
        """Тест: пустой список типов"""
        result = agents_client._format_entity_types_prompt([])
        
        assert result == ""
    
    def test_only_regular_types(self, agents_client):
        """Тест: только обычные типы без event"""
        types = [
            {
                "type_id": "person",
                "name": "People",
                "is_event": False,
                "required_fields": {},
                "optional_fields": {},
            },
        ]
        
        result = agents_client._format_entity_types_prompt(types)
        
        assert "**Обычные сущности:**" in result
        assert "**События" not in result
    
    def test_only_event_types(self, agents_client):
        """Тест: только event типы"""
        types = [
            {
                "type_id": "meeting",
                "name": "Meetings",
                "is_event": True,
                "required_fields": {},
                "optional_fields": {},
            },
        ]
        
        result = agents_client._format_entity_types_prompt(types)
        
        assert "**События (meeting, call, email):**" in result
        assert "**Обычные сущности:**" not in result


class TestFormatRelationshipsPrompt:
    """Тесты на _format_relationships_prompt"""
    
    def test_includes_basic_relationship_types(self, agents_client, sample_entity_types):
        """Тест: включает базовые типы связей"""
        result = agents_client._format_relationships_prompt(sample_entity_types)
        
        assert "works_for" in result
        assert "works_at" in result
        assert "works_on" in result
        assert "knows" in result
        assert "manages" in result
        assert "related_to" in result
    
    def test_includes_event_relationships_when_has_events(self, agents_client, sample_entity_types):
        """Тест: включает связи с событиями когда есть event типы"""
        result = agents_client._format_relationships_prompt(sample_entity_types)
        
        assert "participated_in" in result
        assert "mentioned_in" in result
        assert "organized_by" in result
    
    def test_no_event_relationships_without_events(self, agents_client):
        """Тест: нет связей с событиями когда нет event типов"""
        types = [
            {"type_id": "person", "is_event": False},
        ]
        
        result = agents_client._format_relationships_prompt(types)
        
        assert "participated_in" not in result
        assert "organized_by" not in result
    
    def test_includes_weight_explanation(self, agents_client, sample_entity_types):
        """Тест: включает объяснение weight"""
        result = agents_client._format_relationships_prompt(sample_entity_types)
        
        assert "weight" in result
        assert "1.0" in result
        assert "0.8" in result
        assert "0.5" in result
    
    def test_includes_json_format(self, agents_client, sample_entity_types):
        """Тест: включает формат JSON для связей"""
        result = agents_client._format_relationships_prompt(sample_entity_types)
        
        assert '"source"' in result
        assert '"target"' in result
        assert '"type"' in result
        assert '"weight"' in result
        assert '"attributes"' in result


class TestFormatNoteContext:
    """Тесты на _format_note_context"""
    
    def test_includes_note_type(self, agents_client, sample_entity_types):
        """Тест: включает тип заметки"""
        note_context = {
            "note_type": "meeting_minutes",
            "title": "Team Sync",
            "note_date": "2024-01-15",
        }
        
        result = agents_client._format_note_context(
            note_context, None, sample_entity_types
        )
        
        assert "Протокол встречи" in result
    
    def test_includes_title(self, agents_client):
        """Тест: включает название заметки"""
        note_context = {
            "note_type": "freeform",
            "title": "Important Notes",
            "note_date": "2024-01-15",
        }
        
        result = agents_client._format_note_context(note_context)
        
        assert "Important Notes" in result
    
    def test_includes_date(self, agents_client):
        """Тест: включает дату"""
        note_context = {
            "note_type": "freeform",
            "title": "Notes",
            "note_date": "2024-01-15",
        }
        
        result = agents_client._format_note_context(note_context)
        
        assert "2024-01-15" in result
    
    def test_includes_author_info(self, agents_client):
        """Тест: включает информацию об авторе"""
        note_context = {
            "note_type": "meeting_minutes",
            "title": "Meeting",
            "note_date": "2024-01-15",
        }
        author_info = {
            "name": "John Smith",
            "user_id": "user_123",
        }
        
        result = agents_client._format_note_context(note_context, author_info)
        
        assert "John Smith" in result
        assert "Автор/организатор" in result
    
    def test_includes_organized_by_instruction_for_events(self, agents_client, sample_entity_types):
        """Тест: включает инструкцию organized_by для событий"""
        note_context = {
            "note_type": "meeting_minutes",
            "title": "Meeting",
            "note_date": "2024-01-15",
        }
        author_info = {
            "name": "John Smith",
            "user_id": "user_123",
        }
        
        result = agents_client._format_note_context(
            note_context, author_info, sample_entity_types
        )
        
        assert "организатором" in result
        assert "organized_by" in result
    
    def test_no_organized_by_for_freeform(self, agents_client, sample_entity_types):
        """Тест: нет инструкции organized_by для freeform"""
        note_context = {
            "note_type": "freeform",
            "title": "Notes",
            "note_date": "2024-01-15",
        }
        author_info = {
            "name": "John Smith",
            "user_id": "user_123",
        }
        
        result = agents_client._format_note_context(
            note_context, author_info, sample_entity_types
        )
        
        assert "organized_by" not in result
    
    def test_dynamic_type_labels_from_entity_types(self, agents_client):
        """Тест: динамические лейблы из entity_types"""
        entity_types = [
            {
                "type_id": "meeting",
                "name": "Team Meetings",
                "is_event": True,
            },
        ]
        note_context = {
            "note_type": "meeting_minutes",
            "title": "Sync",
            "note_date": "2024-01-15",
        }
        
        result = agents_client._format_note_context(note_context, None, entity_types)
        
        assert "Team Meetings" in result
    
    def test_call_log_type(self, agents_client, sample_entity_types):
        """Тест: тип call_log"""
        note_context = {
            "note_type": "call_log",
            "title": "Client Call",
            "note_date": "2024-01-15",
        }
        
        result = agents_client._format_note_context(
            note_context, None, sample_entity_types
        )
        
        assert "Лог звонка" in result
    
    def test_custom_event_type(self, agents_client):
        """Тест: кастомный event тип"""
        entity_types = [
            {
                "type_id": "webinar",
                "name": "Webinars",
                "is_event": True,
            },
        ]
        note_context = {
            "note_type": "webinar",
            "title": "Product Demo",
            "note_date": "2024-01-15",
        }
        
        result = agents_client._format_note_context(note_context, None, entity_types)
        
        assert "Webinars" in result


class TestExtractEntitiesPromptAssembly:
    """Тесты на сборку полного промпта в extract_entities"""
    
    @pytest.mark.asyncio
    async def test_prompt_includes_all_sections(self, agents_client, sample_entity_types):
        """Тест: промпт включает все секции"""
        # Тестируем сборку промпта без реального вызова API
        # Используем приватные методы напрямую
        
        note_context = {
            "note_type": "meeting_minutes",
            "title": "Team Meeting",
            "note_date": "2024-01-15",
        }
        author_info = {
            "name": "John Smith",
            "user_id": "user_123",
        }
        
        # Собираем части промпта как в extract_entities
        message_parts = []
        
        context_info = agents_client._format_note_context(
            note_context, author_info, sample_entity_types
        )
        message_parts.append(context_info)
        
        message_parts.append("\n## Текст для анализа:\nTest text content")
        
        types_info = agents_client._format_entity_types_prompt(sample_entity_types)
        message_parts.append(f"\n\n## Доступные типы сущностей:\n{types_info}")
        
        relationships_info = agents_client._format_relationships_prompt(sample_entity_types)
        message_parts.append(f"\n\n## Связи между сущностями:\n{relationships_info}")
        
        full_prompt = "\n".join(message_parts)
        
        # Проверяем наличие всех секций
        assert "## Контекст документа:" in full_prompt
        assert "## Текст для анализа:" in full_prompt
        assert "## Доступные типы сущностей:" in full_prompt
        assert "## Связи между сущностями:" in full_prompt
        
        # Проверяем содержимое
        assert "John Smith" in full_prompt
        assert "Team Meeting" in full_prompt
        assert "person" in full_prompt
        assert "meeting" in full_prompt
        assert "works_for" in full_prompt
        assert "participated_in" in full_prompt
        assert "organized_by" in full_prompt

