"""
E2E: черновик AI analyze на сервере — draft_version, PATCH дельты, POST apply.

Единственный внешний мок — ответ LLM (mock_llm_redis). БД, CRM API, flows worker — реальные.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from apps.crm.models.api import AIAnalysisDraftStored, AIExtractedEntity
from apps.crm.services.entity_service import ApplyAnalysisDraftEntityFailuresError, EntityService


async def _apply_note(crm_client, headers: dict, note_id: str):
    """Применяет черновик анализа заметки через /tasks/note-analyze с mode=apply."""
    import asyncio
    import time
    start = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json={"note_id": note_id, "mode": "apply"},
        headers=headers,
    )
    if start.status_code not in (200, 202):
        return start  # propagate error for assertions
    task_id = start.json()["task_id"]
    deadline = time.monotonic() + 30.0
    last = {}
    while time.monotonic() < deadline:
        tr = await crm_client.get(f"/crm/api/v1/tasks/{task_id}", headers=headers)
        last = tr.json()
        if last.get("status") in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.3)
    return type("FakeResp", (), {"status_code": 200 if last.get("status") == "completed" else 422, "json": lambda self: last, "text": str(last)})()


async def _analyze_note(
    crm_client,
    headers: dict,
    note_id: str,
    **extra,
):
    """Запускает анализ заметки через POST /tasks/note-analyze и ждёт завершения.

    Возвращает (task_row, ai_analysis_draft).
    """
    import asyncio
    import time
    body = {"note_id": note_id, "check_duplicates": False, **extra}
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

    class _R:
        status_code = nr.status_code
        def json(self) -> dict:
            return draft

    return last, _R()



_ANALYZE_META = {"dates_mentioned": [], "places_mentioned": [], "key_topics": []}


def _analyze_body(*, note: dict | None, entities: list, relationships: list) -> dict:
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
        crm_client,
        mock_llm_redis,
        unique_id: str,
        auth_headers_system: dict,
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
        note_id = note_resp.json()["entity_id"]

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
        assert len(body["entities"]) == 2
        assert all(e.get("draft_entity_id") for e in body["entities"])
        assert len(body["relationships"]) == 2
        for rel in body["relationships"]:
            assert rel.get("draft_relationship_id")
            assert rel.get("source_draft_entity_id")
            assert rel.get("target_draft_entity_id")
            assert "confidence" in rel

        stored = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        assert stored.status_code == 200, stored.text
        attrs = stored.json()["attributes"]
        draft = attrs["ai_analysis_draft"]
        assert draft["draft_version"] == 1
        assert len(draft["entities"]) == 2
        assert len(draft["relationships"]) == 2

    @pytest.mark.asyncio
    async def test_patch_analysis_draft_version_conflict_returns_409(
        self,
        crm_client,
        mock_llm_redis,
        unique_id: str,
        auth_headers_system: dict,
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
        note_id = note_resp.json()["entity_id"]

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
        crm_client,
        mock_llm_redis,
        unique_id: str,
        auth_headers_system: dict,
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
        note_id = note_resp.json()["entity_id"]

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

        await _analyze_note(crm_client, auth_headers_system, note_id)

        get1 = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        draft1 = get1.json()["attributes"]["ai_analysis_draft"]
        assert draft1["draft_version"] == 1
        assert len(draft1["entities"]) == 2
        remove_id = next(e["draft_entity_id"] for e in draft1["entities"] if f"Удалить {unique_id}" in e["name"])

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
        out = patched.json()
        assert out["draft_version"] == 2
        assert len(out["entities"]) == 1

    @pytest.mark.asyncio
    async def test_apply_creates_entities_relationships_and_clears_draft(
        self,
        crm_client,
        mock_llm_redis,
        unique_id: str,
        auth_headers_system: dict,
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
        note_id = note_resp.json()["entity_id"]

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
        task_data = result.get("data") or {}
        assert task_data.get("result_entities_count") == 1
        assert task_data.get("result_relationships_count") == 1

        note_after = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        assert "ai_analysis_draft" not in (note_after.json().get("attributes") or {})

        rels_resp = await crm_client.get(
            f"/crm/api/v1/relationships?entity_id={note_id}",
            headers=auth_headers_system,
        )
        assert rels_resp.status_code == 200, rels_resp.text
        rel_items = rels_resp.json().get("items") or []
        mention_rels = [
            item for item in rel_items
            if item.get("source_entity_id") == note_id and item.get("relationship_type") == "mentions"
        ]
        assert mention_rels, f"Expected mentions relationship from note, got: {rel_items}"
        rel_json = mention_rels[0]
        assert rel_json["source_entity_id"] == note_id
        assert rel_json["relationship_type"] == "mentions"

    @pytest.mark.asyncio
    async def test_apply_twice_second_call_fails_without_draft(
        self,
        crm_client,
        mock_llm_redis,
        unique_id: str,
        auth_headers_system: dict,
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
        note_id = note_resp.json()["entity_id"]

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
        crm_client,
        unique_id: str,
        auth_headers_system: dict,
        crm_container,
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
        note_id = note_resp.json()["entity_id"]

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
            merge_target_locks: dict,
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
        assert isinstance(draft_raw, dict)
        assert draft_raw.get("draft_version") == 1

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
