"""
Тесты корректировки результатов AI анализа.

User Story: Возможность править результаты AI и дополнять данные по entities.
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
    **extra: object,
) -> tuple[dict[str, object], _DraftResponse]:
    """Запускает анализ заметки через POST /tasks/note-analyze и ждёт завершения.

    Возвращает (task_row, ai_analysis_draft).
    """
    body: dict[str, object] = {"note_id": note_id}
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
class TestAICorrection:
    """Корректировка извлеченных AI данных"""

    @pytest.mark.asyncio
    async def test_correct_extracted_entity(self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str],
    ):
        """Пользователь правит entity после AI анализа"""
        await mock_llm_redis(mock_llm_queue_with_analyze_spare([{
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
        }]))

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Встреча {unique_id}",
            "description": "Встретился с Иваном",
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, analyze_resp = await _analyze_note(crm_client, auth_headers_system, note_id)
        entities = object_list(analyze_resp.json().get("entities"))
        extracted_entity = entities[0] if entities else {
            "entity_type": "contact",
            "name": "Иван",
            "attributes": {"role": "менеджер"},
        }
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": extracted_entity.get("entity_type"),
            "name": extracted_entity.get("name"),
            "attributes": extracted_entity.get("attributes", {}),
        }, headers=auth_headers_system)
        entity_id = object_str(_http_json(create_resp).get("entity_id"), field="entity_id")

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
        corrected = _http_json(get_resp)
        corrected_attrs = object_dict(corrected.get("attributes"), field="attributes")
        assert object_str(corrected.get("name"), field="name") == "Иван Иванов"
        assert object_str(corrected_attrs.get("role"), field="role") == "старший менеджер"
        assert "email" in corrected_attrs

    @pytest.mark.asyncio
    async def test_add_missing_relationship(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str],
    ):
        """Добавление связи, которую AI не нашел"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Контакт 1 {unique_id}"
        }, headers=auth_headers_system)
        entity1_id = object_str(_http_json(entity1_resp).get("entity_id"), field="entity_id")

        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "project",
            "name": f"Проект {unique_id}"
        }, headers=auth_headers_system)
        entity2_id = object_str(_http_json(entity2_resp).get("entity_id"), field="entity_id")

        rel_resp = await crm_client.post("/crm/api/v1/relationships/", json={
            "source_entity_id": entity1_id,
            "target_entity_id": entity2_id,
            "relationship_type": "related_to"
        }, headers=auth_headers_system)
        assert rel_resp.status_code == 200, rel_resp.text

        relationship = _http_json(rel_resp)
        assert object_str(relationship.get("source_entity_id"), field="source_entity_id") == entity1_id
        assert object_str(relationship.get("target_entity_id"), field="target_entity_id") == entity2_id

    @pytest.mark.asyncio
    async def test_delete_incorrect_entity(self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str],
    ):
        """Удаление ошибочно извлеченной entity"""
        await mock_llm_redis(mock_llm_queue_with_analyze_spare([{
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
        }]))

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Встреча {unique_id}",
            "description": "Встретился с контактом",
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        # check_duplicates=False: тест ставит ровно 1 LLM-ответ для analyze;
        # включённый dedup потребовал бы доп. ответов и зависит от состояния
        # pgvector (загрязнения от соседних тестов).
        _, analyze_resp = await _analyze_note(
            crm_client, auth_headers_system, note_id, check_duplicates=False
        )
        entities = object_list(analyze_resp.json().get("entities"))

        incorrect_entity_id = None
        for entity_data in entities:
            entity_name = object_str(entity_data.get("name"), field="entity.name")
            create_resp = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": entity_data.get("entity_type"),
                "name": entity_name,
            }, headers=auth_headers_system)
            assert create_resp.status_code == 200
            if "Ошибочный" in entity_name:
                incorrect_entity_id = object_str(
                    _http_json(create_resp).get("entity_id"),
                    field="entity_id",
                )

        if incorrect_entity_id is None:
            raise ValueError("Ошибочный контакт не найден")
        delete_resp = await crm_client.delete(f"/crm/api/v1/entities/{incorrect_entity_id}", headers=auth_headers_system)
        assert delete_resp.status_code == 200

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{incorrect_entity_id}", headers=auth_headers_system)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_merge_duplicate_entities(self, crm_client: AsyncClient, unique_id: str, auth_headers_system: dict[str, str],
    ):
        """Объединение дублирующихся entities"""
        entity1_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Иван {unique_id}",
            "attributes": {"email": "ivan1@example.com"}
        }, headers=auth_headers_system)
        entity1_id = object_str(_http_json(entity1_resp).get("entity_id"), field="entity_id")

        entity2_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "contact",
            "name": f"Иван Иванов {unique_id}",
            "attributes": {"phone": "+79991234567"}
        }, headers=auth_headers_system)
        entity2_id = object_str(_http_json(entity2_resp).get("entity_id"), field="entity_id")

        update_resp = await crm_client.put(f"/crm/api/v1/entities/{entity1_id}", json={
            "attributes": {
                "email": "ivan1@example.com",
                "phone": "+79991234567"
            }
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200

        _ = await crm_client.delete(f"/crm/api/v1/entities/{entity2_id}", headers=auth_headers_system)

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{entity1_id}", headers=auth_headers_system)
        merged = _http_json(get_resp)
        merged_attrs = object_dict(merged.get("attributes"), field="attributes")
        assert "email" in merged_attrs
        assert "phone" in merged_attrs

    @pytest.mark.asyncio
    async def test_update_note_after_ai_analysis(self, crm_client: AsyncClient, mock_llm_redis: MockLlmRedisFactory, unique_id: str, auth_headers_system: dict[str, str],
    ):
        """Корректировка самой заметки после AI анализа"""
        await mock_llm_redis(mock_llm_queue_with_analyze_spare([{
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
        }]))

        note_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Встреча {unique_id}",
            "description": "Встреча прошла",
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(note_resp).get("entity_id"), field="entity_id")

        _, analyze_resp = await _analyze_note(crm_client, auth_headers_system, note_id)
        note_data = object_dict(analyze_resp.json().get("note"), field="note")

        # Создаём note на основе AI анализа
        create_resp = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": note_data.get("entity_type"),
            "entity_subtype": note_data.get("entity_subtype"),
            "name": note_data.get("name"),
            "description": note_data.get("description"),
        }, headers=auth_headers_system)
        note_id = object_str(_http_json(create_resp).get("entity_id"), field="entity_id")

        # Теперь корректируем созданную note
        update_resp = await crm_client.put(f"/crm/api/v1/entities/{note_id}", json={
            "name": "Встреча команды по проекту X",
            "description": "Детальное описание: обсудили прогресс, приняли решения",
            "tags": ["важно", "проект-x"]
        }, headers=auth_headers_system)
        assert update_resp.status_code == 200

        get_resp = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        updated_note = _http_json(get_resp)
        updated_name = object_str(updated_note.get("name"), field="name")
        assert "проекту X" in updated_name
        tags_raw = updated_note.get("tags")
        if not isinstance(tags_raw, list):
            raise AssertionError("tags must be a list")
        tags = [object_str(tag, field="tag") for tag in cast(list[object], tags_raw)]
        assert "важно" in tags

