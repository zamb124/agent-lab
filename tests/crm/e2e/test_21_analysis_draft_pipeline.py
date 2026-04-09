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
                                },
                                {
                                    "source_type": "note",
                                    "source_name": note_name,
                                    "target_type": "task",
                                    "target_name": petr,
                                    "relationship_type": "mentions",
                                    "weight": 0.9,
                                },
                            ],
                        )
                    ),
                }
            ]
        )

        analyze = await crm_client.post(
            f"/crm/api/v1/entities/notes/{note_id}/analyze",
            json={},
            headers=auth_headers_system,
        )
        assert analyze.status_code == 200, analyze.text
        body = analyze.json()
        assert len(body["entities"]) == 2
        assert all(e.get("draft_entity_id") for e in body["entities"])
        assert len(body["relationships"]) == 2
        for rel in body["relationships"]:
            assert rel.get("draft_relationship_id")
            assert rel.get("source_draft_entity_id")
            assert rel.get("target_draft_entity_id")

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

        analyze = await crm_client.post(
            f"/crm/api/v1/entities/notes/{note_id}/analyze",
            json={},
            headers=auth_headers_system,
        )
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

        await crm_client.post(
            f"/crm/api/v1/entities/notes/{note_id}/analyze",
            json={},
            headers=auth_headers_system,
        )

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
                                },
                            ],
                        )
                    ),
                }
            ]
        )

        an = await crm_client.post(
            f"/crm/api/v1/entities/notes/{note_id}/analyze",
            json={"check_duplicates": False},
            headers=auth_headers_system,
        )
        assert an.status_code == 200, an.text

        apply_resp = await crm_client.post(
            f"/crm/api/v1/entities/notes/{note_id}/apply",
            headers=auth_headers_system,
        )
        assert apply_resp.status_code == 200, apply_resp.text
        result = apply_resp.json()
        assert len(result["created_entity_ids"]) == 1
        assert len(result["created_relationship_ids"]) == 1

        note_after = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=auth_headers_system)
        assert "ai_analysis_draft" not in (note_after.json().get("attributes") or {})

        rel_id = result["created_relationship_ids"][0]
        rel = await crm_client.get(f"/crm/api/v1/relationships/{rel_id}", headers=auth_headers_system)
        assert rel.status_code == 200, rel.text
        rel_json = rel.json()
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

        await crm_client.post(
            f"/crm/api/v1/entities/notes/{note_id}/analyze",
            json={},
            headers=auth_headers_system,
        )

        first = await crm_client.post(
            f"/crm/api/v1/entities/notes/{note_id}/apply",
            headers=auth_headers_system,
        )
        assert first.status_code == 200, first.text

        second = await crm_client.post(
            f"/crm/api/v1/entities/notes/{note_id}/apply",
            headers=auth_headers_system,
        )
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
        ):
            if ent.name == fail_name:
                raise ValueError("simulated_row_persist_failure")
            return await orig(self, ent, namespace, merge_target_locks)

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

        ok_tasks, _, _ = await entity_service.list_entities(
            entity_type="task",
            namespace="default",
            filters={"name": ok_name},
            limit=20,
        )
        assert ok_tasks == []

        fail_contacts, _, _ = await entity_service.list_entities(
            entity_type="contact",
            namespace="default",
            filters={"name": fail_name},
            limit=20,
        )
        assert fail_contacts == []
