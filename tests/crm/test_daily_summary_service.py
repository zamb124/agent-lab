from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import apps.crm.services.entity_service as entity_service_module
from apps.crm.services.entity_service import EntityService
from core.context import Context, set_context
from core.models.identity_models import Company, User

pytestmark = pytest.mark.no_crm_http


def _set_test_context() -> None:
    set_context(
        Context(
            user=User(user_id="u-1", name="Tester"),
            active_company=Company(company_id="c-1", name="Company"),
            channel="test",
        )
    )


def _analyzed_note() -> SimpleNamespace:
    return SimpleNamespace(
        entity_id="n-1",
        updated_at=None,
        name="n1",
        entity_subtype=None,
        description="d",
        tags=[],
        attributes={"ai_analysis_applied_at": "2026-01-01T00:00:00+00:00"},
    )


def _build_service() -> EntityService:
    entity_repo = AsyncMock()
    entity_repo.list_by_entity_ids_ordered = AsyncMock(return_value=[])
    entity_type_repo = AsyncMock()
    entity_type_repo.get_by_type_id = AsyncMock(
        return_value=SimpleNamespace(
            namespace="default",
            required_fields={},
            optional_fields={},
        )
    )
    namespace_repo = AsyncMock()
    namespace_repo.get = AsyncMock(return_value=SimpleNamespace(name="default"))
    artifact_service = AsyncMock()
    artifact_service.put_daily_payload = AsyncMock()
    artifact_service.get_daily_payload = AsyncMock(return_value=None)
    artifact_service.put_period_payload = AsyncMock()
    artifact_service.get_period_payload = AsyncMock(return_value=None)
    relationship_repo = AsyncMock()
    relationship_repo.get_neighbors = AsyncMock(return_value={})
    return EntityService(
        entity_repo=entity_repo,
        entity_type_repo=entity_type_repo,
        relationship_type_repo=AsyncMock(),
        relationship_repo=relationship_repo,
        namespace_repo=namespace_repo,
        attachment_service=AsyncMock(),
        a2a_client=AsyncMock(),
        daily_summary_cache_service=AsyncMock(),
        daily_summary_artifact_service=artifact_service,
        user_person_service=AsyncMock(),
        access_grant_repo=AsyncMock(),
        access_request_repo=AsyncMock(),
        company_mapping_repo=AsyncMock(),
        company_repo=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_enqueue_daily_summary_rebuild_deduplicates(monkeypatch):
    _set_test_context()
    service = _build_service()
    service._collect_notes_and_source_version = AsyncMock(
        return_value=([_analyzed_note()], {"notes_count": 1, "max_updated_at": None})
    )
    service._daily_summary_cache_service.set_revalidating = AsyncMock(side_effect=[True, False])

    import apps.crm_worker.tasks.daily_summary_tasks as summary_tasks_module

    kiq_mock = AsyncMock()
    monkeypatch.setattr(
        summary_tasks_module,
        "rebuild_daily_summary_task",
        SimpleNamespace(kiq=kiq_mock),
    )

    first = await service.enqueue_daily_summary_rebuild(date_str="2026-03-28", namespace=None)
    second = await service.enqueue_daily_summary_rebuild(date_str="2026-03-28", namespace=None)

    assert first is True
    assert second is False
    assert kiq_mock.await_count == 1


@pytest.mark.asyncio
async def test_rebuild_daily_summary_returns_stale_if_lock_busy():
    _set_test_context()
    service = _build_service()
    service._daily_summary_cache_service.acquire_rebuild_lock = AsyncMock(return_value=False)
    service._daily_summary_cache_service.get_state = AsyncMock(
        return_value={
            "date": "2026-03-28",
            "summary": "cached",
            "source_version": {"notes_count": 1, "max_updated_at": "2026-03-28T10:00:00+00:00"},
            "revalidating": False,
        }
    )

    payload = await service.rebuild_daily_summary(date_str="2026-03-28", namespace=None)

    assert payload["revalidating"] is True
    assert payload["stale"] is True
    assert payload["summary"] == "cached"


@pytest.mark.asyncio
async def test_get_daily_summary_cached_miss_enqueues_rebuild():
    _set_test_context()
    service = _build_service()
    service._collect_notes_and_source_version = AsyncMock(
        return_value=(
            [_analyzed_note()],
            {"notes_count": 1, "max_updated_at": "2026-03-28T11:00:00+00:00"},
        )
    )
    service._daily_summary_cache_service.get_state = AsyncMock(return_value=None)
    service._daily_summary_cache_service.is_revalidating = AsyncMock(return_value=False)
    service.enqueue_daily_summary_rebuild = AsyncMock(return_value=True)

    payload = await service.get_daily_summary_cached(date_str="2026-03-28", namespace=None)

    assert payload["revalidating"] is True
    assert payload["stale"] is True
    service.enqueue_daily_summary_rebuild.assert_awaited_once_with(
        date_str="2026-03-28",
        namespace=None,
    )


@pytest.mark.asyncio
async def test_get_daily_summary_cached_empty_day_no_enqueue(monkeypatch):
    _set_test_context()
    service = _build_service()
    service._collect_notes_and_source_version = AsyncMock(
        return_value=([], {"notes_count": 0, "max_updated_at": None})
    )
    service._daily_summary_cache_service.get_state = AsyncMock(return_value=None)
    service._daily_summary_cache_service.clear_revalidating = AsyncMock()
    service.enqueue_daily_summary_rebuild = AsyncMock(return_value=True)

    # Материализация пустого дня публикует UI-событие через
    # broadcast_crm_daily_summary_updated -> resolve_user_ids_for_namespace_broadcast,
    # которому нужен живой Company. В юнит-тесте сам факт публикации не
    # проверяем — изолируем broadcast через AsyncMock.
    broadcast_mock = AsyncMock()
    monkeypatch.setattr(
        entity_service_module, "broadcast_crm_daily_summary_updated", broadcast_mock
    )

    payload = await service.get_daily_summary_cached(date_str="2026-03-28", namespace=None)

    assert payload["revalidating"] is False
    assert payload["stale"] is False
    assert "2026-03-28" in payload["summary"]
    service.enqueue_daily_summary_rebuild.assert_not_awaited()
    service._daily_summary_artifact_service.put_daily_payload.assert_awaited()
    broadcast_mock.assert_awaited()


@pytest.mark.asyncio
async def test_get_daily_summary_cached_marks_stale_and_requeues():
    _set_test_context()
    service = _build_service()
    service._collect_notes_and_source_version = AsyncMock(
        return_value=(
            [_analyzed_note()],
            {"notes_count": 3, "max_updated_at": "2026-03-28T11:00:00+00:00"},
        )
    )
    service._daily_summary_cache_service.get_state = AsyncMock(
        return_value={
            "date": "2026-03-28",
            "summary": "old",
            "source_version": {"notes_count": 2, "max_updated_at": "2026-03-28T10:00:00+00:00"},
            "revalidating": False,
            "generated_at": "2026-03-28T10:01:00+00:00",
        }
    )
    service._daily_summary_cache_service.is_revalidating = AsyncMock(return_value=False)
    service.enqueue_daily_summary_rebuild = AsyncMock(return_value=True)

    payload = await service.get_daily_summary_cached(date_str="2026-03-28", namespace=None)

    assert payload["stale"] is True
    assert payload["revalidating"] is True
    service.enqueue_daily_summary_rebuild.assert_awaited_once_with(
        date_str="2026-03-28",
        namespace=None,
    )


@pytest.mark.asyncio
async def test_get_daily_summary_cached_hydrates_from_s3_when_redis_miss():
    _set_test_context()
    service = _build_service()
    ver = {"notes_count": 1, "max_updated_at": "2026-03-28T11:00:00+00:00"}
    service._collect_notes_and_source_version = AsyncMock(return_value=([_analyzed_note()], ver))
    service._daily_summary_cache_service.get_state = AsyncMock(return_value=None)
    service._daily_summary_artifact_service.get_daily_payload = AsyncMock(
        return_value={
            "date": "2026-03-28",
            "summary": "from s3",
            "entities": ["Acme"],
            "entity_links": [],
            "source_version": ver,
            "generated_at": "2026-03-28T12:00:00+00:00",
        }
    )
    service._daily_summary_cache_service.is_revalidating = AsyncMock(return_value=False)
    service.enqueue_daily_summary_rebuild = AsyncMock(return_value=True)

    payload = await service.get_daily_summary_cached(date_str="2026-03-28", namespace=None)

    assert payload["summary"] == "from s3"
    assert payload["entities"] == ["Acme"]
    assert payload["entity_links"] == []
    assert payload["revalidating"] is False
    service.enqueue_daily_summary_rebuild.assert_not_awaited()
    service._daily_summary_cache_service.set_state.assert_awaited()


@pytest.mark.asyncio
async def test_get_period_summary_cached_long_period_clamps_to_max_days(monkeypatch):
    _set_test_context()
    service = _build_service()

    def _tiny_period_settings():
        return SimpleNamespace(period_summary_max_days=1)

    monkeypatch.setattr(entity_service_module, "get_crm_settings", _tiny_period_settings)
    service._collect_period_days_bundle = AsyncMock(
        return_value={"days": [{"date": "2026-03-29", "source_version": {"notes_count": 0}}]}
    )
    service._daily_summary_cache_service.get_period_state = AsyncMock(return_value=None)
    service._daily_summary_cache_service.is_period_revalidating = AsyncMock(return_value=False)
    service.enqueue_period_summary_rebuild = AsyncMock(return_value=True)

    payload = await service.get_period_summary_cached(
        date_from="2026-03-28",
        date_to="2026-03-29",
        namespace=None,
    )

    assert payload["date_from"] == "2026-03-29"
    assert payload["date_to"] == "2026-03-29"
    assert payload["period_truncated"] is True
    assert payload["requested_date_from"] == "2026-03-28"
    assert payload["requested_date_to"] == "2026-03-29"
    assert payload["requested_period_days"] == 2
    service.enqueue_period_summary_rebuild.assert_awaited_once_with(
        date_from="2026-03-29",
        date_to="2026-03-29",
        namespace=None,
    )


@pytest.mark.asyncio
async def test_get_period_summary_cached_miss_enqueues_period_rebuild():
    _set_test_context()
    service = _build_service()
    service._collect_notes_and_source_version = AsyncMock(
        return_value=([], {"notes_count": 0, "max_updated_at": None})
    )
    service._daily_summary_cache_service.get_period_state = AsyncMock(return_value=None)
    service._daily_summary_cache_service.is_period_revalidating = AsyncMock(return_value=False)
    service.enqueue_period_summary_rebuild = AsyncMock(return_value=True)

    payload = await service.get_period_summary_cached(
        date_from="2026-03-28",
        date_to="2026-03-29",
        namespace=None,
    )

    assert payload["revalidating"] is True
    assert payload["stale"] is True
    service.enqueue_period_summary_rebuild.assert_awaited_once_with(
        date_from="2026-03-28",
        date_to="2026-03-29",
        namespace=None,
    )


@pytest.mark.asyncio
async def test_compute_period_summary_calls_merge_skill_for_range():
    _set_test_context()
    service = _build_service()
    service._collect_notes_and_source_version = AsyncMock(
        return_value=([], {"notes_count": 0, "max_updated_at": None})
    )
    service._call_period_summarize_merge_skill = AsyncMock(
        return_value={"summary": "Итог периода", "entities": ["Org"]}
    )

    payload = await service.compute_period_summary(
        date_from="2026-03-28",
        date_to="2026-03-29",
        namespace=None,
    )

    assert payload["summary"] == "Итог периода"
    assert payload["entities"] == ["Org"]
    assert payload["date_from"] == "2026-03-28"
    assert payload["date_to"] == "2026-03-29"
    service._call_period_summarize_merge_skill.assert_awaited_once()
    call_kw = service._call_period_summarize_merge_skill.call_args[0][0]
    assert len(call_kw) == 2
    assert {p["date"] for p in call_kw} == {"2026-03-28", "2026-03-29"}


@pytest.mark.asyncio
async def test_get_daily_summary_cached_force_rebuild_on_fresh_cache():
    _set_test_context()
    service = _build_service()
    service._collect_notes_and_source_version = AsyncMock(
        return_value=(
            [_analyzed_note()],
            {"notes_count": 2, "max_updated_at": "2026-03-28T11:00:00+00:00"},
        )
    )
    service._daily_summary_cache_service.get_state = AsyncMock(
        return_value={
            "date": "2026-03-28",
            "summary": "fresh summary",
            "source_version": {"notes_count": 2, "max_updated_at": "2026-03-28T11:00:00+00:00"},
            "revalidating": False,
            "generated_at": "2026-03-28T11:01:00+00:00",
        }
    )
    service._daily_summary_cache_service.is_revalidating = AsyncMock(return_value=False)
    service.enqueue_daily_summary_rebuild = AsyncMock(return_value=True)

    payload = await service.get_daily_summary_cached(
        date_str="2026-03-28",
        namespace=None,
        force_rebuild=True,
    )

    assert payload["revalidating"] is True
    assert payload["stale"] is True
    service.enqueue_daily_summary_rebuild.assert_awaited_once_with(
        date_str="2026-03-28",
        namespace=None,
    )


@pytest.mark.asyncio
async def test_compute_daily_summary_uses_structured_data_summary():
    _set_test_context()
    service = _build_service()
    note = SimpleNamespace(
        entity_id="n-1",
        updated_at=None,
        name="n1",
        entity_subtype=None,
        description="d",
        tags=[],
        attributes={"ai_analysis_applied_at": "2026-01-01T00:00:00+00:00"},
    )
    service._collect_notes_and_source_version = AsyncMock(
        return_value=([note], {"notes_count": 1, "max_updated_at": None})
    )
    service._entity_to_dict = lambda _: {"name": "n1"}
    service._a2a_client.send_task = AsyncMock(
        return_value={
            "response": "",
            "raw": {
                "result": {
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "kind": "data",
                                    "data": {
                                        "summary": "Structured summary from artifact",
                                        "entities": ["Yandex", "Sber"],
                                    },
                                }
                            ]
                        }
                    ]
                }
            },
        }
    )

    payload = await service.compute_daily_summary(date_str="2026-03-28", namespace=None)

    assert payload["summary"] == "Structured summary from artifact"
    assert payload["entities"] == ["Yandex", "Sber"]


