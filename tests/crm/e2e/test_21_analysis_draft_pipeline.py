"""
E2E: черновик AI analyze на сервере — draft_version, PATCH дельты, POST apply.

Единственный внешний мок — ответ LLM (mock_llm_redis). БД, CRM API, flows worker — реальные.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from apps.crm.container import CRMContainer
from apps.crm.models.api import AIAnalysisDraftStored, AIExtractedEntity
from apps.crm.services.entity_service import ApplyAnalysisDraftEntityFailuresError, EntityService
from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str

MockLlmRedisFactory = Callable[[list[object]], Awaitable[None]]


class _DraftResponse:
    status_code: int
    text: str
    _draft: dict[str, object]

    def __init__(self, status_code: int, draft: dict[str, object]) -> None:
        self.status_code = status_code
        self._draft = draft
        self.text = json.dumps(draft)

    def json(self) -> dict[str, object]:
        return self._draft


class _TaskCompletionResponse:
    status_code: int
    text: str
    _payload: dict[str, object]

    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict[str, object]:
        return self._payload


def _json_object(response_payload: object) -> dict[str, object]:
    return json_object(response_payload)


async def _apply_note(
    crm_client: AsyncClient,
    headers: dict[str, str],
    note_id: str,
) -> _TaskCompletionResponse:
    """Применяет черновик анализа заметки через /tasks/note-analyze с mode=apply."""
    start = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json={"note_id": note_id, "mode": "apply"},
        headers=headers,
    )
    if start.status_code not in (200, 202):
        return _TaskCompletionResponse(start.status_code, _json_object(start.json()))
    start_payload = _json_object(start.json())
    task_id_raw = start_payload.get("task_id")
    assert isinstance(task_id_raw, str)
    task_id = task_id_raw
    deadline = time.monotonic() + 30.0
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        tr = await crm_client.get(f"/crm/api/v1/tasks/{task_id}", headers=headers)
        last = _json_object(tr.json())
        status_raw = last.get("status")
        if status_raw in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.3)
    status_code = 200 if last.get("status") == "completed" else 422
    return _TaskCompletionResponse(status_code, last)


async def _analyze_note(
    crm_client: AsyncClient,
    headers: dict[str, str],
    note_id: str,
    **extra: object,
) -> tuple[dict[str, object], _DraftResponse]:
    """Запускает анализ заметки через POST /tasks/note-analyze и ждёт завершения.

    Возвращает (task_row, ai_analysis_draft).
    """
    body: dict[str, object] = {"note_id": note_id, "check_duplicates": False}
    body.update(extra)
    start = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json=body,
        headers=headers,
    )
    assert start.status_code == 202, start.text
    start_payload = _json_object(start.json())
    task_id_raw = start_payload.get("task_id")
    assert isinstance(task_id_raw, str)
    task_id = task_id_raw
    deadline = time.monotonic() + 60.0
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        tr = await crm_client.get(f"/crm/api/v1/tasks/{task_id}", headers=headers)
        assert tr.status_code == 200, tr.text
        last = _json_object(tr.json())
        status_raw = last.get("status")
        if status_raw in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.4)
    assert last.get("status") == "completed", f"task failed: {last.get('error_message')}"
    nr = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=headers)
    note_payload = _json_object(nr.json())
    attributes_raw = note_payload.get("attributes")
    attributes = object_dict(attributes_raw, field="attributes")
    draft_raw = attributes.get("ai_analysis_draft")
    draft: dict[str, object] = object_dict(draft_raw, field="ai_analysis_draft") if isinstance(draft_raw, dict) else {}

    return last, _DraftResponse(nr.status_code, draft)


_ANALYZE_META: dict[str, object] = {
    "dates_mentioned": [],
    "places_mentioned": [],
    "key_topics": [],
}


def _analyze_body(
    *,
    note: dict[str, object] | None,
    entities: list[dict[str, object]],
    relationships: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "note": note,
        "entities": entities,
        "relationships": relationships,
        "metadata": _ANALYZE_META,
    }


@pytest.mark.real_taskiq
class TestAnalysisDraftPipeline:
    @pytest.mark.asyncio
    async def test_analyze_with_note_id_persists_draft_with_ids(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        note_name = f"Черновик-тест {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": "Текст заметки для проверки сохранения черновика analyze",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_json_object(note_resp.json()).get("entity_id"), field="entity_id")

        ivan = "Иван Иванов"
        petr = "Петр Петров"
        await mock_llm_redis(
            [
                {
                    "type": "text",
                    "content": json.dumps(
                        _analyze_body(
                            note={
                                "entity_type": "note",
                                "name": note_name,
                                "description": "Итог встречи: обсудили проект и команду",
                            },
                            entities=[
                                {
                                    "entity_type": "task",
                                    "name": ivan,
                                    "description": "Менеджер проекта, ответственный за сроки",
                                    "attributes": {"role": "менеджер"},
                                },
                                {
                                    "entity_type": "task",
                                    "name": petr,
                                    "description": "Разработчик backend, подключается к спринту",
                                    "attributes": {"role": "разработчик"},
                                },
                            ],
                            relationships=[
                                {
                                    "source_type": "note",
                                    "source_name": note_name,
                                    "target_type": "task",
                                    "target_name": ivan,
                                    "relationship_type": "mentions",
                                    "weight": 1.0,
                                    "confidence": 0.9,
                                },
                                {
                                    "source_type": "note",
                                    "source_name": note_name,
                                    "target_type": "task",
                                    "target_name": petr,
                                    "relationship_type": "mentions",
                                    "weight": 0.9,
                                    "confidence": 0.85,
                                },
                            ],
                        )
                    ),
                }
            ]
        )

        _, analyze = await _analyze_note(crm_client, auth_headers_system, note_id)
        assert analyze.status_code == 200, analyze.text
        body = analyze.json()
        entities = object_list(body.get("entities"))
        relationships = object_list(body.get("relationships"))
        assert len(entities) == 2
        assert all(object_dict(entity, field="entity").get("draft_entity_id") for entity in entities)
        assert len(relationships) == 2
        for rel in relationships:
            rel_dict = object_dict(rel, field="relationship")
            assert rel_dict.get("draft_relationship_id")
            assert rel_dict.get("source_draft_entity_id")
            assert rel_dict.get("target_draft_entity_id")
            assert "confidence" in rel_dict

        stored = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        assert stored.status_code == 200, stored.text
        stored_payload = _json_object(stored.json())
        attrs = object_dict(stored_payload.get("attributes"), field="attributes")
        draft = object_dict(attrs.get("ai_analysis_draft"), field="ai_analysis_draft")
        assert draft.get("draft_version") == 1
        assert len(object_list(draft.get("entities"))) == 2
        assert len(object_list(draft.get("relationships"))) == 2

    @pytest.mark.asyncio
    async def test_patch_analysis_draft_version_conflict_returns_409(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        note_name = f"Патч-конфликт {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": "Заметка для проверки конфликта версий черновика",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_json_object(note_resp.json()).get("entity_id"), field="entity_id")

        await mock_llm_redis(
            [
                {
                    "type": "text",
                    "content": json.dumps(
                        _analyze_body(
                            note={
                                "entity_type": "note",
                                "name": note_name,
                                "description": "Краткое резюме для теста PATCH конфликта",
                            },
                            entities=[
                                {
                                    "entity_type": "task",
                                    "name": f"Контакт {unique_id}",
                                    "description": "Участник для проверки optimistic locking",
                                    "attributes": {},
                                },
                            ],
                            relationships=[],
                        )
                    ),
                }
            ]
        )

        _, analyze = await _analyze_note(crm_client, auth_headers_system, note_id)
        assert analyze.status_code == 200, analyze.text

        bad = await crm_client.patch(
            f"/crm/api/v1/entities/notes/{note_id}/analysis-draft",
            json={
                "expected_version": 99,
                "remove_entity_draft_ids": [],
                "remove_relationship_draft_ids": [],
                "patch_entities": [],
                "patch_relationships": [],
            },
            headers=auth_headers_system,
        )
        assert bad.status_code == 409, bad.text

    @pytest.mark.asyncio
    async def test_patch_removes_entity_and_bumps_version(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        note_name = f"Патч-удаление {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": "Заметка для проверки удаления строки сущности из черновика",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        note_id = object_str(_json_object(note_resp.json()).get("entity_id"), field="entity_id")

        await mock_llm_redis(
            [
                {
                    "type": "text",
                    "content": json.dumps(
                        _analyze_body(
                            note={
                                "entity_type": "note",
                                "name": note_name,
                                "description": "Резюме перед удалением одной сущности из черновика",
                            },
                            entities=[
                                {
                                    "entity_type": "task",
                                    "name": f"Оставить {unique_id}",
                                    "description": "Эта сущность должна остаться после PATCH",
                                    "attributes": {},
                                },
                                {
                                    "entity_type": "task",
                                    "name": f"Удалить {unique_id}",
                                    "description": "Эту сущность удаляем из черновика запросом PATCH",
                                    "attributes": {},
                                },
                            ],
                            relationships=[],
                        )
                    ),
                }
            ]
        )

        _ = await _analyze_note(crm_client, auth_headers_system, note_id)

        get1 = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        get1_payload = _json_object(get1.json())
        draft1 = object_dict(
            object_dict(get1_payload.get("attributes"), field="attributes").get("ai_analysis_draft"),
            field="ai_analysis_draft",
        )
        assert draft1.get("draft_version") == 1
        draft1_entities = object_list(draft1.get("entities"))
        assert len(draft1_entities) == 2
        remove_id = ""
        for entity in draft1_entities:
            entity_dict = object_dict(entity, field="entity")
            entity_name = object_str(entity_dict.get("name"), field="name")
            if f"Удалить {unique_id}" in entity_name:
                remove_id = object_str(entity_dict.get("draft_entity_id"), field="draft_entity_id")
                break
        assert remove_id

        patched = await crm_client.patch(
            f"/crm/api/v1/entities/notes/{note_id}/analysis-draft",
            json={
                "expected_version": 1,
                "remove_entity_draft_ids": [remove_id],
                "remove_relationship_draft_ids": [],
                "patch_entities": [],
                "patch_relationships": [],
            },
            headers=auth_headers_system,
        )
        assert patched.status_code == 200, patched.text
        out = object_dict(_json_object(patched.json()), field="patched")
        assert out.get("draft_version") == 2
        assert len(object_list(out.get("entities"))) == 1

    @pytest.mark.asyncio
    async def test_apply_creates_entities_relationships_and_clears_draft(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        note_name = f"Apply-тест {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": "Заметка для полного сценария apply черновика analyze",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        note_id = object_str(_json_object(note_resp.json()).get("entity_id"), field="entity_id")

        contact = f"Контакт CRM {unique_id}"
        await mock_llm_redis(
            [
                {
                    "type": "text",
                    "content": json.dumps(
                        _analyze_body(
                            note={
                                "entity_type": "note",
                                "name": note_name,
                                "description": "Встреча зафиксирована для последующего apply в CRM",
                            },
                            entities=[
                                {
                                    "entity_type": "contact",
                                    "name": contact,
                                    "description": "Новый контакт из текста заметки для apply",
                                    "attributes": {"source": "test"},
                                },
                            ],
                            relationships=[
                                {
                                    "source_type": "note",
                                    "source_name": note_name,
                                    "target_type": "contact",
                                    "target_name": contact,
                                    "relationship_type": "mentions",
                                    "weight": 1.0,
                                    "confidence": 0.9,
                                },
                            ],
                        )
                    ),
                }
            ]
        )

        _, an = await _analyze_note(crm_client, auth_headers_system, note_id, check_duplicates=False)
        assert an.status_code == 200, an.text

        apply_resp = await _apply_note(crm_client, auth_headers_system, note_id)
        assert apply_resp.status_code == 200, apply_resp.text
        result = apply_resp.json()
        task_data_raw = result.get("data")
        task_data = task_data_raw if isinstance(task_data_raw, dict) else {}
        assert task_data.get("result_entities_count") == 1
        assert task_data.get("result_relationships_count") == 1

        note_after = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        note_after_payload = _json_object(note_after.json())
        note_after_attrs_raw = note_after_payload.get("attributes")
        note_after_attrs = note_after_attrs_raw if isinstance(note_after_attrs_raw, dict) else {}
        assert "ai_analysis_draft" not in note_after_attrs

        rels_resp = await crm_client.get(
            f"/crm/api/v1/relationships?entity_id={note_id}",
            headers=auth_headers_system,
        )
        assert rels_resp.status_code == 200, rels_resp.text
        rels_payload = _json_object(rels_resp.json())
        rel_items = object_list(rels_payload.get("items"))
        mention_rels = [
            item
            for item in rel_items
            if object_dict(item, field="relationship").get("source_entity_id") == note_id
            and object_dict(item, field="relationship").get("relationship_type") == "mentions"
        ]
        assert mention_rels, f"Expected mentions relationship from note, got: {rel_items}"
        rel_json = object_dict(mention_rels[0], field="mention_rel")
        assert rel_json.get("source_entity_id") == note_id
        assert rel_json.get("relationship_type") == "mentions"

    @pytest.mark.asyncio
    async def test_apply_twice_second_call_fails_without_draft(
        self,
        crm_client: AsyncClient,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        note_name = f"Двойной-apply {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": "Повторный apply без черновика должен вернуть 422",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        note_id = object_str(_json_object(note_resp.json()).get("entity_id"), field="entity_id")

        await mock_llm_redis(
            [
                {
                    "type": "text",
                    "content": json.dumps(
                        _analyze_body(
                            note={
                                "entity_type": "note",
                                "name": note_name,
                                "description": "Краткое содержание для однократного apply",
                            },
                            entities=[
                                {
                                    "entity_type": "task",
                                    "name": f"Задача {unique_id}",
                                    "description": "Одиночная задача в черновике для apply",
                                    "attributes": {},
                                },
                            ],
                            relationships=[],
                        )
                    ),
                }
            ]
        )

        await _analyze_note(crm_client, auth_headers_system, note_id)

        first = await _apply_note(crm_client, auth_headers_system, note_id)
        assert first.status_code == 200, first.text

        second = await _apply_note(crm_client, auth_headers_system, note_id)
        assert second.status_code == 422, second.text


class TestAnalysisDraftApplyPartialFailureCompensation:
    """
    Параллельный apply строк черновика: при постоянной ошибке одной строки
    уже созданные сущности удаляются, черновик на заметке сохраняется.

    Вызов EntityService.apply_analysis_draft в процессе теста (не HTTP/TaskIQ),
    иначе monkeypatch на EntityService не попал бы в crm_worker.
    """

    @pytest.mark.timeout(20)
    @pytest.mark.asyncio
    async def test_compensation_deletes_partial_creates_on_row_failure(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
        crm_container: CRMContainer,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        note_name = f"Компенсация-apply {unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={
                "entity_type": "note",
                "name": note_name,
                "description": "Заметка с черновиком для сценария частичного сбоя apply",
                "namespace": "default",
            },
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = object_str(_json_object(note_resp.json()).get("entity_id"), field="entity_id")

        ok_name = f"OK_ROW_TASK_{unique_id}"
        fail_name = f"FAIL_ROW_CONTACT_{unique_id}"
        stored = AIAnalysisDraftStored(
            draft_version=1,
            updated_at=datetime.now(timezone.utc).isoformat(),
            note=None,
            entities=[
                AIExtractedEntity(
                    draft_entity_id=f"draft-ok-{unique_id}",
                    entity_type="task",
                    name=ok_name,
                    description="Описание задачи достаточной длины для apply черновика",
                    dedup_action="create",
                ),
                AIExtractedEntity(
                    draft_entity_id=f"draft-fail-{unique_id}",
                    entity_type="contact",
                    name=fail_name,
                    description="Описание контакта достаточной длины для apply черновика",
                    dedup_action="create",
                ),
            ],
            relationships=[],
        )

        entity_service = crm_container.entity_service
        note_row = await entity_service.get_entity(note_id)
        if not note_row:
            raise AssertionError(f"note {note_id} not found")
        attrs = dict(note_row.attributes or {})
        attrs["ai_analysis_draft"] = stored.model_dump(mode="json")
        await entity_service.update_entity(note_id, {"attributes": attrs})

        orig = EntityService._persist_analysis_draft_entity_row

        async def _patched(
            self,
            ent: AIExtractedEntity,
            namespace: str,
            merge_target_locks: dict[str, asyncio.Lock],
            source_entity_id: str | None = None,
        ):
            if ent.name == fail_name:
                raise ValueError("simulated_row_persist_failure")
            return await orig(self, ent, namespace, merge_target_locks, source_entity_id)

        monkeypatch.setattr(EntityService, "_persist_analysis_draft_entity_row", _patched)

        with pytest.raises(ApplyAnalysisDraftEntityFailuresError) as exc_info:
            await entity_service.apply_analysis_draft(note_id)

        failed = {f[0]: f for f in exc_info.value.failures}
        assert f"draft-fail-{unique_id}" in failed

        note_after = await entity_service.get_entity(note_id)
        if not note_after:
            raise AssertionError(f"note {note_id} missing after apply failure")
        draft_raw = (note_after.attributes or {}).get("ai_analysis_draft")
        draft_after = object_dict(draft_raw, field="ai_analysis_draft")
        assert draft_after.get("draft_version") == 1

        ok_task_filter = {"field": "name", "op": "$eq", "value": ok_name}
        ok_task_filter_types = await entity_service.resolve_filter_field_types(
            namespace="default",
            entity_type="task",
            entity_subtype=None,
            filters=ok_task_filter,
        )
        ok_tasks, _, _ = await entity_service.list_entities(
            entity_type="task",
            namespace="default",
            filters=ok_task_filter,
            filter_field_types=ok_task_filter_types,
            limit=20,
        )
        assert ok_tasks == []

        fail_contact_filter = {"field": "name", "op": "$eq", "value": fail_name}
        fail_contact_filter_types = await entity_service.resolve_filter_field_types(
            namespace="default",
            entity_type="contact",
            entity_subtype=None,
            filters=fail_contact_filter,
        )
        fail_contacts, _, _ = await entity_service.list_entities(
            entity_type="contact",
            namespace="default",
            filters=fail_contact_filter,
            filter_field_types=fail_contact_filter_types,
            limit=20,
        )
        assert fail_contacts == []
