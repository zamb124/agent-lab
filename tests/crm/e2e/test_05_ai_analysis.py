"""
Тесты AI анализа текста с извлечением entities и relationships.

User Story: AI автоматически анализирует текст, выделяет проекты, людей, задачи и суммаризирует.
"""

import pytest
import json


@pytest.mark.real_taskiq
class TestAIAnalysis:
    """AI извлечение entities, relationships и задач"""
    
    @pytest.mark.asyncio
    async def test_ai_extract_note_with_entities(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """AI извлекает note + entities + relationships из текста"""
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "entity_subtype": "meeting",
                    "name": "Встреча с Иваном",
                    "description": "Обсудили проект X. Иван предложил нанять Петра для разработки.",
                    "note_date": "2024-01-06"
                },
                "entities": [
                    {
                        "entity_type": "contact",
                        "name": "Иван Иванов",
                        "attributes": {"role": "менеджер"}
                    },
                    {
                        "entity_type": "contact",
                        "name": "Петр Петров",
                        "attributes": {"role": "разработчик"}
                    },
                    {
                        "entity_type": "project",
                        "name": "Проект X",
                        "attributes": {"status": "в разработке"}
                    }
                ],
                "relationships": [
                    {
                        "source_entity_id": "note_id",
                        "target_entity_id": "ivan_id",
                        "relationship_type": "mentions"
                    },
                    {
                        "source_entity_id": "note_id",
                        "target_entity_id": "project_x_id",
                        "relationship_type": "mentions"
                    }
                ]
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": "Сегодня встретился с Иваном. Обсудили проект X. Иван предложил нанять Петра."
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["note"] is not None
        assert result["note"]["entity_type"] == "note"
        assert result["note"]["entity_subtype"] == "meeting"
        
        assert len(result["entities"]) == 3
        entity_types = [e["entity_type"] for e in result["entities"]]
        assert "contact" in entity_types
        assert "project" in entity_types
        
        assert len(result["relationships"]) >= 2
    
    @pytest.mark.asyncio
    async def test_ai_extract_tasks(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """AI извлекает задачи с дедлайнами и приоритетами"""
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "План задач на неделю"
                },
                "entities": [
                    {
                        "entity_type": "task",
                        "name": "Подготовить отчет",
                        "description": "Квартальный отчет для руководства",
                        "due_date": "2024-01-10",
                        "priority": "urgent",
                        "assignees": ["ivan"]
                    },
                    {
                        "entity_type": "task",
                        "name": "Созвониться с клиентом",
                        "description": "Обсудить детали контракта",
                        "due_date": "2024-01-08",
                        "priority": "high"
                    },
                    {
                        "entity_type": "task",
                        "name": "Обновить документацию",
                        "due_date": "2024-01-15",
                        "priority": "medium"
                    }
                ],
                "relationships": []
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": "Нужно подготовить отчет к 10 января (срочно, Иван). Также созвониться с клиентом до 8 января. Обновить документацию к 15 числу."
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        tasks = [e for e in result["entities"] if e["entity_type"] == "task"]
        assert len(tasks) == 3
        
        urgent_task = next((t for t in tasks if t["priority"] == "urgent"), None)
        assert urgent_task is not None
        assert urgent_task["due_date"] == "2024-01-10"
        assert "ivan" in urgent_task["assignees"]
    
    @pytest.mark.asyncio
    async def test_ai_summarize_text(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """AI суммаризирует длинный текст"""
        long_text = """Сегодня была продуктивная встреча с командой. 
        Мы обсудили текущий прогресс по проекту X, который находится на 75% готовности.
        Иван предложил нанять дополнительного разработчика для ускорения работы.
        Петр согласился помочь с backend частью. Анна возьмет на себя тестирование.
        Следующая встреча назначена на следующую неделю.
        Основные договоренности: начать разработку новой фичи, провести код-ревью, подготовить документацию."""
        
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "entity_subtype": "meeting",
                    "name": "Встреча команды",
                    "description": "Обсудили проект X (75% готовности). Решили нанять разработчика. Петр - backend, Анна - тестирование. Следующая встреча через неделю."
                },
                "entities": [
                    {"entity_type": "project", "name": "Проект X"},
                    {"entity_type": "contact", "name": "Иван"},
                    {"entity_type": "contact", "name": "Петр"},
                    {"entity_type": "contact", "name": "Анна"}
                ],
                "relationships": []
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": long_text
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        note = result["note"]
        assert note is not None
        assert len(note["description"]) < len(long_text)
        description_lower = note["description"].lower()
        assert "проект x" in description_lower or "проекта x" in description_lower
    
    @pytest.mark.asyncio
    async def test_ai_extract_with_mentioned_entities(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """AI учитывает явно упомянутые entities через @"""
        existing_entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Существующий контакт {unique_id}",
            "attributes": {"email": "existing@example.com"}
        }, headers=auth_headers_system)
        existing_id = existing_entity_resp.json()["entity_id"]
        
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "Звонок с клиентом",
                    "description": "Обсудили условия сотрудничества"
                },
                "entities": [],
                "relationships": [
                    {
                        "source_entity_id": "note_id",
                        "target_entity_id": existing_id,
                        "relationship_type": "mentions"
                    }
                ]
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": "Созвонился с клиентом. Обсудили условия.",
            "mentioned_entity_ids": [existing_id]
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        relationships = result["relationships"]
        mentioned_rel = next((r for r in relationships if r["target_entity_id"] == existing_id), None)
        assert mentioned_rel is not None
    
    @pytest.mark.asyncio
    async def test_ai_extract_specific_entity_types(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """AI извлекает только указанные типы entities"""
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "Встреча"
                },
                "entities": [
                    {"entity_type": "contact", "name": "Иван"},
                    {"entity_type": "contact", "name": "Петр"}
                ],
                "relationships": []
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": "Встретились с Иваном и Петром. Обсудили проект X.",
            "extract_entity_types": ["contact"]
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        all_contacts = all(e["entity_type"] == "contact" for e in result["entities"])
        assert all_contacts
    
    @pytest.mark.asyncio
    async def test_ai_extract_custom_relationship_types(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """AI извлекает кастомные типы связей"""
        await crm_client.post("/crm/api/v1/relationships/types/", json={
            "type_id": f"works_on_{unique_id}",
            "name": "Работает над",
            "prompt": "Ищи кто над чем работает",
            "is_directed": True
        }, headers=auth_headers_system)
        
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "Распределение задач"
                },
                "entities": [
                    {"entity_type": "contact", "name": "Иван"},
                    {"entity_type": "project", "name": "Проект A"}
                ],
                "relationships": [
                    {
                        "source_entity_id": "ivan_id",
                        "target_entity_id": "project_a_id",
                        "relationship_type": f"works_on_{unique_id}"
                    }
                ]
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": "Иван работает над проектом A.",
            "extract_relationship_types": [f"works_on_{unique_id}"]
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        custom_rel = next(
            (r for r in result["relationships"] if r["relationship_type"] == f"works_on_{unique_id}"),
            None
        )
        assert custom_rel is not None