@pytest.mark.asyncio
async def test_compute_daily_summary_adds_inline_entity_links_from_note_graph():
    _set_test_context()
    service = _build_service()
    entity_id = "11111111-1111-1111-1111-111111111111"
    note = SimpleNamespace(
        entity_id="n-1",
        updated_at=None,
        name="n1",
        entity_subtype=None,
        description="Обсудили Yandex",
        tags=[],
        attributes={"ai_analysis_applied_at": "2026-01-01T00:00:00+00:00"},
    )
    service._collect_notes_and_source_version = AsyncMock(
        return_value=([note], {"notes_count": 1, "max_updated_at": None})
    )
    service._relationship_repo.get_neighbors = AsyncMock(
        return_value={
            "n-1": [
                SimpleNamespace(
                    source_entity_id="n-1",
                    target_entity_id=entity_id,
                    relationship_type="mentions",
                )
            ]
        }
    )
    service._entity_repo.list_by_entity_ids_ordered = AsyncMock(
        return_value=[
            SimpleNamespace(
                entity_id=entity_id,
                name="Yandex",
                entity_type="company",
                entity_subtype=None,
                namespace="sales",
                attributes={},
            )
        ]
    )
    service._a2a_client.send_task = AsyncMock(
        return_value={
            "response": "",
            "raw": {
                "result": {
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "kind": "data",
                                    "data": {
                                        "summary": "Договорились с Yandex о следующей встрече",
                                        "entities": ["Yandex"],
                                    },
                                }
                            ]
                        }
                    ]
                }
            },
        }
    )

    payload = await service.compute_daily_summary(date_str="2026-03-28", namespace="sales")

    assert payload["summary"] == (
        "Договорились с "
        f"[@Yandex](entity:{entity_id})"
        " о следующей встрече"
    )
    assert payload["entity_links"] == [
        {
            "entity_id": entity_id,
            "name": "Yandex",
            "entity_type": "company",
            "namespace": "sales",
        }
    ]


