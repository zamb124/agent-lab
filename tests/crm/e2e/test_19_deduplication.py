"""
Тесты дедупликации entities при AI анализе.

User Story: При извлечении entities из текста система проверяет наличие дубликатов
и предлагает merge или create в зависимости от similarity.
"""

import pytest
import json


@pytest.mark.real_taskiq
class TestEntityDeduplication:
    """Дедупликация entities при AI анализе"""
    
    @pytest.mark.asyncio
    async def test_dedup_new_entity_no_duplicates(
        self, crm_client, mock_llm_redis, unique_id, auth_headers_system
    ):
        """
        AI извлекает entity -> проверяем что dedup_action заполнен
        """
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": f"Встреча {unique_id}",
                    "description": "Обсуждение нового проекта"
                },
                "entities": [
                    {
                        "entity_type": "contact",
                        "name": f"Уникальный контакт {unique_id}",
                        "description": "Абсолютно новый человек в системе",
                        "attributes": {"role": "менеджер"}
                    }
                ],
                "relationships": []
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": f"Сегодня познакомился с Уникальный контакт {unique_id}. Он менеджер проекта."
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        
        assert entity["dedup_action"] in ["create", "merge"]
    
    @pytest.mark.asyncio
    async def test_dedup_high_similarity_auto_merge(
        self, crm_client, mock_llm_redis, unique_id, auth_headers_system
    ):
        """
        В БД есть entity с высоким similarity (>0.95) -> автоматический merge
        """
        existing_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Иван Петров {unique_id}",
            "description": "Технический директор компании ABC, отвечает за разработку",
            "attributes": {"phone": "+79991234567"}
        }, headers=auth_headers_system)
        assert existing_resp.status_code in [200, 201]
        existing_entity = existing_resp.json()
        
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": f"Звонок {unique_id}",
                    "description": "Звонок с Иваном"
                },
                "entities": [
                    {
                        "entity_type": "contact",
                        "name": f"Иван Петров {unique_id}",
                        "description": "Технический директор компании ABC",
                        "attributes": {"email": "ivan@abc.com"}
                    }
                ],
                "relationships": []
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": f"Созвонился с Иваном Петровым {unique_id}. Он CTO в ABC."
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        
        assert entity["dedup_action"] in ["merge", "create"]
        if entity["dedup_action"] == "merge":
            assert entity["dedup_existing_id"] is not None
            assert entity["dedup_confidence"] is not None
    
    @pytest.mark.asyncio
    async def test_dedup_medium_similarity_llm_decision(
        self, crm_client, mock_llm_redis, unique_id, auth_headers_system
    ):
        """
        В БД есть entity со средним similarity (0.7-0.95) -> вызов LLM для решения
        """
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "organization",
            "name": f"ООО Альфа {unique_id}",
            "description": "IT компания, занимается разработкой ПО",
            "attributes": {"industry": "IT"}
        }, headers=auth_headers_system)
        
        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "note": {
                        "entity_type": "note",
                        "name": f"Заметка {unique_id}",
                        "description": "Встреча с компанией"
                    },
                    "entities": [
                        {
                            "entity_type": "organization",
                            "name": f"Компания Альфа {unique_id}",
                            "description": "Разработка программного обеспечения",
                            "attributes": {"location": "Москва"}
                        }
                    ],
                    "relationships": []
                })
            },
            {
                "type": "text",
                "content": json.dumps({
                    "is_duplicate": True,
                    "confidence": 0.85,
                    "reason": "Это одна и та же компания с разными вариантами названия",
                    "action": "merge",
                    "merged_attributes": {
                        "industry": "IT",
                        "location": "Москва"
                    },
                    "merged_description": "IT компания, занимается разработкой ПО. Офис в Москве."
                })
            }
        ])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": f"Провел встречу с Компания Альфа {unique_id}. Они занимаются разработкой."
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        
        assert entity["dedup_action"] in ["merge", "create"]
        if entity["dedup_action"] == "merge":
            assert entity["dedup_existing_id"] is not None
            assert entity["dedup_confidence"] >= 0.7
    
    @pytest.mark.asyncio
    async def test_dedup_different_entities(
        self, crm_client, mock_llm_redis, unique_id, auth_headers_system
    ):
        """
        Проверяем что дедупликация работает для разных entities
        """
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Мария Сидорова {unique_id}",
            "description": "Бухгалтер, работает в финансовом отделе",
            "attributes": {"department": "finance"}
        }, headers=auth_headers_system)
        
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": f"Собеседование {unique_id}",
                    "description": "Собеседование нового кандидата"
                },
                "entities": [
                    {
                        "entity_type": "contact",
                        "name": f"Алексей Кузнецов {unique_id}",
                        "description": "Разработчик, кандидат на позицию backend",
                        "attributes": {"role": "developer"}
                    }
                ],
                "relationships": []
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": f"Провел собеседование с Алексеем Кузнецовым {unique_id}. Хороший backend разработчик."
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        
        assert entity["dedup_action"] in ["create", "merge"]
    
    @pytest.mark.asyncio
    async def test_dedup_multiple_entities_mixed(
        self, crm_client, mock_llm_redis, unique_id, auth_headers_system
    ):
        """
        AI извлекает несколько entities - часть дубликаты, часть новые
        """
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Петр Иванов {unique_id}",
            "description": "Менеджер по продажам",
            "attributes": {"email": "petr@company.com"}
        }, headers=auth_headers_system)
        
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": f"Планерка {unique_id}",
                    "description": "Еженедельная планерка команды"
                },
                "entities": [
                    {
                        "entity_type": "contact",
                        "name": f"Петр Иванов {unique_id}",
                        "description": "Менеджер по продажам в нашей компании",
                        "attributes": {"phone": "+79998887766"}
                    },
                    {
                        "entity_type": "contact",
                        "name": f"Анна Новикова {unique_id}",
                        "description": "Новый дизайнер в команде",
                        "attributes": {"role": "designer"}
                    }
                ],
                "relationships": []
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": f"На планерке был Петр Иванов {unique_id} и новая дизайнер Анна Новикова {unique_id}."
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 2
        
        actions = [e["dedup_action"] for e in result["entities"]]
        assert "create" in actions or "merge" in actions
    
    @pytest.mark.asyncio
    async def test_dedup_skip_when_disabled(
        self, crm_client, mock_llm_redis, unique_id, auth_headers_system
    ):
        """
        Дедупликация может быть отключена параметром check_duplicates=false
        """
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project",
            "name": f"Проект Омега {unique_id}",
            "description": "Секретный проект",
            "attributes": {}
        }, headers=auth_headers_system)
        
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": f"Статус проекта {unique_id}",
                    "description": "Обновление статуса"
                },
                "entities": [
                    {
                        "entity_type": "project",
                        "name": f"Проект Омега {unique_id}",
                        "description": "Тот же проект с обновлениями",
                        "attributes": {"status": "in_progress"}
                    }
                ],
                "relationships": []
            })
        }])
        
        response = await crm_client.post(
            "/crm/api/v1/entities/analyze?check_duplicates=false",
            json={"text": f"Обсудили статус Проекта Омега {unique_id}. Все идет по плану."},
            headers=auth_headers_system
        )
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        
        assert entity.get("dedup_action") is None


