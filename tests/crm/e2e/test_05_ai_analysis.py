"""
Тесты AI анализа текста с извлечением entities и relationships.

User Story: AI автоматически анализирует текст, выделяет проекты, людей, задачи и суммаризирует.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import (
    json_object,
    mock_llm_queue_with_analyze_spare,
    object_dict,
    object_list,
    object_str,
    optional_object_dict,
)

MockLlmRedisFactory = Callable[[list[object]], Awaitable[None]]


class _DraftResponse:
    status_code: int
    _draft: dict[str, object]

    def __init__(self, status_code: int, draft: dict[str, object]) -> None:
        self.status_code = status_code
        self._draft = draft

    def json(self) -> dict[str, object]:
        return self._draft


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


async def _analyze_note(
    crm_client: AsyncClient,
    headers: dict[str, str],
    note_id: str,
    *,
    mock_llm_redis: MockLlmRedisFactory | None = None,
    mock_responses: list[object] | None = None,
    prepare_mock: Callable[[], Awaitable[None]] | None = None,
    **extra: object,
) -> tuple[dict[str, object], _DraftResponse]:
    """Запускает анализ заметки через POST /tasks/note-analyze и ждёт завершения.

    Возвращает (task_row, ai_analysis_draft).
    """
    if mock_llm_redis is not None or mock_responses is not None:
        if mock_llm_redis is None or mock_responses is None:
            raise ValueError("mock_llm_redis and mock_responses must be passed together")
        await mock_llm_redis(mock_llm_queue_with_analyze_spare(mock_responses))
    elif prepare_mock is not None:
        await prepare_mock()
    body: dict[str, object] = {
        "note_id": note_id,
        "check_duplicates": False,
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
    task_id_raw = start_payload.get("task_id")
    assert isinstance(task_id_raw, str)
    task_id = task_id_raw
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
    attributes = optional_object_dict(note_payload.get("attributes"))
    draft = optional_object_dict(attributes.get("ai_analysis_draft"))

    return last, _DraftResponse(nr.status_code, draft)


_META: dict[str, object] = {"dates_mentioned": [], "places_mentioned": [], "key_topics": []}


@pytest.mark.real_taskiq
class TestAIAnalysis:
    """AI извлечение entities, relationships и задач"""

    @pytest.mark.asyncio
    async def test_ai_extract_note_with_entities(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ):
        """AI извлекает note + entities + relationships из текста"""
        _ = unique_id
        note_title = "Встреча с Иваном"
        analyze_mock_responses = [{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": note_title,
                    "description": "Обсудили проект X. Иван предложил нанять Петра для разработки.",
                    "note_date": "2024-01-06",
                    "attributes": {},
                    "confidence": 0.92,
                },
                "entities": [
                    {
                        "entity_type": "task",
                        "name": "Иван Иванов",
                        "description": "Менеджер проекта, ведёт переговоры и сроки",
                        "attributes": {"role": "менеджер"},
                        "confidence": 0.9,
                    },
                    {
                        "entity_type": "task",
                        "name": "Петр Петров",
                        "description": "Разработчик, подключается к задачам бэкенда",
                        "attributes": {"role": "разработчик"},
                        "confidence": 0.88,
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
                        "confidence": 0.9,
                    },
                    {
                        "source_type": "note",
                        "source_name": note_title,
                        "target_type": "task",
                        "target_name": "Петр Петров",
                        "relationship_type": "mentions",
                        "weight": 1.0,
                        "confidence": 0.9,
                    }
                ],
                "metadata": _META,
                "attachment_summaries": [],
            })
        }]

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Анализ встречи",
            "description": "Сегодня встретился с Иваном. Обсудили проект X. Иван предложил нанять Петра.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_payload = _http_json(note_resp)
        note_id = object_str(note_payload.get("entity_id"), field="entity_id")

        _, response = await _analyze_note(
            crm_client,
            auth_headers_system,
            note_id,
            mock_llm_redis=mock_llm_redis,
            mock_responses=analyze_mock_responses,
        )

        assert response.status_code == 200
        result = response.json()

        note = object_dict(result.get("note"), field="note")
        assert note["entity_type"] == "note"
        assert note.get("entity_subtype") is None

        entities = object_list(result.get("entities"))
        assert len(entities) == 2
        entity_types = [object_str(entity.get("entity_type"), field="entity_type") for entity in entities]
        assert "task" in entity_types

        relationships = object_list(result.get("relationships"))
        assert len(relationships) >= 2
        for rel in relationships:
            assert rel.get("draft_relationship_id")
            assert rel.get("source_draft_entity_id")
            assert rel.get("target_draft_entity_id")
            assert "confidence" in rel

    @pytest.mark.asyncio
    async def test_ai_extract_tasks(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ):
        """AI извлекает задачи с дедлайнами и приоритетами"""
        _ = unique_id
        analyze_mock_responses = [{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "План задач на неделю",
                    "description": "Список приоритетных задач на текущую неделю команды",
                    "attributes": {},
                    "confidence": 0.9,
                },
                "entities": [
                    {
                        "entity_type": "task",
                        "name": "Подготовить отчет",
                        "description": "Квартальный отчет для руководства",
                        "attributes": {},
                        "confidence": 0.91,
                        "due_date": "2024-01-10",
                        "priority": "urgent",
                        "assignees": ["ivan"]
                    },
                    {
                        "entity_type": "task",
                        "name": "Созвониться с клиентом",
                        "description": "Обсудить детали контракта",
                        "attributes": {},
                        "confidence": 0.9,
                        "due_date": "2024-01-08",
                        "priority": "high"
                    },
                    {
                        "entity_type": "task",
                        "name": "Обновить документацию",
                        "description": "Актуализировать внутреннюю документацию продукта",
                        "attributes": {},
                        "confidence": 0.87,
                        "due_date": "2024-01-15",
                        "priority": "medium"
                    }
                ],
                "relationships": [],
                "metadata": _META,
                "attachment_summaries": [],
            })
        }]

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "План задач",
            "description": "Нужно подготовить отчет к 10 января (срочно, Иван). Также созвониться с клиентом до 8 января. Обновить документацию к 15 числу.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(
            crm_client,
            auth_headers_system,
            note_id,
            mock_llm_redis=mock_llm_redis,
            mock_responses=analyze_mock_responses,
        )

        assert response.status_code == 200
        result = response.json()

        tasks = [
            entity
            for entity in object_list(result.get("entities"))
            if entity.get("entity_type") == "task"
        ]
        assert len(tasks) == 3

        urgent_task = next((task for task in tasks if task.get("priority") == "urgent"), None)
        assert urgent_task is not None
        assert urgent_task.get("due_date") == "2024-01-10"
        assignees_raw = urgent_task.get("assignees")
        assert isinstance(assignees_raw, list)
        assert "ivan" in assignees_raw

    @pytest.mark.asyncio
    async def test_ai_summarize_text(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ):
        """AI суммаризирует длинный текст"""
        _ = unique_id
        long_text = """Сегодня была продуктивная встреча с командой.
        Мы обсудили текущий прогресс по проекту X, который находится на 75% готовности.
        Иван предложил нанять дополнительного разработчика для ускорения работы.
        Петр согласился помочь с backend частью. Анна возьмет на себя тестирование.
        Следующая встреча назначена на следующую неделю.
        Основные договоренности: начать разработку новой фичи, провести код-ревью, подготовить документацию."""

        analyze_mock_responses = [{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "Встреча команды",
                    "description": "Обсудили проект X (75% готовности). Решили нанять разработчика. Петр - backend, Анна - тестирование. Следующая встреча через неделю.",
                    "attributes": {},
                    "confidence": 0.93,
                },
                "entities": [
                    {"entity_type": "task", "name": "Проект X", "description": "Текущий проект с прогрессом и рисками", "attributes": {}, "confidence": 0.9},
                    {"entity_type": "task", "name": "Иван", "description": "Участник встречи, предложил усилить команду", "attributes": {}, "confidence": 0.88},
                    {"entity_type": "task", "name": "Петр", "description": "Отвечает за backend и реализацию сервисов", "attributes": {}, "confidence": 0.9},
                    {"entity_type": "task", "name": "Анна", "description": "Занимается тестированием и качеством релиза", "attributes": {}, "confidence": 0.89}
                ],
                "relationships": [],
                "metadata": _META,
                "attachment_summaries": [],
            })
        }]

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Встреча команды (исходный)",
            "description": long_text,
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(
            crm_client,
            auth_headers_system,
            note_id,
            mock_llm_redis=mock_llm_redis,
            mock_responses=analyze_mock_responses,
        )

        assert response.status_code == 200
        result = response.json()

        note = object_dict(result.get("note"), field="note")
        description = object_str(note.get("description"), field="note.description")
        assert len(description) < len(long_text)
        description_lower = description.lower()
        assert "проект x" in description_lower or "проекта x" in description_lower

    @pytest.mark.asyncio
    async def test_ai_extract_with_mentioned_entities(self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str],
    ):
        """AI учитывает явно упомянутые entities через @"""
        existing_name = f"Существующая задача {unique_id}"
        existing_entity_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "task",
            "name": existing_name,
            "description": "Задача уже в CRM для проверки связи analyze по имени",
            "attributes": {"email": "existing@example.com"}
        }, headers=auth_headers_system)
        existing_id = object_str(
            _http_json(existing_entity_resp).get("entity_id"),
            field="entity_id",
        )

        call_title = "Звонок с клиентом"
        analyze_mock_responses = [{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": call_title,
                    "description": "Обсудили условия сотрудничества",
                    "attributes": {},
                    "confidence": 0.92,
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
                        "confidence": 0.9,
                    }
                ],
                "metadata": _META,
                "attachment_summaries": [],
            })
        }]

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Звонок",
            "description": "Созвонился с клиентом. Обсудили условия.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(
            crm_client,
            auth_headers_system,
            note_id,
            mock_llm_redis=mock_llm_redis,
            mock_responses=analyze_mock_responses,
            mentioned_entity_ids=[existing_id],
        )

        assert response.status_code == 200
        result = response.json()

        relationships = object_list(result.get("relationships"))
        if relationships:
            rel0 = relationships[0]
            assert rel0.get("relationship_type") == "mentions"
            assert rel0.get("target_draft_entity_id")
        else:
            known_map = optional_object_dict(result.get("known_entity_id_map"))
            known_entity_ids = [
                object_str(entity_id, field="known_entity_id")
                for entity_id in known_map.values()
            ]
            assert existing_id in known_entity_ids, f"Expected mentioned entity mapping, got: {result}"

    @pytest.mark.asyncio
    async def test_ai_extract_specific_entity_types(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ):
        """AI извлекает только указанные типы entities"""
        _ = unique_id
        analyze_mock_responses = [{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "Встреча",
                    "description": "Краткий протокол встречи с участниками команды",
                    "attributes": {},
                    "confidence": 0.9,
                },
                "entities": [
                    {"entity_type": "task", "name": "Иван", "description": "Участник встречи, статус задач", "attributes": {}, "confidence": 0.89},
                    {"entity_type": "task", "name": "Петр", "description": "Второй участник, вопросы по срокам", "attributes": {}, "confidence": 0.88}
                ],
                "relationships": [],
                "metadata": _META,
                "attachment_summaries": [],
            })
        }]

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Встреча (типы)",
            "description": "Встретились с Иваном и Петром. Обсудили проект X.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(
            crm_client,
            auth_headers_system,
            note_id,
            mock_llm_redis=mock_llm_redis,
            mock_responses=analyze_mock_responses,
            extract_entity_types=["task"],
        )

        assert response.status_code == 200
        result = response.json()

        entities = object_list(result.get("entities"))
        assert all(entity.get("entity_type") == "task" for entity in entities)

    @pytest.mark.asyncio
    async def test_ai_extract_custom_relationship_types(self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str],
    ):
        """AI извлекает кастомные типы связей"""
        _ = await crm_client.post("/crm/api/v1/relationships/types/", json={
            "type_id": f"works_on_{unique_id}",
            "name": "Работает над",
            "prompt": "Ищи кто над чем работает",
            "is_directed": True
        }, headers=auth_headers_system)

        analyze_mock_responses = [{
            "type": "text",
            "content": json.dumps({
                "note": {
                    "entity_type": "note",
                    "name": "Распределение задач",
                    "description": "Кто над чем работает в текущем спринте команды",
                    "attributes": {},
                    "confidence": 0.91,
                },
                "entities": [
                    {"entity_type": "task", "name": "Иван", "description": "Сотрудник, назначенный на проект A", "attributes": {}, "confidence": 0.9},
                    {"entity_type": "task", "name": "Проект A", "description": "Основной проект спринта с дедлайнами", "attributes": {}, "confidence": 0.92}
                ],
                "relationships": [
                    {
                        "source_type": "task",
                        "source_name": "Иван",
                        "target_type": "task",
                        "target_name": "Проект A",
                        "relationship_type": f"works_on_{unique_id}",
                        "weight": 1.0,
                        "confidence": 0.88,
                    }
                ],
                "metadata": _META,
                "attachment_summaries": [],
            })
        }]

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Распределение",
            "description": "Иван работает над проектом A.",
            "namespace": "default",
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, response = await _analyze_note(
            crm_client, auth_headers_system, note_id,
            mock_llm_redis=mock_llm_redis,
            mock_responses=analyze_mock_responses,
            extract_relationship_types=[f"works_on_{unique_id}"],
        )
        result = response.json()

        relationships = object_list(result.get("relationships"))
        custom_rel = next(
            (
                rel
                for rel in relationships
                if rel.get("relationship_type") == f"works_on_{unique_id}"
            ),
            None,
        )
        assert custom_rel is not None

    @pytest.mark.asyncio
    async def test_entity_creation_rejects_missing_namespace(
        self, crm_client: AsyncClient, auth_headers_system: dict[str, str]
    ):
        """422 при попытке создать entity в несуществующем namespace."""
        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": "Заметка в несуществующем namespace",
            "description": "Текст для анализа",
            "namespace": "missing_namespace_for_ai",
        }, headers=auth_headers_system)
        assert note_resp.status_code == 422