@pytest.mark.asyncio
async def test_compute_daily_summary_uses_nested_structured_output_summary():
    _set_test_context()
    service = _build_service()
    note = SimpleNamespace(
        entity_id="n-1",
        updated_at=None,
        name="n1",
        entity_subtype=None,
        description="d",
        tags=[],
        attributes={"ai_analysis_applied_at": "2026-01-01T00:00:00+00:00"},
    )
    service._collect_notes_and_source_version = AsyncMock(
        return_value=([note], {"notes_count": 1, "max_updated_at": None})
    )
    service._entity_to_dict = lambda _: {"name": "n1"}
    service._a2a_client.send_task = AsyncMock(
        return_value={
            "response": "",
            "raw": {
                "result": {
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "kind": "data",
                                    "data": {
                                        "structured_output": {
                                            "summary": "Nested structured summary",
                                            "entities": ["Ozon"],
                                            "highlights": [],
                                        }
                                    },
                                }
                            ]
                        }
                    ]
                }
            },
        }
    )

    payload = await service.compute_daily_summary(date_str="2026-03-28", namespace=None)

    assert payload["summary"] == "Nested structured summary"
    assert payload["entities"] == ["Ozon"]


@pytest.mark.asyncio
async def test_compute_daily_summary_falls_back_to_entities_from_notes():
    _set_test_context()
    service = _build_service()
    note = SimpleNamespace(
        entity_id="n-1",
        updated_at=None,
        entity_subtype=None,
        tags=["Альфа Банк"],
        name="Встреча с @Yandex",
        description="Обсудили планы с @Sber и @Yandex",
        attributes={"ai_analysis_applied_at": "2026-01-01T00:00:00+00:00"},
    )
    service._collect_notes_and_source_version = AsyncMock(
        return_value=([note], {"notes_count": 1, "max_updated_at": None})
    )
    service._entity_to_dict = lambda _: {"name": "n1"}
    service._a2a_client.send_task = AsyncMock(
        return_value={
            "response": '{"summary":"Итог дня без списка сущностей"}',
            "raw": {
                "result": {
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "kind": "data",
                                    "data": {"summary": "Итог дня без списка сущностей"},
                                }
                            ]
                        }
                    ]
                }
            },
        }
    )

    payload = await service.compute_daily_summary(date_str="2026-03-28", namespace=None)

    assert payload["summary"] == "Итог дня без списка сущностей"
    assert payload["entities"] == ["Альфа Банк", "Yandex", "Sber"]


