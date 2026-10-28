from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

import pytest
from aiohttp import web

import apps.crm.services.entity_service as entity_service_module
from apps.crm.config import get_crm_settings
from apps.crm.di import CrmDi
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.relationship import Relationship
from apps.crm.models.task import CRMTask
from apps.crm.services.daily_summary_cache_service import DailySummaryCacheService
from apps.crm.services.entity_service import SUMMARY_ALL_NAMESPACES_TASK_KEY, EntityService
from core.clients.a2a_client import A2AClient, A2ATaskResult
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.context import set_context
from core.di import open_di
from core.di.kit import ProcessIdentity
from core.events.contract import PlatformEvent
from core.files.urls import resolve_files_route_segment
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.realtime.submit import (
    bind_local_event_ingest,
    local_event_ingest_bound,
    unbind_local_event_ingest,
)
from core.test_scope import LOG_TEST_SCOPE
from core.types import JsonObject, parse_json_object
from tests.fixtures.aiohttp_ephemeral import ephemeral_web_server

pytestmark = pytest.mark.no_crm_http


def _a2a_response(*, response: str, raw: dict) -> A2ATaskResult:
    result_raw = raw.get("result")
    if isinstance(result_raw, dict):
        result = result_raw
    else:
        result = {
            "status": {"state": "TASK_STATE_COMPLETED"},
            "artifacts": [{"artifactId": "a1", "parts": [{"text": response}]}],
        }
    artifacts_raw = result.get("artifacts")
    artifacts: list[object] = list(artifacts_raw) if isinstance(artifacts_raw, list) else []
    return A2ATaskResult(
        task=result,
        artifacts=artifacts,
        response=response,
        status="completed",
        raw=raw,
    )


def _set_test_context() -> None:
    set_context(
        Context(
            user=User(user_id="u-1", name="Tester"),
            active_company=Company(company_id="c-1", name="Company"),
            channel="test",
        )
    )


_SUMMARY_DATE = "2026-03-28"


def _bind_summary_company(company_id: str, user_id: str) -> None:
    set_context(
        Context(
            user=User(user_id=user_id, name="Tester"),
            active_company=Company(company_id=company_id, name="Company"),
            channel="test",
        )
    )


async def _create_summary_note(
    company_id: str,
    user_id: str,
    entity_id: str,
    *,
    name: str = "n1",
    description: str = "d",
    tags: list[str] | None = None,
    namespace: str = "default",
    note_date: date | None = None,
) -> None:
    await CRMEntity.create(
        CRMEntity(
            entity_id=entity_id,
            company_id=company_id,
            user_id=user_id,
            entity_type="note",
            name=name,
            description=description,
            tags=tags or [],
            namespace=namespace,
            note_date=note_date or date.fromisoformat(_SUMMARY_DATE),
            attributes={"ai_analysis_applied_at": "2026-01-01T00:00:00+00:00"},
        )
    )


async def _cleanup_summary_enqueue(
    company_id: str,
    entity_id: str,
    cache: DailySummaryCacheService,
) -> None:
    await cache.clear_revalidating(
        company_id=company_id,
        namespace=None,
        date_str=_SUMMARY_DATE,
    )
    await cache.release_rebuild_lock(
        company_id=company_id,
        namespace=None,
        date_str=_SUMMARY_DATE,
    )
    redis = RedisClient(get_settings().database.redis_url)
    _ = await redis.delete(
        DailySummaryCacheService._state_key(company_id, None, _SUMMARY_DATE)
    )
    _ = await CRMEntity.delete_returning(entity_id)
    tasks = await CRMTask.namespace_tasks(
        company_id,
        SUMMARY_ALL_NAMESPACES_TASK_KEY,
        "daily_summary",
    ).all()
    for task in tasks:
        _ = await CRMTask.delete_by_id(task.task_id)


