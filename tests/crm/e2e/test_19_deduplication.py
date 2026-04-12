"""
Тесты дедупликации entities при AI анализе.

User Story: При извлечении entities из текста система проверяет наличие дубликатов
и предлагает merge или create в зависимости от similarity.
"""

import pytest
import json

from tests.fixtures.crm_test_setup import wait_for_crm_semantic_search_hit


async def _analyze_note(
    crm_client,
    headers: dict,
    note_id: str,
    **extra,
):
    """Запускает анализ заметки через POST /tasks/note-analyze и ждёт завершения.

    Возвращает (task_row, ai_analysis_draft).
    """
    import asyncio, time
    body = {"note_id": note_id, **extra}
    start = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json=body,
        headers=headers,
    )
    assert start.status_code == 202, start.text
    task_id = start.json()["task_id"]
    deadline = time.monotonic() + 60.0
    last = {}
    while time.monotonic() < deadline:
        tr = await crm_client.get(f"/crm/api/v1/tasks/{task_id}", headers=headers)
        assert tr.status_code == 200, tr.text
        last = tr.json()
        if last.get("status") in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.4)
    assert last.get("status") == "completed", f"task failed: {last.get('error_message')}"
    nr = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=headers)
    draft = nr.json().get("attributes", {}).get("ai_analysis_draft") or {}
    return last, draft




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
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Знакомство {unique_id}",
            "description": f"Сегодня познакомился с Уникальный контакт {unique_id}. Он менеджер проекта.",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        
        assert entity["dedup_action"] in ["create", "merge"]
        assert entity["dedup_confidence"] is not None
        if entity["dedup_action"] == "merge":
            assert entity["dedup_existing_id"] is not None
    
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
            "attributes": {"phone": "+79991234567"},
            "namespace": "default",
        }, headers=auth_headers_system)
        assert existing_resp.status_code in [200, 201]
        existing_entity = existing_resp.json()

        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=f"Иван Петров {unique_id}",
            entity_type="contact",
        )
        
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
        }, {
            "type": "text",
            "content": json.dumps({
                "is_duplicate": True,
                "confidence": 0.96,
                "reason": "Это один и тот же контакт",
                "action": "merge",
                "merged_attributes": {
                    "phone": "+79991234567",
                    "email": "ivan@abc.com"
                },
                "merged_description": "Технический директор компании ABC, отвечает за разработку"
            })
        }])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Звонок {unique_id}",
            "description": f"Созвонился с Иваном Петровым {unique_id}. Он CTO в ABC.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        
        assert entity["dedup_action"] == "merge"
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
            "attributes": {"industry": "IT"},
            "namespace": "default",
        }, headers=auth_headers_system)

        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=f"Альфа {unique_id}",
            entity_type="organization",
        )
        
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
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Встреча {unique_id}",
            "description": f"Провел встречу с Компания Альфа {unique_id}. Они занимаются разработкой.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        
        assert entity["dedup_action"] == "merge"
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

        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=f"Мария Сидорова {unique_id}",
            entity_type="contact",
        )
        
        await mock_llm_redis([
            {
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
            },
            {
                "type": "text",
                "content": json.dumps({
                    "is_duplicate": False,
                    "confidence": 0.82,
                    "reason": "Разные люди с разными ролями",
                    "action": "create",
                    "merged_attributes": None,
                    "merged_description": None
                })
            }
        ])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Собеседование {unique_id}",
            "description": f"Провел собеседование с Алексеем Кузнецовым {unique_id}. Хороший backend разработчик.",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        
        assert entity["dedup_action"] in ["create", "merge"]
        if entity["dedup_action"] == "merge":
            assert entity["dedup_existing_id"] is not None
    
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
            "attributes": {"email": "petr@company.com"},
            "namespace": "default",
        }, headers=auth_headers_system)

        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=f"Петр Иванов {unique_id}",
            entity_type="contact",
        )
        
        await mock_llm_redis([
            {
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
            },
            {
                "type": "text",
                "content": json.dumps({
                    "decisions": [
                        {
                            "pair_index": 0,
                            "is_duplicate": True,
                            "confidence": 0.9,
                            "reason": "Это тот же контакт",
                            "action": "merge",
                            "merged_attributes": {
                                "email": "petr@company.com",
                                "phone": "+79998887766"
                            },
                            "merged_description": "Менеджер по продажам"
                        },
                        {
                            "pair_index": 1,
                            "is_duplicate": False,
                            "confidence": 0.81,
                            "reason": "Новый участник команды",
                            "action": "create",
                            "merged_attributes": None,
                            "merged_description": None
                        }
                    ]
                })
            }
        ])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Планерка {unique_id}",
            "description": f"На планерке был Петр Иванов {unique_id} и новая дизайнер Анна Новикова {unique_id}.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)
        
        assert response.status_code == 200
        result = response.json()
        
        assert isinstance(result["entities"], list)
        assert len(result["entities"]) >= 1
        for entity in result["entities"]:
            assert entity["dedup_action"] in ["create", "merge"]
            if entity["dedup_action"] == "merge":
                assert entity["dedup_existing_id"] is not None
    
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
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Статус {unique_id}",
            "description": f"Обсудили статус Проекта Омега {unique_id}. Все идет по плану.",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id, check_duplicates=False)
        
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
        existing_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "organization",
            "name": f"ООО Рога и Копыта {unique_id}",
            "description": "Крупная торговая компания",
            "attributes": {"phone": "+74951234567"},
            "namespace": "default",
        }, headers=auth_headers_system)
        assert existing_resp.status_code in [200, 201]
        existing_entity = existing_resp.json()

        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=f"Рога и Копыта {unique_id}",
            entity_type="organization",
        )
        
        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "note": {
                        "entity_type": "note",
                        "name": f"Встреча {unique_id}",
                        "description": "Встреча по поставкам"
                    },
                    "entities": [
                        {
                            "entity_type": "organization",
                            "name": f"ООО Рога и Копыта {unique_id}",
                            "description": "Торговая компания, обсуждение поставок",
                            "attributes": {"email": "info@rogaicopyta.ru"}
                        }
                    ],
                    "relationships": []
                })
            },
            {
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
            }
        ])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Встреча {unique_id}",
            "description": f"Встреча с ООО Рога и Копыта {unique_id}. Обсудили поставки.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)
        
        assert response.status_code == 200
        result = response.json()
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        assert entity["dedup_action"] == "merge"
        assert entity["dedup_existing_id"] is not None
        assert entity["dedup_confidence"] >= 0.9
    
    @pytest.mark.asyncio
    async def test_deduplicate_skill_create_decision(
        self, crm_client, mock_llm_redis, unique_id, auth_headers_system
    ):
        """
        При check_duplicates=false -> dedup не запускается, action=create.
        Проверяем что AI analyze корректно возвращает entity без дедупликации.
        """
        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "note": {
                        "entity_type": "note",
                        "name": f"Записка {unique_id}",
                        "description": "Техническая записка"
                    },
                    "entities": [
                        {
                            "entity_type": "contact",
                            "name": f"Новый контакт {unique_id}",
                            "description": "Новый человек в системе",
                            "attributes": {"position": "engineer"}
                        }
                    ],
                    "relationships": []
                })
            }
        ])
        
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Знакомство {unique_id}",
            "description": f"Познакомился с новым контактом {unique_id}, инженер.",
        }, headers=auth_headers_system)
        note_id = note_resp.json()["entity_id"]

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id, check_duplicates=False)
        
        assert response.status_code == 200
        result = response.json()
        
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        assert entity.get("dedup_action") is None, "dedup не запускался при check_duplicates=false"
        assert entity.get("dedup_existing_id") is None
