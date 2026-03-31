"""
Тесты корректировки результатов AI анализа.

User Story: Возможность править результаты AI и дополнять данные по entities.
"""

import pytest
import json

_META = {"dates_mentioned": [], "places_mentioned": [], "key_topics": []}


@pytest.mark.real_taskiq
class TestAICorrection:
    """Корректировка извлеченных AI данных"""
    
    @pytest.mark.asyncio
    async def test_correct_extracted_entity(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """Пользователь правит entity после AI анализа"""
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "Встреча",
                    "description": "Краткий итог встречи с контактом для CRM",
                },
                "entities": [
                    {
                        "entity_type": "contact",
                        "name": "Иван",
                        "description": "Контакт из встречи, роль менеджер в переговорах",
                        "attributes": {"role": "менеджер"}
                    }
                ],
                "relationships": [],
                "metadata": _META,
            })
        }])
        
        analyze_resp = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": "Встретился с Иваном"
        }, headers=auth_headers_system)
        entities = analyze_resp.json()["entities"]
        
        # Сначала создаём entity на основе AI анализа
        extracted_entity = entities[0]
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": extracted_entity["entity_type"],
            "name": extracted_entity["name"],
            "attributes": extracted_entity.get("attributes", {})
        }, headers=auth_headers_system)
        entity_id = create_resp.json()["entity_id"]
        
        # Теперь корректируем созданную entity
        update_resp = await crm_client.put(f"/crm/api/v1/entities/{entity_id}", json={
            "name": "Иван Иванов",
            "attributes": {
                "role": "старший менеджер",
                "email": "ivan@example.com",
                "phone": "+79991234567"
            }
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system)
        corrected = get_resp.json()
        assert corrected["name"] == "Иван Иванов"
        assert corrected["attributes"]["role"] == "старший менеджер"
        assert "email" in corrected["attributes"]
    
    @pytest.mark.asyncio
    async def test_add_missing_relationship(self, crm_client, unique_id, auth_headers_system):
        """Добавление связи, которую AI не нашел"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Контакт 1 {unique_id}"
        }, headers=auth_headers_system)
        entity1_id = entity1_resp.json()["entity_id"]
        
        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project",
            "name": f"Проект {unique_id}"
        }, headers=auth_headers_system)
        entity2_id = entity2_resp.json()["entity_id"]
        
        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": entity1_id,
            "target_entity_id": entity2_id,
            "relationship_type": "works_on"
        }, headers=auth_headers_system)
        assert rel_resp.status_code == 200
        
        relationship = rel_resp.json()
        assert relationship["source_entity_id"] == entity1_id
        assert relationship["target_entity_id"] == entity2_id
    
    @pytest.mark.asyncio
    async def test_delete_incorrect_entity(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """Удаление ошибочно извлеченной entity"""
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "Встреча",
                    "description": "Заметка о встрече с двумя извлечёнными контактами",
                },
                "entities": [
                    {
                        "entity_type": "contact",
                        "name": "Правильный контакт",
                        "description": "Основной контакт, подтверждённый пользователем",
                    },
                    {
                        "entity_type": "contact",
                        "name": "Ошибочный контакт",
                        "description": "Лишний контакт, который пользователь удалит",
                    },
                ],
                "relationships": [],
                "metadata": _META,
            })
        }])
        
        analyze_resp = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": "Встретился с контактом"
        }, headers=auth_headers_system)
        entities = analyze_resp.json()["entities"]
        
        incorrect_entity_id = None
        for entity_data in entities:
            create_resp = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": entity_data["entity_type"],
                "name": entity_data["name"]
            }, headers=auth_headers_system)
            assert create_resp.status_code == 200
            if "Ошибочный" in entity_data["name"]:
                incorrect_entity_id = create_resp.json()["entity_id"]

        if incorrect_entity_id is None:
            raise ValueError("Ошибочный контакт не найден")
        delete_resp = await crm_client.delete(f"/crm/api/v1/entities/{incorrect_entity_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 200
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{incorrect_entity_id}", headers=auth_headers_system)
        assert get_resp.status_code == 404
    
    @pytest.mark.asyncio
    async def test_merge_duplicate_entities(self, crm_client, unique_id, auth_headers_system):
        """Объединение дублирующихся entities"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Иван {unique_id}",
            "attributes": {"email": "ivan1@example.com"}
        }, headers=auth_headers_system)
        entity1_id = entity1_resp.json()["entity_id"]
        
        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Иван Иванов {unique_id}",
            "attributes": {"phone": "+79991234567"}
        }, headers=auth_headers_system)
        entity2_id = entity2_resp.json()["entity_id"]
        
        update_resp = await crm_client.put(f"/crm/api/v1/entities/{entity1_id}", json={
            "attributes": {
                "email": "ivan1@example.com",
                "phone": "+79991234567"
            }
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200
        
        await crm_client.delete(f"/crm/api/v1/entities/{entity2_id}", headers=auth_headers_system)
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity1_id}", headers=auth_headers_system)
        merged = get_resp.json()
        assert "email" in merged["attributes"]
        assert "phone" in merged["attributes"]
    
    @pytest.mark.asyncio
    async def test_update_note_after_ai_analysis(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """Корректировка самой заметки после AI анализа"""
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "entity_subtype": "meeting",
                    "name": "Встреча",
                    "description": "Краткое описание итогов встречи для последующей правки",
                },
                "entities": [],
                "relationships": [],
                "metadata": _META,
            })
        }])
        
        analyze_resp = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": "Встреча прошла"
        }, headers=auth_headers_system)
        note_data = analyze_resp.json()["note"]
        
        # Создаём note на основе AI анализа
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": note_data["entity_type"],
            "entity_subtype": note_data.get("entity_subtype"),
            "name": note_data["name"],
            "description": note_data.get("description")
        }, headers=auth_headers_system)
        note_id = create_resp.json()["entity_id"]
        
        # Теперь корректируем созданную note
        update_resp = await crm_client.put(f"/crm/api/v1/entities/{note_id}", json={
            "name": "Встреча команды по проекту X",
            "description": "Детальное описание: обсудили прогресс, приняли решения",
            "tags": ["важно", "проект-x"]
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200
        
        get_resp = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        updated_note = get_resp.json()
        assert "проекту X" in updated_note["name"]
        assert "важно" in updated_note["tags"]