def _capture_enqueue_dates(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    recorded: list[object] = []

    async def record_enqueue(*_args: object, **kwargs: object) -> None:
        recorded.append(kwargs.get("date_str"))

    monkeypatch.setattr(entity_service_module, "enqueue", record_enqueue)
    return recorded


def _capture_enqueue_period(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, object]]:
    recorded: list[tuple[object, object]] = []

    async def record_enqueue(*_args: object, **kwargs: object) -> None:
        recorded.append((kwargs.get("date_from"), kwargs.get("date_to")))

    monkeypatch.setattr(entity_service_module, "enqueue", record_enqueue)
    return recorded


async def _cleanup_period_enqueue(
    company_id: str,
    cache: DailySummaryCacheService,
    date_from: str,
    date_to: str,
) -> None:
    await cache.clear_period_revalidating(
        company_id=company_id,
        namespace=None,
        date_from=date_from,
        date_to=date_to,
    )
    redis = RedisClient(get_settings().database.redis_url)
    _ = await redis.delete(
        DailySummaryCacheService._period_state_key(company_id, None, date_from, date_to)
    )
    tasks = await CRMTask.namespace_tasks(
        company_id,
        SUMMARY_ALL_NAMESPACES_TASK_KEY,
        "period_summary",
    ).all()
    for task in tasks:
        _ = await CRMTask.delete_by_id(task.task_id)


@asynccontextmanager
async def _local_platform_events(published: list[str] | None = None) -> AsyncIterator[None]:
    async def accept(event: PlatformEvent) -> PlatformEvent:
        if published is not None:
            published.append(event.type)
        return event

    bound_here = not local_event_ingest_bound()
    if bound_here:
        bind_local_event_ingest(accept)
    try:
        yield
    finally:
        if bound_here:
            unbind_local_event_ingest()


async def _clear_summary_state(
    cache: DailySummaryCacheService,
    company_id: str,
    namespace: str | None,
    date_str: str,
) -> None:
    await cache.clear_revalidating(
        company_id=company_id,
        namespace=namespace,
        date_str=date_str,
    )
    redis = RedisClient(get_settings().database.redis_url)
    _ = await redis.delete(
        DailySummaryCacheService._state_key(company_id, namespace, date_str)
    )


async def _stored_note_source_version(entity_id: str) -> dict[str, str | int | None]:
    note = await CRMEntity.get(entity_id)
    if note is None:
        raise RuntimeError(f"summary note {entity_id} was not stored")
    return {"notes_count": 1, "max_updated_at": note.updated_at.isoformat()}


def _completed_skill_body(data: JsonObject) -> JsonObject:
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "result": {
            "id": "task-1",
            "status": {"state": "TASK_STATE_COMPLETED"},
            "artifacts": [
                {
                    "artifactId": "a1",
                    "parts": [{"data": data}],
                }
            ],
        },
    }


def _skill_rpc_app(body: JsonObject, seen: list[JsonObject] | None = None) -> web.Application:
    async def rpc(request: web.Request) -> web.Response:
        if seen is not None:
            seen.append(parse_json_object(await request.read(), "skill request"))
        return web.json_response(body)

    app = web.Application()
    app.router.add_post("/flows/api/v1/crm", rpc)
    return app


def _period_partials(raw: JsonObject) -> list[JsonObject]:
    params = raw.get("params")
    if not isinstance(params, dict):
        raise ValueError("skill request params must be an object")
    metadata = params.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("skill request metadata must be an object")
    variables = metadata.get("variables")
    if not isinstance(variables, dict):
        raise ValueError("skill request variables must be an object")
    partials_json = variables.get("partials_json")
    if not isinstance(partials_json, str):
        raise ValueError("skill request partials_json must be a string")
    loaded = json.loads(partials_json)
    if not isinstance(loaded, list):
        raise ValueError("partials_json must be an array")
    partials: list[JsonObject] = []
    for item in loaded:
        if not isinstance(item, dict):
            raise ValueError("period partial must be an object")
        partials.append(parse_json_object(json.dumps(item), "period partial"))
    return partials