@pytest.mark.asyncio
async def test_compute_daily_summary_fallback_from_highlights_when_summary_empty():
    _set_test_context()
    service = _build_service()
    note = SimpleNamespace(
        entity_id="n-1",
        updated_at=None,
        name="n1",
        entity_subtype=None,
        description="d",
        tags=[],
        attributes={"ai_analysis_applied_at": "2026-01-01T00:00:00+00:00"},
    )
    service._collect_notes_and_source_version = AsyncMock(
        return_value=([note], {"notes_count": 1, "max_updated_at": None})
    )
    service._entity_to_dict = lambda _: {"name": "n1"}

    body = {
        "summary": "",
        "entities": [],
        "key_events": ["Событие дня"],
        "highlights": ["Главное"],
        "statistics": {"entities_created": 0, "notes_added": 0, "tasks_completed": 0},
    }
    service._a2a_client.send_task = AsyncMock(
        return_value={
            "response": "",
            "raw": {
                "result": {
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "kind": "data",
                                    "data": {"res": json.dumps(body, ensure_ascii=False)},
                                }
                            ]
                        }
                    ]
                }
            },
        }
    )

    payload = await service.compute_daily_summary(date_str="2026-03-28", namespace=None)

    assert payload["summary"] == "Главное\nСобытие дня"