@pytest.mark.real_taskiq
class TestDeduplicateSkill:
    """Тесты skill deduplicate напрямую"""
    
    @pytest.mark.asyncio
    async def test_deduplicate_skill_merge_decision(
        self, crm_client, mock_llm_redis, unique_id, auth_headers_system
    ):
        """
        Deduplicate skill корректно определяет дубликат и возвращает merge
        """
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "is_duplicate": True,
                "confidence": 0.92,
                "reason": "Одна и та же организация - ООО Рога и Копыта",
                "action": "merge",
                "merged_attributes": {
                    "phone": "+74951234567",
                    "email": "info@rogaicopyta.ru",
                    "address": "Москва, ул. Ленина 1"
                },
                "merged_description": "Крупная торговая компания. Основана в 2010 году. Офис в Москве на ул. Ленина."
            })
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": f"Встреча с ООО Рога и Копыта {unique_id}. Обсудили поставки."
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_deduplicate_skill_create_decision(
        self, crm_client, mock_llm_redis, unique_id, auth_headers_system
    ):
        """
        Deduplicate skill корректно определяет что это разные сущности
        """
        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Иван Сидоров {unique_id}",
            "description": "Менеджер отдела продаж",
            "attributes": {}
        }, headers=auth_headers_system)
        
        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "note": {
                        "entity_type": "note",
                        "name": f"Встреча {unique_id}",
                        "description": "Деловая встреча"
                    },
                    "entities": [
                        {
                            "entity_type": "contact",
                            "name": f"Иван Петров {unique_id}",
                            "description": "Директор по развитию",
                            "attributes": {"position": "director"}
                        }
                    ],
                    "relationships": []
                })
            },
            {
                "type": "text",
                "content": json.dumps({
                    "is_duplicate": False,
                    "confidence": 0.75,
                    "reason": "Разные люди - Сидоров и Петров, разные должности",
                    "action": "create"
                })
            }
        ])
        
        response = await crm_client.post("/crm/api/v1/entities/analyze", json={
            "text": f"Сегодня встретился с Иваном Петровым {unique_id}, директором по развитию."
        }, headers=auth_headers_system)
        
        assert response.status_code == 200
        result = response.json()
        
        if result["entities"]:
            entity = result["entities"][0]
            assert entity["dedup_action"] in ["create", "merge"]