@asynccontextmanager
async def _crm_skill_service(
    monkeypatch: pytest.MonkeyPatch,
    skill_data: JsonObject,
    seen: list[JsonObject] | None = None,
) -> AsyncIterator[EntityService]:
    cache = DailySummaryCacheService(RedisClient(get_settings().database.redis_url))
    async with _crm_graph() as di:
        async with ephemeral_web_server(_skill_rpc_app(_completed_skill_body(skill_data), seen)) as base_url:
            monkeypatch.setattr(
                type(get_settings().server),
                "get_flows_service_url",
                lambda _server: base_url,
            )
            yield _summary_service(di, cache=cache, a2a_client=A2AClient(timeout=3.0))


@asynccontextmanager
async def _crm_graph() -> AsyncIterator[CrmDi]:
    async with open_di(
        CrmDi,
        settings=get_crm_settings(),
        identity=ProcessIdentity(
            service_name="crm",
            files_route_segment=resolve_files_route_segment("crm"),
        ),
        database="crm_url",
    ) as di:
        yield di


def _summary_service(
    di: CrmDi,
    *,
    cache: DailySummaryCacheService,
    a2a_client: A2AClient | None = None,
) -> EntityService:
    base = di.entity_service
    return EntityService(
        rag=base._rag,
        rerank_score_cache=base._rerank_score_cache,
        namespace_service=base._namespace_service,
        attachment_service=base._attachment_service,
        a2a_client=base._a2a_client if a2a_client is None else a2a_client,
        daily_summary_cache_service=cache,
        daily_summary_artifact_service=base._daily_summary_artifact_service,
        user_person_service=base._user_person_service,
        authz=base._authz,
        entity_access=base._entity_access,
        crm_work_item_service=base._crm_work_item_service,
    )


@asynccontextmanager
async def _service_with_redis_cache() -> AsyncIterator[tuple[EntityService, DailySummaryCacheService]]:
    cache = DailySummaryCacheService(RedisClient(get_settings().database.redis_url))
    async with _crm_graph() as di:
        yield _summary_service(di, cache=cache), cache


@pytest.mark.asyncio
async def test_enqueue_daily_summary_rebuild_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    user_id = f"user-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, user_id)
    await _create_summary_note(company_id, user_id, entity_id)
    recorded: list[object] = []

    async def record_enqueue(*_args: object, **kwargs: object) -> None:
        recorded.append(kwargs.get("extra_labels"))

    monkeypatch.setattr(entity_service_module, "enqueue", record_enqueue)
    async with _service_with_redis_cache() as (service, cache):
        try:
            first = await service.enqueue_daily_summary_rebuild(
                date_str=_SUMMARY_DATE,
                namespace=None,
            )
            second = await service.enqueue_daily_summary_rebuild(
                date_str=_SUMMARY_DATE,
                namespace=None,
            )
            tasks = await CRMTask.namespace_tasks(
                company_id,
                SUMMARY_ALL_NAMESPACES_TASK_KEY,
                "daily_summary",
            ).all()
            assert first is True
            assert second is False
            assert len(recorded) == 1
            assert len(tasks) == 1
            assert tasks[0].data.get("date_str") == _SUMMARY_DATE
        finally:
            await _cleanup_summary_enqueue(company_id, entity_id, cache)


