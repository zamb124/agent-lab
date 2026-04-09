"""
Тесты AI анализа текста с извлечением entities и relationships.

User Story: AI автоматически анализирует текст, выделяет проекты, людей, задачи и суммаризирует.
"""

import pytest
import json

_META = {"dates_mentioned": [], "places_mentioned": [], "key_topics": []}


@pytest.mark.real_taskiq
class TestAIAnalysis:
    """AI извлечение entities, relationships и задач"""
    
    @pytest.mark.asyncio
    async def test_ai_extract_note_with_entities(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """AI извлекает note + entities + relationships из текста"""
        note_title = "Встреча с Иваном"
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": note_title,
                    "description": "Обсудили проект X. Иван предложил нанять Петра для разработки.",
                    "note_date": "2024-01-06"
                },
                "entities": [
                    {
                        "entity_type": "task",
                        "name": "Иван Иванов",
                        "description": "Менеджер проекта, ведёт переговоры и сроки",
                        "attributes": {"role": "менеджер"}
                    },
                    {
                        "entity_type": "task",
                        "name": "Петр Петров",
                        "description": "Разработчик, подключается к задачам бэкенда",
                        "attributes": {"role": "разработчик"}
                    }
                ],
                "relationships": [
                    {
                        "source_type": "note",
                        "source_name": note_title,
                        "target_type": "task",
                        "target_name": "Иван Иванов",
                        "relationship_type": "mentions",
                        "weight": 1.0,
                    },
                    {
                        "source_type": "note",
                        "source_name": note_title,
                        "target_type": "task",
                        "target_name": "Петр Петров",
                        "relationship_type": "mentions",
                        "weight": 1.0,
                    }
                ],
                "metadata": _META,
            })
        }])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Анализ встречи",
            "description": "Сегодня встретился с Иваном. Обсудили проект X. Иван предложил нанять Петра.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]
        
        response = await crm_client.post(f"/crm/api/v1/entities/notes/{note_id}/analyze", json={},
                                         headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        assert result["note"] is not None
        assert result["note"]["entity_type"] == "note"
        assert result["note"]["entity_subtype"] is None
        
        assert len(result["entities"]) == 2
        entity_types = [e["entity_type"] for e in result["entities"]]
        assert "task" in entity_types
        
        assert len(result["relationships"]) >= 2
        for rel in result["relationships"]:
            assert rel.get("draft_relationship_id")
            assert rel.get("source_draft_entity_id")
            assert rel.get("target_draft_entity_id")

    @pytest.mark.asyncio
    async def test_ai_extract_tasks(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """AI извлекает задачи с дедлайнами и приоритетами"""
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "План задач на неделю",
                    "description": "Список приоритетных задач на текущую неделю команды",
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
                        "description": "Актуализировать внутреннюю документацию продукта",
                        "due_date": "2024-01-15",
                        "priority": "medium"
                    }
                ],
                "relationships": [],
                "metadata": _META,
            })
        }])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "План задач",
            "description": "Нужно подготовить отчет к 10 января (срочно, Иван). Также созвониться с клиентом до 8 января. Обновить документацию к 15 числу.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]
        
        response = await crm_client.post(f"/crm/api/v1/entities/notes/{note_id}/analyze", json={},
                                         headers=auth_headers_system)
        
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
                    "name": "Встреча команды",
                    "description": "Обсудили проект X (75% готовности). Решили нанять разработчика. Петр - backend, Анна - тестирование. Следующая встреча через неделю."
                },
                "entities": [
                    {"entity_type": "task", "name": "Проект X", "description": "Текущий проект с прогрессом и рисками"},
                    {"entity_type": "task", "name": "Иван", "description": "Участник встречи, предложил усилить команду"},
                    {"entity_type": "task", "name": "Петр", "description": "Отвечает за backend и реализацию сервисов"},
                    {"entity_type": "task", "name": "Анна", "description": "Занимается тестированием и качеством релиза"}
                ],
                "relationships": [],
                "metadata": _META,
            })
        }])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Встреча команды (исходный)",
            "description": long_text,
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]
        
        response = await crm_client.post(f"/crm/api/v1/entities/notes/{note_id}/analyze", json={},
                                         headers=auth_headers_system)
        
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
        existing_name = f"Существующая задача {unique_id}"
        existing_entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": existing_name,
            "description": "Задача уже в CRM для проверки связи analyze по имени",
            "attributes": {"email": "existing@example.com"}
        }, headers=auth_headers_system)
        existing_id = existing_entity_resp.json()["entity_id"]

        call_title = "Звонок с клиентом"
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": call_title,
                    "description": "Обсудили условия сотрудничества"
                },
                "entities": [],
                "relationships": [
                    {
                        "source_type": "note",
                        "source_name": call_title,
                        "target_type": "task",
                        "target_name": existing_name,
                        "relationship_type": "mentions",
                        "weight": 1.0,
                    }
                ],
                "metadata": _META,
            })
        }])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Звонок",
            "description": "Созвонился с клиентом. Обсудили условия.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]
        
        response = await crm_client.post(f"/crm/api/v1/entities/notes/{note_id}/analyze", json={
            "mentioned_entity_ids": [existing_id],
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        relationships = result["relationships"]
        assert len(relationships) >= 1
        rel0 = relationships[0]
        assert rel0["relationship_type"] == "mentions"
        assert rel0.get("target_draft_entity_id")
    
    @pytest.mark.asyncio
    async def test_ai_extract_specific_entity_types(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """AI извлекает только указанные типы entities"""
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "Встреча",
                    "description": "Краткий протокол встречи с участниками команды",
                },
                "entities": [
                    {"entity_type": "task", "name": "Иван", "description": "Участник встречи, статус задач"},
                    {"entity_type": "task", "name": "Петр", "description": "Второй участник, вопросы по срокам"}
                ],
                "relationships": [],
                "metadata": _META,
            })
        }])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Встреча (типы)",
            "description": "Встретились с Иваном и Петром. Обсудили проект X.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]
        
        response = await crm_client.post(f"/crm/api/v1/entities/notes/{note_id}/analyze", json={
            "extract_entity_types": ["task"],
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        all_tasks = all(e["entity_type"] == "task" for e in result["entities"])
        assert all_tasks
    
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
                    "name": "Распределение задач",
                    "description": "Кто над чем работает в текущем спринте команды",
                },
                "entities": [
                    {"entity_type": "task", "name": "Иван", "description": "Сотрудник, назначенный на проект A"},
                    {"entity_type": "task", "name": "Проект A", "description": "Основной проект спринта с дедлайнами"}
                ],
                "relationships": [
                    {
                        "source_type": "task",
                        "source_name": "Иван",
                        "target_type": "task",
                        "target_name": "Проект A",
                        "relationship_type": f"works_on_{unique_id}",
                        "weight": 1.0,
                    }
                ],
                "metadata": _META,
            })
        }])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Распределение",
            "description": "Иван работает над проектом A.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]
        
        response = await crm_client.post(f"/crm/api/v1/entities/notes/{note_id}/analyze", json={
            "extract_relationship_types": [f"works_on_{unique_id}"],
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        custom_rel = next(
            (r for r in result["relationships"] if r["relationship_type"] == f"works_on_{unique_id}"),
            None
        )
        assert custom_rel is not None

    @pytest.mark.asyncio
    async def test_entity_creation_rejects_missing_namespace(self, crm_client, auth_headers_system):
        """422 при попытке создать entity в несуществующем namespace."""
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Заметка в несуществующем namespace",
            "description": "Текст для анализа",
            "namespace": "missing_namespace_for_ai",
        }, headers=auth_headers_system)
        assert note_resp.status_code == 422

