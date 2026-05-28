"""
Тесты дедупликации entities при AI анализе.

User Story: При извлечении entities из текста система проверяет наличие дубликатов
и предлагает merge или create в зависимости от similarity.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str
from tests.fixtures.crm_test_setup import wait_for_crm_semantic_search_hit

MockLlmRedisFactory = Callable[[list[object]], Awaitable[None]]

_META: dict[str, object] = {
    "dates_mentioned": [],
    "places_mentioned": [],
    "key_topics": [],
}


def _mock_analyze_note(name: str, description: str) -> dict[str, object]:
    return {
        "entity_type": "note",
        "name": name,
        "description": description,
        "attributes": {},
        "confidence": 0.9,
    }


def _mock_analyze_entity(
    entity_type: str,
    name: str,
    description: str,
    attributes: dict[str, object],
    *,
    confidence: float = 0.9,
) -> dict[str, object]:
    return {
        "entity_type": entity_type,
        "name": name,
        "description": description,
        "attributes": attributes,
        "confidence": confidence,
    }


def _test_namespace(unique_id: str) -> str:
    return f"g_{unique_id}"


def _json_object(response_payload: object) -> dict[str, object]:
    return json_object(response_payload)


def _http_json(response: Response) -> dict[str, object]:
    return _json_object(cast(object, response.json()))


class _DraftResponse:
    status_code: int
    _draft: dict[str, object]

    def __init__(self, status_code: int, draft: dict[str, object]) -> None:
        self.status_code = status_code
        self._draft = draft

    def json(self) -> dict[str, object]:
        return self._draft


async def _analyze_note(
    crm_client: AsyncClient,
    headers: dict[str, str],
    note_id: str,
    **extra: object,
) -> tuple[dict[str, object], _DraftResponse]:
    """Запускает анализ заметки через POST /tasks/note-analyze и ждёт завершения.

    Возвращает (task_row, ai_analysis_draft).
    """
    body: dict[str, object] = {
        "note_id": note_id,
        "include_attachments": False,
    }
    body.update(extra)
    start = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json=body,
        headers=headers,
    )
    assert start.status_code == 202, start.text
    start_payload = _http_json(start)
    task_id = object_str(start_payload.get("task_id"), field="task_id")
    deadline = time.monotonic() + 60.0
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        tr = await crm_client.get(f"/crm/api/v1/tasks/{task_id}", headers=headers)
        assert tr.status_code == 200, tr.text
        last = _http_json(tr)
        status_raw = last.get("status")
        if status_raw in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.4)
    assert last.get("status") == "completed", f"task failed: {last.get('error_message')}"
    nr = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=headers)
    note_payload = _http_json(nr)
    attributes_raw = note_payload.get("attributes")
    if isinstance(attributes_raw, dict):
        attributes = object_dict(cast(object, attributes_raw), field="attributes")
    else:
        attributes = {}
    draft_raw = attributes.get("ai_analysis_draft")
    if isinstance(draft_raw, dict):
        draft = object_dict(cast(object, draft_raw), field="ai_analysis_draft")
    else:
        draft = {}

    return last, _DraftResponse(nr.status_code, draft)


def _entities(result: dict[str, object]) -> list[dict[str, object]]:
    return object_list(result.get("entities"))


def _first_entity(result: dict[str, object]) -> dict[str, object]:
    entities = _entities(result)
    assert len(entities) >= 1
    return object_dict(entities[0], field="entity")




@pytest.mark.real_taskiq
class TestEntityDeduplication:
    """Дедупликация entities при AI анализе"""

    @pytest.mark.asyncio
    async def test_dedup_new_entity_no_duplicates(
        self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """
        AI извлекает entity -> проверяем что dedup_action заполнен
        """
        namespace = _test_namespace(unique_id)
        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": _mock_analyze_note(
                    f"Встреча {unique_id}",
                    "Обсуждение нового проекта",
                ),
                "entities": [
                    _mock_analyze_entity(
                        "contact",
                        f"Уникальный контакт {unique_id}",
                        "Абсолютно новый человек в системе",
                        {"role": "менеджер"},
                    )
                ],
                "relationships": [],
                "metadata": _META,
                "attachment_summaries": []
            })
        }])

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Знакомство {unique_id}",
            "description": f"Сегодня познакомился с Уникальный контакт {unique_id}. Он менеджер проекта.",
            "namespace": namespace,
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)

        assert response.status_code == 200
        result = response.json()
        entities = object_list(result.get("entities"))
        assert len(entities) == 1
        entity = object_dict(entities[0], field="entity")

        dedup_action = object_str(entity.get("dedup_action"), field="dedup_action")
        assert dedup_action in ["create", "merge"]
        assert entity.get("dedup_confidence") is not None
        if dedup_action == "merge":
            assert entity.get("dedup_existing_id") is not None

    @pytest.mark.asyncio
    async def test_dedup_high_similarity_auto_merge(
        self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """
        В БД есть entity с высоким similarity (>0.95) -> автоматический merge
        """
        namespace = _test_namespace(unique_id)
        existing_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Иван Петров {unique_id}",
            "description": "Технический директор компании ABC, отвечает за разработку",
            "attributes": {"phone": "+79991234567"},
            "namespace": namespace,
        }, headers=auth_headers_system)
        assert existing_resp.status_code in [200, 201]
        existing_resp.json()

        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=f"Иван Петров {unique_id}",
            entity_type="contact",
            namespace=namespace,
        )

        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": _mock_analyze_note(
                    f"Звонок {unique_id}",
                    "Звонок с Иваном",
                ),
                "entities": [
                    _mock_analyze_entity(
                        "contact",
                        f"Иван Петров {unique_id}",
                        "Технический директор компании ABC",
                        {"email": "ivan@abc.com"},
                    )
                ],
                "relationships": [],
                "metadata": _META,
                "attachment_summaries": []
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
            "namespace": namespace,
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)

        assert response.status_code == 200
        result = response.json()
        entity = _first_entity(result)

        assert object_str(entity.get("dedup_action"), field="dedup_action") == "merge"
        assert entity.get("dedup_existing_id") is not None
        assert entity.get("dedup_confidence") is not None

    @pytest.mark.asyncio
    async def test_dedup_medium_similarity_llm_decision(
        self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """
        В БД есть organization с тем же каноническим названием и близким описанием ->
        семантическая проверка выбирает merge (ветка LLM при среднем score или merge без LLM при >0.95).
        """
        namespace = _test_namespace(unique_id)
        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "organization",
            "name": f"ООО Альфа {unique_id}",
            "description": "IT компания, занимается разработкой ПО",
            "attributes": {"industry": "IT"},
            "namespace": namespace,
        }, headers=auth_headers_system)

        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=f"Альфа {unique_id}",
            entity_type="organization",
            namespace=namespace,
        )

        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "note": _mock_analyze_note(
                        f"Заметка {unique_id}",
                        "Встреча с компанией",
                    ),
                    "entities": [
                        _mock_analyze_entity(
                            "organization",
                            f"ООО Альфа {unique_id}",
                            "IT компания, занимается разработкой программного обеспечения",
                            {"location": "Москва"},
                        )
                    ],
                    "relationships": [],
                    "metadata": _META,
                    "attachment_summaries": []
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
            "description": f"Встреча с ООО Альфа {unique_id}: обсудили разработку ПО.",
            "namespace": namespace,
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)

        assert response.status_code == 200
        result = response.json()
        entity = _first_entity(result)

        assert object_str(entity.get("dedup_action"), field="dedup_action") == "merge"
        assert entity.get("dedup_existing_id") is not None
        dedup_confidence = entity.get("dedup_confidence")
        assert isinstance(dedup_confidence, (int, float))
        assert dedup_confidence >= 0.7

    @pytest.mark.asyncio
    async def test_dedup_different_entities(
        self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """
        Проверяем что дедупликация работает для разных entities
        """
        namespace = _test_namespace(unique_id)
        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Мария Сидорова {unique_id}",
            "description": "Бухгалтер, работает в финансовом отделе",
            "attributes": {"department": "finance"},
            "namespace": namespace,
        }, headers=auth_headers_system)

        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=f"Мария Сидорова {unique_id}",
            entity_type="contact",
            namespace=namespace,
        )

        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "note": _mock_analyze_note(
                        f"Собеседование {unique_id}",
                        "Собеседование нового кандидата",
                    ),
                    "entities": [
                        _mock_analyze_entity(
                            "contact",
                            f"Алексей Кузнецов {unique_id}",
                            "Разработчик, кандидат на позицию backend",
                            {"role": "developer"},
                        )
                    ],
                    "relationships": [],
                    "metadata": _META,
                    "attachment_summaries": []
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
            "namespace": namespace,
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)

        assert response.status_code == 200
        result = response.json()
        entity = _first_entity(result)

        dedup_action = object_str(entity.get("dedup_action"), field="dedup_action")
        assert dedup_action in ["create", "merge"]
        if dedup_action == "merge":
            assert entity.get("dedup_existing_id") is not None

    @pytest.mark.asyncio
    async def test_dedup_multiple_entities_mixed(
        self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """
        AI извлекает несколько entities - часть дубликаты, часть новые
        """
        namespace = _test_namespace(unique_id)
        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Петр Иванов {unique_id}",
            "description": "Менеджер по продажам",
            "attributes": {"email": "petr@company.com"},
            "namespace": namespace,
        }, headers=auth_headers_system)

        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=f"Петр Иванов {unique_id}",
            entity_type="contact",
            namespace=namespace,
        )

        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "note": _mock_analyze_note(
                        f"Планерка {unique_id}",
                        "Еженедельная планерка команды",
                    ),
                    "entities": [
                        _mock_analyze_entity(
                            "contact",
                            f"Петр Иванов {unique_id}",
                            "Менеджер по продажам в нашей компании",
                            {"phone": "+79998887766"},
                        ),
                        _mock_analyze_entity(
                            "contact",
                            f"Анна Новикова {unique_id}",
                            "Новый дизайнер в команде",
                            {"role": "designer"},
                        ),
                    ],
                    "relationships": [],
                    "metadata": _META,
                    "attachment_summaries": []
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
            "namespace": namespace,
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)

        assert response.status_code == 200
        result = response.json()

        entities = _entities(result)
        assert len(entities) >= 1
        for entity_raw in entities:
            entity = object_dict(entity_raw, field="entity")
            dedup_action = object_str(entity.get("dedup_action"), field="dedup_action")
            assert dedup_action in ["create", "merge"]
            if dedup_action == "merge":
                assert entity.get("dedup_existing_id") is not None

    @pytest.mark.asyncio
    async def test_dedup_skip_when_disabled(
        self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """
        Дедупликация может быть отключена параметром check_duplicates=false
        """
        namespace = _test_namespace(unique_id)
        _ = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project",
            "name": f"Проект Омега {unique_id}",
            "description": "Секретный проект",
            "attributes": {},
            "namespace": namespace,
        }, headers=auth_headers_system)

        await mock_llm_redis([{
            "type": "text",
            "content": json.dumps({
                "note": _mock_analyze_note(
                    f"Статус проекта {unique_id}",
                    "Обновление статуса",
                ),
                "entities": [
                    _mock_analyze_entity(
                        "project",
                        f"Проект Омега {unique_id}",
                        "Тот же проект с обновлениями",
                        {"status": "in_progress"},
                    )
                ],
                "relationships": [],
                "metadata": _META,
                "attachment_summaries": []
            })
        }])

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Статус {unique_id}",
            "description": f"Обсудили статус Проекта Омега {unique_id}. Все идет по плану.",
            "namespace": namespace,
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id, check_duplicates=False)

        assert response.status_code == 200
        result = response.json()
        entity = _first_entity(result)

        assert entity.get("dedup_action") is None


@pytest.mark.real_taskiq
class TestDeduplicateSkill:
    """Тесты skill deduplicate напрямую"""

    @pytest.mark.asyncio
    async def test_deduplicate_skill_merge_decision(
        self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """
        Deduplicate skill корректно определяет дубликат и возвращает merge
        """
        namespace = _test_namespace(unique_id)
        existing_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "organization",
            "name": f"ООО Рога и Копыта {unique_id}",
            "description": "Крупная торговая компания",
            "attributes": {"phone": "+74951234567"},
            "namespace": namespace,
        }, headers=auth_headers_system)
        assert existing_resp.status_code in [200, 201]
        existing_resp.json()

        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=f"Рога и Копыта {unique_id}",
            entity_type="organization",
            namespace=namespace,
        )

        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "note": _mock_analyze_note(
                        f"Встреча {unique_id}",
                        "Встреча по поставкам",
                    ),
                    "entities": [
                        _mock_analyze_entity(
                            "organization",
                            f"ООО Рога и Копыта {unique_id}",
                            "Торговая компания, обсуждение поставок",
                            {"email": "info@rogaicopyta.ru"},
                        )
                    ],
                    "relationships": [],
                    "metadata": _META,
                    "attachment_summaries": []
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
            "namespace": namespace,
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id)

        assert response.status_code == 200
        result = response.json()
        entity = _first_entity(result)
        assert object_str(entity.get("dedup_action"), field="dedup_action") == "merge"
        assert entity.get("dedup_existing_id") is not None
        dedup_confidence = entity.get("dedup_confidence")
        assert isinstance(dedup_confidence, (int, float))
        assert dedup_confidence >= 0.9

    @pytest.mark.asyncio
    async def test_deduplicate_skill_create_decision(
        self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str]
    ):
        """
        При check_duplicates=false -> dedup не запускается, action=create.
        Проверяем что AI analyze корректно возвращает entity без дедупликации.
        """
        namespace = _test_namespace(unique_id)
        await mock_llm_redis([
            {
                "type": "text",
                "content": json.dumps({
                    "note": _mock_analyze_note(
                        f"Записка {unique_id}",
                        "Техническая записка",
                    ),
                    "entities": [
                        _mock_analyze_entity(
                            "contact",
                            f"Новый контакт {unique_id}",
                            "Новый человек в системе",
                            {"position": "engineer"},
                        )
                    ],
                    "relationships": [],
                    "metadata": _META,
                    "attachment_summaries": []
                })
            }
        ])

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Знакомство {unique_id}",
            "description": f"Познакомился с новым контактом {unique_id}, инженер.",
            "namespace": namespace,
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(crm_client, auth_headers_system, note_id, check_duplicates=False)

        assert response.status_code == 200
        result = response.json()
        entity = _first_entity(result)
        assert entity.get("dedup_action") is None, "dedup не запускался при check_duplicates=false"
        assert entity.get("dedup_existing_id") is None