@pytest.mark.asyncio
async def test_enqueue_daily_summary_rebuild_isolates_mock_llm_scope(
    monkeypatch: pytest.MonkeyPatch,
    platform_test_scope: str,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    user_id = f"user-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, user_id)
    await _create_summary_note(company_id, user_id, entity_id)
    recorded: list[object] = []

    async def record_enqueue(*_args: object, **kwargs: object) -> None:
        recorded.append(kwargs.get("extra_labels"))

    monkeypatch.setattr(entity_service_module, "enqueue", record_enqueue)
    async with _service_with_redis_cache() as (service, cache):
        try:
            first = await service.enqueue_daily_summary_rebuild(
                date_str=_SUMMARY_DATE,
                namespace=None,
            )
            assert first is True
            assert recorded == [{LOG_TEST_SCOPE: f"{platform_test_scope}:crm_summary"}]
        finally:
            await _cleanup_summary_enqueue(company_id, entity_id, cache)


@pytest.mark.asyncio
async def test_rebuild_daily_summary_returns_stale_if_lock_busy(unique_id: str) -> None:
    company_id = f"sum-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, f"user-{unique_id}")
    async with _service_with_redis_cache() as (service, cache):
        await cache.set_state(
            company_id=company_id,
            namespace=None,
            date_str=_SUMMARY_DATE,
            state={
                "date": _SUMMARY_DATE,
                "summary": "cached",
                "source_version": {"notes_count": 1, "max_updated_at": "2026-03-28T10:00:00+00:00"},
                "revalidating": False,
            },
        )
        assert await cache.acquire_rebuild_lock(
            company_id=company_id,
            namespace=None,
            date_str=_SUMMARY_DATE,
        )
        try:
            payload = await service.rebuild_daily_summary(date_str=_SUMMARY_DATE, namespace=None)
            assert payload["revalidating"] is True
            assert payload["stale"] is True
            assert payload["summary"] == "cached"
        finally:
            await _cleanup_summary_enqueue(company_id, entity_id, cache)


@pytest.mark.asyncio
async def test_get_daily_summary_cached_miss_enqueues_rebuild(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    user_id = f"user-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, user_id)
    await _create_summary_note(company_id, user_id, entity_id)
    recorded = _capture_enqueue_dates(monkeypatch)
    async with _service_with_redis_cache() as (service, cache):
        try:
            payload = await service.get_daily_summary_cached(date_str=_SUMMARY_DATE, namespace=None)
            assert payload["revalidating"] is True
            assert payload["stale"] is True
            assert payload["summary"] == ""
            assert recorded == [_SUMMARY_DATE]
        finally:
            await _cleanup_summary_enqueue(company_id, entity_id, cache)


@pytest.mark.asyncio
async def test_get_daily_summary_cached_marks_stale_and_requeues(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    user_id = f"user-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, user_id)
    await _create_summary_note(company_id, user_id, entity_id)
    recorded = _capture_enqueue_dates(monkeypatch)
    async with _service_with_redis_cache() as (service, cache):
        await cache.set_state(
            company_id=company_id,
            namespace=None,
            date_str=_SUMMARY_DATE,
            state={
                "date": _SUMMARY_DATE,
                "summary": "old",
                "entities": [],
                "entity_links": [],
                "source_version": {"notes_count": 2, "max_updated_at": "2026-03-28T10:00:00+00:00"},
                "revalidating": False,
                "generated_at": "2026-03-28T10:01:00+00:00",
            },
        )
        try:
            payload = await service.get_daily_summary_cached(date_str=_SUMMARY_DATE, namespace=None)
            assert payload["summary"] == "old"
            assert payload["stale"] is True
            assert payload["revalidating"] is True
            assert recorded == [_SUMMARY_DATE]
        finally:
            await _cleanup_summary_enqueue(company_id, entity_id, cache)


@pytest.mark.asyncio
async def test_get_daily_summary_cached_force_rebuild_on_fresh_cache(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    user_id = f"user-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, user_id)
    await _create_summary_note(company_id, user_id, entity_id)
    source_version = await _stored_note_source_version(entity_id)
    recorded = _capture_enqueue_dates(monkeypatch)
    async with _service_with_redis_cache() as (service, cache):
        await cache.set_state(
            company_id=company_id,
            namespace=None,
            date_str=_SUMMARY_DATE,
            state={
                "date": _SUMMARY_DATE,
                "summary": "fresh summary",
                "entities": [],
                "entity_links": [],
                "source_version": source_version,
                "revalidating": False,
                "generated_at": "2026-03-28T11:01:00+00:00",
            },
        )
        try:
            payload = await service.get_daily_summary_cached(
                date_str=_SUMMARY_DATE,
                namespace=None,
                force_rebuild=True,
            )
            assert payload["summary"] == "fresh summary"
            assert payload["revalidating"] is True
            assert payload["stale"] is True
            assert recorded == [_SUMMARY_DATE]
        finally:
            await _cleanup_summary_enqueue(company_id, entity_id, cache)


@pytest.mark.asyncio
async def test_get_daily_summary_cached_empty_day_no_enqueue(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    _bind_summary_company(company_id, f"user-{unique_id}")
    recorded = _capture_enqueue_dates(monkeypatch)
    published: list[str] = []
    async with _service_with_redis_cache() as (service, cache):
        try:
            async with _local_platform_events(published):
                payload = await service.get_daily_summary_cached(
                    date_str=_SUMMARY_DATE,
                    namespace=None,
                )
            assert payload["revalidating"] is False
            assert payload["stale"] is False
            assert _SUMMARY_DATE in str(payload["summary"])
            assert recorded == []
            artifact = await service._daily_summary_artifact_service.get_daily_payload(
                company_id=company_id,
                namespace=None,
                date_str=_SUMMARY_DATE,
            )
            assert artifact is not None
            assert artifact["summary"] == f"За {_SUMMARY_DATE} заметок не найдено."
            assert "crm/daily_summary/updated" in published
            stored = await cache.get_state(
                company_id=company_id,
                namespace=None,
                date_str=_SUMMARY_DATE,
            )
            assert stored is not None
            assert stored["summary"] == f"За {_SUMMARY_DATE} заметок не найдено."
        finally:
            await _clear_summary_state(cache, company_id, None, _SUMMARY_DATE)


@pytest.mark.asyncio
async def test_get_daily_summary_cached_hydrates_from_s3_when_redis_miss(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    user_id = f"user-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, user_id)
    await _create_summary_note(company_id, user_id, entity_id)
    source_version = await _stored_note_source_version(entity_id)
    recorded = _capture_enqueue_dates(monkeypatch)
    async with _service_with_redis_cache() as (service, cache):
        async with _local_platform_events():
            await service._daily_summary_artifact_service.put_daily_payload(
                company_id=company_id,
                namespace=None,
                date_str=_SUMMARY_DATE,
                payload={
                    "date": _SUMMARY_DATE,
                    "summary": "from s3",
                    "entities": ["Acme"],
                    "entity_links": [],
                    "source_version": source_version,
                    "generated_at": "2026-03-28T12:00:00+00:00",
                },
            )
        try:
            payload = await service.get_daily_summary_cached(
                date_str=_SUMMARY_DATE,
                namespace=None,
            )
            assert payload["summary"] == "from s3"
            assert payload["entities"] == ["Acme"]
            assert payload["entity_links"] == []
            assert payload["revalidating"] is False
            assert recorded == []
            stored = await cache.get_state(
                company_id=company_id,
                namespace=None,
                date_str=_SUMMARY_DATE,
            )
            assert stored is not None
            assert stored["summary"] == "from s3"
        finally:
            await _clear_summary_state(cache, company_id, None, _SUMMARY_DATE)
            _ = await CRMEntity.delete_returning(entity_id)


@pytest.mark.asyncio
async def test_get_period_summary_cached_long_period_clamps_to_max_days(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    _bind_summary_company(company_id, f"user-{unique_id}")
    monkeypatch.setattr(get_crm_settings(), "period_summary_max_days", 1)
    recorded = _capture_enqueue_period(monkeypatch)
    async with _service_with_redis_cache() as (service, cache):
        try:
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
            assert recorded == [("2026-03-29", "2026-03-29")]
        finally:
            await _cleanup_period_enqueue(company_id, cache, "2026-03-29", "2026-03-29")


@pytest.mark.asyncio
async def test_get_period_summary_cached_miss_enqueues_period_rebuild(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    _bind_summary_company(company_id, f"user-{unique_id}")
    recorded = _capture_enqueue_period(monkeypatch)
    async with _service_with_redis_cache() as (service, cache):
        try:
            payload = await service.get_period_summary_cached(
                date_from="2026-03-28",
                date_to="2026-03-29",
                namespace=None,
            )
            assert payload["revalidating"] is True
            assert payload["stale"] is True
            assert payload["summary"] == ""
            assert recorded == [("2026-03-28", "2026-03-29")]
        finally:
            await _cleanup_period_enqueue(company_id, cache, "2026-03-28", "2026-03-29")


@pytest.mark.asyncio
async def test_compute_period_summary_calls_merge_skill_for_range(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    _bind_summary_company(company_id, f"user-{unique_id}")
    seen: list[JsonObject] = []
    async with _crm_skill_service(
        monkeypatch,
        {"summary": "Итог периода", "entities": ["Org"]},
        seen,
    ) as service:
        payload = await service.compute_period_summary(
            date_from="2026-03-28",
            date_to="2026-03-29",
            namespace=None,
        )
    assert payload["summary"] == "Итог периода"
    assert payload["entities"] == ["Org"]
    assert payload["date_from"] == "2026-03-28"
    assert payload["date_to"] == "2026-03-29"
    assert len(seen) == 1
    partials = _period_partials(seen[0])
    assert len(partials) == 2
    assert {partial["date"] for partial in partials} == {"2026-03-28", "2026-03-29"}


@pytest.mark.asyncio
async def test_compute_daily_summary_uses_structured_data_summary(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, f"user-{unique_id}")
    await _create_summary_note(company_id, f"user-{unique_id}", entity_id)
    try:
        async with _crm_skill_service(
            monkeypatch,
            {
                "summary": "Structured summary from artifact",
                "entities": ["Yandex", "Sber"],
            },
        ) as service:
            payload = await service.compute_daily_summary(date_str=_SUMMARY_DATE, namespace=None)
        assert payload["summary"] == "Structured summary from artifact"
        assert payload["entities"] == ["Yandex", "Sber"]
    finally:
        _ = await CRMEntity.delete_returning(entity_id)


@pytest.mark.asyncio
async def test_compute_daily_summary_adds_inline_entity_links_from_note_graph(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    user_id = f"user-{unique_id}"
    note_id = f"note-{unique_id}"
    org_id = f"org-{unique_id}"
    _bind_summary_company(company_id, user_id)
    await _create_summary_note(
        company_id,
        user_id,
        note_id,
        description="Обсудили Yandex",
        namespace="sales",
    )
    await CRMEntity.create(
        CRMEntity(
            entity_id=org_id,
            company_id=company_id,
            user_id=user_id,
            entity_type="company",
            name="Yandex",
            namespace="sales",
        )
    )
    await Relationship.create(
        Relationship(
            relationship_id=f"rel-{unique_id}",
            company_id=company_id,
            source_entity_id=note_id,
            target_entity_id=org_id,
            relationship_type="mentions",
            namespace="sales",
        )
    )
    try:
        async with _crm_skill_service(
            monkeypatch,
            {
                "summary": "Договорились с Yandex о следующей встрече",
                "entities": ["Yandex"],
            },
        ) as service:
            payload = await service.compute_daily_summary(
                date_str=_SUMMARY_DATE,
                namespace="sales",
            )
        assert payload["summary"] == (
            "Договорились с "
            f"[@Yandex](entity:{org_id})"
            " о следующей встрече"
        )
        assert payload["entity_links"] == [
            {
                "entity_id": org_id,
                "name": "Yandex",
                "entity_type": "company",
                "namespace": "sales",
            }
        ]
    finally:
        _ = await Relationship.delete_by_company_and_relationship_id(
            company_id,
            f"rel-{unique_id}",
        )
        _ = await CRMEntity.delete_returning(note_id)
        _ = await CRMEntity.delete_returning(org_id)


@pytest.mark.asyncio
async def test_compute_daily_summary_uses_nested_structured_output_summary(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, f"user-{unique_id}")
    await _create_summary_note(company_id, f"user-{unique_id}", entity_id)
    try:
        async with _crm_skill_service(
            monkeypatch,
            {
                "structured_output": {
                    "summary": "Nested structured summary",
                    "entities": ["Ozon"],
                    "highlights": [],
                }
            },
        ) as service:
            payload = await service.compute_daily_summary(date_str=_SUMMARY_DATE, namespace=None)
        assert payload["summary"] == "Nested structured summary"
        assert payload["entities"] == ["Ozon"]
    finally:
        _ = await CRMEntity.delete_returning(entity_id)


@pytest.mark.asyncio
async def test_compute_daily_summary_uses_entities_from_notes_when_payload_entities_empty(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, f"user-{unique_id}")
    await _create_summary_note(
        company_id,
        f"user-{unique_id}",
        entity_id,
        name="Встреча с @Yandex",
        description="Обсудили планы с @Sber и @Yandex",
        tags=["Альфа Банк"],
    )
    try:
        async with _crm_skill_service(
            monkeypatch,
            {"summary": "Итог дня без списка сущностей"},
        ) as service:
            payload = await service.compute_daily_summary(date_str=_SUMMARY_DATE, namespace=None)
        assert payload["summary"] == "Итог дня без списка сущностей"
        assert payload["entities"] == ["Альфа Банк", "Yandex", "Sber"]
    finally:
        _ = await CRMEntity.delete_returning(entity_id)


@pytest.mark.asyncio
async def test_compute_daily_summary_raises_when_summary_empty(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, f"user-{unique_id}")
    await _create_summary_note(company_id, f"user-{unique_id}", entity_id)
    body = {
        "summary": "",
        "entities": [],
        "key_events": ["Событие дня"],
        "highlights": ["Главное"],
        "statistics": {"entities_created": 0, "notes_added": 0, "tasks_completed": 0},
    }
    try:
        async with _crm_skill_service(
            monkeypatch,
            {"res": json.dumps(body, ensure_ascii=False)},
        ) as service:
            with pytest.raises(ValueError, match="empty summary"):
                await service.compute_daily_summary(date_str=_SUMMARY_DATE, namespace=None)
    finally:
        _ = await CRMEntity.delete_returning(entity_id)


@pytest.mark.asyncio
async def test_extract_json_from_text_falls_through_invalid_fence() -> None:
    _set_test_context()
    async with _crm_graph() as di:
        service = di.entity_service
    fenced = service._extract_json_from_text('```json\n{"summary": "ok"}\n```')
    assert fenced == {"summary": "ok"}
    fallback = service._extract_json_from_text(
        '```json\nnot-json\n```\n{"summary": "later"}'
    )
    assert fallback == {"summary": "later"}
    assert service._extract_json_from_text("no braces here") == {}


@pytest.mark.asyncio
async def test_extract_data_from_a2a_response_res_as_dict_not_string() -> None:
    _set_test_context()
    async with _crm_graph() as di:
        service = di.entity_service
    out = service._extract_data_from_a2a_response(
        _a2a_response(
            response="",
            raw={
                "result": {
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "data": {
                                        "res": {"summary": "OK", "entities": []},
                                    },
                                }
                            ]
                        }
                    ]
                }
            },
        )
    )
    assert out.get("summary") == "OK"


@pytest.mark.asyncio
async def test_extract_data_from_a2a_response_skips_node_complete_telemetry() -> None:
    _set_test_context()
    async with _crm_graph() as di:
        service = di.entity_service
    out = service._extract_data_from_a2a_response(
        _a2a_response(
            response="",
            raw={
                "result": {
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "data": {
                                        "res": {
                                            "event": "node_complete",
                                            "node_id": "main",
                                            "node_type": "llm_node",
                                        }
                                    }
                                }
                            ]
                        },
                        {
                            "parts": [
                                {
                                    "data": {
                                        "content": json.dumps(
                                            {
                                                "note": {
                                                    "entity_type": "note",
                                                    "name": "Встреча",
                                                    "description": "Итог встречи для CRM анализа",
                                                },
                                                "entities": [
                                                    {
                                                        "entity_type": "task",
                                                        "name": "Иван",
                                                        "description": "Контакт из встречи менеджер",
                                                    }
                                                ],
                                                "relationships": [],
                                            },
                                            ensure_ascii=False,
                                        )
                                    }
                                }
                            ]
                        },
                    ]
                }
            },
        )
    )
    assert out.get("note") is not None
    entities = out.get("entities")
    assert isinstance(entities, list)
    assert len(entities) == 1


@pytest.mark.asyncio
async def test_update_entity_note_date_triggers_both_dates(
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    company_id = f"sum-{unique_id}"
    user_id = f"user-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, user_id)
    await _create_summary_note(
        company_id,
        user_id,
        entity_id,
        description="old",
        namespace="sales",
        note_date=date.fromisoformat("2026-03-27"),
    )
    recorded: list[tuple[object, object]] = []

    async def record_enqueue(*_args: object, **kwargs: object) -> None:
        recorded.append((kwargs.get("date_str"), kwargs.get("namespace")))

    async def skip_index(_rag: object, _entity: object, *, replace: bool) -> None:
        _ = replace

    monkeypatch.setattr(entity_service_module, "enqueue", record_enqueue)
    monkeypatch.setattr(entity_service_module, "index_crm_entity", skip_index)
    async with _service_with_redis_cache() as (service, cache):
        _ = await service._namespace_service.get_or_create("sales")
        _ = await service._namespace_service.get_or_create("support")
        try:
            async with _local_platform_events():
                updated = await service.update_entity(
                    entity_id=entity_id,
                    updates={
                        "note_date": date.fromisoformat("2026-03-28"),
                        "namespace": "support",
                    },
                )
            assert updated.namespace == "support"
            assert updated.note_date == date.fromisoformat("2026-03-28")
            assert recorded == [("2026-03-28", "support")]
            emptied = await cache.get_state(
                company_id=company_id,
                namespace="sales",
                date_str="2026-03-27",
            )
            assert emptied is not None
            assert emptied["summary"] == "За 2026-03-27 заметок не найдено."
        finally:
            await _clear_summary_state(cache, company_id, "sales", "2026-03-27")
            await _clear_summary_state(cache, company_id, "support", "2026-03-28")
            _ = await CRMEntity.delete_returning(entity_id)
            tasks = await CRMTask.namespace_tasks(
                company_id,
                "support",
                "daily_summary",
            ).all()
            for task in tasks:
                _ = await CRMTask.delete_by_id(task.task_id)


@pytest.mark.asyncio
async def test_delete_entity_note_triggers_rebuild(unique_id: str) -> None:
    company_id = f"sum-{unique_id}"
    user_id = f"user-{unique_id}"
    entity_id = f"note-{unique_id}"
    _bind_summary_company(company_id, user_id)
    await _create_summary_note(
        company_id,
        user_id,
        entity_id,
        namespace="sales",
        note_date=date.fromisoformat("2026-03-28"),
    )
    async with _service_with_redis_cache() as (service, cache):
        try:
            async with _local_platform_events():
                success = await service.delete_entity(entity_id)
            assert success is True
            assert await CRMEntity.get(entity_id) is None
            emptied = await cache.get_state(
                company_id=company_id,
                namespace="sales",
                date_str="2026-03-28",
            )
            assert emptied is not None
            assert emptied["summary"] == "За 2026-03-28 заметок не найдено."
        finally:
            await _clear_summary_state(cache, company_id, "sales", "2026-03-28")
            _ = await CRMEntity.delete_returning(entity_id)