def test_extract_data_from_a2a_response_res_as_dict_not_string():
    _set_test_context()
    service = _build_service()
    out = service._extract_data_from_a2a_response(
        {
            "response": "",
            "raw": {
                "result": {
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "kind": "data",
                                    "data": {
                                        "res": {"summary": "OK", "entities": []},
                                    },
                                }
                            ]
                        }
                    ]
                }
            },
        }
    )
    assert out.get("summary") == "OK"


@pytest.mark.asyncio
async def test_update_entity_note_date_triggers_both_dates(monkeypatch):
    _set_test_context()
    monkeypatch.setattr(entity_service_module, "broadcast_crm_note_event", AsyncMock())
    service = _build_service()
    existing = SimpleNamespace(
        entity_id="e-1",
        entity_type="note",
        entity_subtype=None,
        company_id="c-1",
        user_id="u-1",
        note_date=date.fromisoformat("2026-03-27"),
        namespace="sales",
        updated_at=None,
        description="old",
        attributes={},
        attachment_ids=[],
    )
    service._entity_repo.get = AsyncMock(return_value=existing)
    service._entity_repo.update = AsyncMock()
    service.enqueue_daily_summary_rebuild = AsyncMock(return_value=True)
    service._relationship_repo.get_outgoing = AsyncMock(return_value=[])
    service._relationship_repo.delete_outgoing_by_source_and_types = AsyncMock()
    service._relationship_repo.create = AsyncMock()

    await service.update_entity(
        entity_id="e-1",
        updates={"note_date": date.fromisoformat("2026-03-28"), "namespace": "support"},
    )

    assert service.enqueue_daily_summary_rebuild.await_count == 2
    service.enqueue_daily_summary_rebuild.assert_any_await(
        date_str="2026-03-27",
        namespace="sales",
    )
    service.enqueue_daily_summary_rebuild.assert_any_await(
        date_str="2026-03-28",
        namespace="support",
    )


@pytest.mark.asyncio
async def test_delete_entity_note_triggers_rebuild(monkeypatch):
    _set_test_context()
    monkeypatch.setattr(entity_service_module, "broadcast_crm_note_event", AsyncMock())
    service = _build_service()
    entity = SimpleNamespace(
        entity_id="e-1",
        entity_type="note",
        company_id="c-1",
        note_date=date.fromisoformat("2026-03-28"),
        namespace="sales",
        attachment_ids=[],
    )
    service._entity_repo.get = AsyncMock(return_value=entity)
    service._relationship_repo.get_by_entity = AsyncMock(return_value=[])
    service._relationship_repo.delete_by_entity = AsyncMock()
    service._attachment_service.delete_all_attachments = AsyncMock(return_value=0)
    service._entity_repo.delete = AsyncMock()
    service.enqueue_daily_summary_rebuild = AsyncMock(return_value=True)

    class DummySaga:
        def __init__(self):
            self._steps = []

        def add_step(self, step):
            self._steps.append(step)

        async def execute(self):
            for step in self._steps:
                await step.execute_fn()

    monkeypatch.setattr(entity_service_module, "EntityDeletionSaga", DummySaga)

    success = await service.delete_entity("e-1")

    assert success is True
    service.enqueue_daily_summary_rebuild.assert_awaited_once_with(
        date_str="2026-03-28",
        namespace="sales",
    )
