from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from httpx import AsyncClient, Response

from apps.crm_worker.tasks.suggest_tasks import crm_generate_namespace_suggests_tick
from tests.crm.e2e._json_helpers import json_object, object_dict, object_list, object_str
from tests.fixtures.crm_test_setup import wait_for_crm_semantic_search_hit

pytestmark = [
    pytest.mark.real_taskiq,
    pytest.mark.timeout(180, func_only=True),
]

MockLlmRedisFactory = Callable[[list[object]], Awaitable[None]]

_META: dict[str, object] = {"dates_mentioned": [], "places_mentioned": [], "key_topics": []}


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(entity: dict[str, object]) -> str:
    return object_str(entity.get("entity_id"), field="entity_id")


def _suggest_id(suggest: dict[str, object]) -> str:
    return object_str(suggest.get("suggest_id"), field="suggest_id")


def _entity_ids_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    entity_ids: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str):
            entity_ids.append(item)
    return entity_ids


def _tick_count(summary: dict[str, object], field: str) -> int:
    value = summary.get(field)
    if not isinstance(value, int):
        raise AssertionError(f"{field} must be an int")
    return value


async def _create_entity(
    crm_client: AsyncClient,
    headers: dict[str, str],
    body: dict[str, object],
) -> dict[str, object]:
    response = await crm_client.post("/crm/api/v1/entities/", json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return _http_json(response)


async def _run_suggest_tick(namespace: str) -> dict[str, object]:
    task = await crm_generate_namespace_suggests_tick.kiq(
        company_id="system",
        namespace=namespace,
    )
    result = await task.wait_result(timeout=90)
    assert not result.is_err, f"Task failed: {result.error}"
    return_value = result.return_value
    return json_object(cast(object, return_value))


async def _wait_note_analyze(
    crm_client: AsyncClient,
    headers: dict[str, str],
    note_id: str,
) -> dict[str, object]:
    start = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json={
            "note_id": note_id,
            "mode": "analyze",
            "include_attachments": False,
            "check_duplicates": False,
        },
        headers=headers,
    )
    assert start.status_code == 202, start.text
    task_id = object_str(_http_json(start).get("task_id"), field="task_id")
    deadline = time.monotonic() + 90.0
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = await crm_client.get(f"/crm/api/v1/tasks/{task_id}", headers=headers)
        assert response.status_code == 200, response.text
        last = _http_json(response)
        status = last.get("status")
        if status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.4)
    assert last.get("status") == "completed", last
    return last


async def _suggests(
    crm_client: AsyncClient,
    headers: dict[str, str],
    namespace: str,
    *,
    status: str = "pending",
) -> list[dict[str, object]]:
    response = await crm_client.get(
        f"/crm/api/v1/namespaces/{namespace}/suggests",
        params={"status": status},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return object_list(_http_json(response).get("items"))


async def _pending_suggests(
    crm_client: AsyncClient,
    headers: dict[str, str],
    namespace: str,
) -> list[dict[str, object]]:
    return await _suggests(crm_client, headers, namespace, status="pending")


class TestSuggestsE2E:
    @pytest.mark.asyncio
    async def test_real_taskiq_generates_duplicate_suggest(
        self,
        crm_client: AsyncClient,
        crm_worker: object,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        _ = crm_worker
        namespace = f"g_{unique_id}"
        marker = f"suggest-dup-{unique_id}"
        first = await _create_entity(
            crm_client,
            auth_headers_system,
            {
                "entity_type": "contact",
                "namespace": namespace,
                "name": f"Suggest Duplicate {unique_id}",
                "description": f"duplicate marker {marker}",
            },
        )
        second = await _create_entity(
            crm_client,
            auth_headers_system,
            {
                "entity_type": "contact",
                "namespace": namespace,
                "name": f"Suggest Duplicate {unique_id}",
                "description": f"duplicate marker {marker}",
            },
        )
        first_id = _entity_id(first)
        second_id = _entity_id(second)
        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=marker,
            entity_type="contact",
            namespace=namespace,
            required_entity_ids={first_id, second_id},
        )

        summary = await _run_suggest_tick(namespace)
        assert _tick_count(summary, "duplicate_created") >= 1

        target_ids = {first_id, second_id}
        suggests = await _pending_suggests(crm_client, auth_headers_system, namespace)
        duplicate = next(
            item
            for item in suggests
            if object_str(item.get("suggest_type"), field="suggest_type") == "duplicate"
            and set(_entity_ids_list(item.get("target_entity_ids"))) == target_ids
        )

        second_summary = await _run_suggest_tick(namespace)
        assert _tick_count(second_summary, "duplicate_skipped_existing") >= 1
        pending_after_second_tick = [
            item
            for item in await _pending_suggests(crm_client, auth_headers_system, namespace)
            if object_str(item.get("suggest_type"), field="suggest_type") == "duplicate"
            and set(_entity_ids_list(item.get("target_entity_ids"))) == target_ids
        ]
        assert [_suggest_id(item) for item in pending_after_second_tick] == [_suggest_id(duplicate)]

        response = await crm_client.post(
            f"/crm/api/v1/namespaces/{namespace}/suggests/{_suggest_id(duplicate)}/resolve",
            headers=auth_headers_system,
        )
        assert response.status_code == 200, response.text
        assert object_str(_http_json(response).get("status"), field="status") == "resolved"

        first_after = await crm_client.get(
            f"/crm/api/v1/entities/{first_id}",
            headers=auth_headers_system,
        )
        second_after = await crm_client.get(
            f"/crm/api/v1/entities/{second_id}",
            headers=auth_headers_system,
        )
        assert {first_after.status_code, second_after.status_code} == {200, 404}

    @pytest.mark.asyncio
    async def test_real_taskiq_auto_resolves_duplicate_suggest(
        self,
        crm_client: AsyncClient,
        crm_worker: object,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        _ = crm_worker
        namespace = f"g_{unique_id}"
        type_id = f"auto_contact_{unique_id}"
        create_type = await crm_client.post(
            "/crm/api/v1/entity-types/",
            json={
                "type_id": type_id,
                "namespace": namespace,
                "name": "Auto Contact",
                "auto_resolve_suggests": True,
            },
            headers=auth_headers_system,
        )
        assert create_type.status_code == 200, create_type.text
        assert _http_json(create_type).get("auto_resolve_suggests") is True

        marker = f"suggest-auto-dup-{unique_id}"
        first = await _create_entity(
            crm_client,
            auth_headers_system,
            {
                "entity_type": type_id,
                "namespace": namespace,
                "name": f"Auto Suggest Duplicate {unique_id}",
                "description": f"duplicate marker {marker}",
            },
        )
        second = await _create_entity(
            crm_client,
            auth_headers_system,
            {
                "entity_type": type_id,
                "namespace": namespace,
                "name": f"Auto Suggest Duplicate {unique_id}",
                "description": f"duplicate marker {marker}",
            },
        )
        first_id = _entity_id(first)
        second_id = _entity_id(second)
        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=marker,
            entity_type=type_id,
            namespace=namespace,
            required_entity_ids={first_id, second_id},
        )

        summary = await _run_suggest_tick(namespace)
        assert _tick_count(summary, "duplicate_auto_resolved") >= 1

        target_ids = {first_id, second_id}
        all_suggests = await _suggests(crm_client, auth_headers_system, namespace, status="")
        auto_resolved = [
            item
            for item in all_suggests
            if object_str(item.get("suggest_type"), field="suggest_type") == "duplicate"
            and object_str(item.get("status"), field="status") == "auto_resolved"
            and set(_entity_ids_list(item.get("target_entity_ids"))) == target_ids
        ]
        assert len(auto_resolved) == 1

        first_after = await crm_client.get(
            f"/crm/api/v1/entities/{first_id}",
            headers=auth_headers_system,
        )
        second_after = await crm_client.get(
            f"/crm/api/v1/entities/{second_id}",
            headers=auth_headers_system,
        )
        assert {first_after.status_code, second_after.status_code} == {200, 404}

    @pytest.mark.asyncio
    async def test_real_taskiq_generates_missed_entity_suggest_from_llm_draft(
        self,
        crm_client: AsyncClient,
        crm_worker: object,
        mock_llm_redis: MockLlmRedisFactory,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        _ = crm_worker
        namespace = f"g_{unique_id}"
        note = await _create_entity(
            crm_client,
            auth_headers_system,
            {
                "entity_type": "note",
                "namespace": namespace,
                "name": f"Suggest missed note {unique_id}",
                "description": "Нужно создать задачу follow-up после встречи.",
            },
        )
        note_id = _entity_id(note)
        note_name = object_str(note.get("name"), field="name")
        await mock_llm_redis(
            [
                {
                    "type": "text",
                    "content": json.dumps(
                        {
                            "note": {
                                "entity_type": "note",
                                "name": note_name,
                                "description": "Итог: нужен follow-up по встрече.",
                                "attributes": {},
                                "confidence": 0.9,
                            },
                            "entities": [
                                {
                                    "entity_type": "task",
                                    "name": f"Follow-up {unique_id}",
                                    "description": "Связаться с участниками после встречи.",
                                    "attributes": {},
                                    "confidence": 0.88,
                                },
                            ],
                            "relationships": [],
                            "metadata": _META,
                            "attachment_summaries": [],
                        },
                    ),
                },
            ],
        )

        _ = await _wait_note_analyze(crm_client, auth_headers_system, note_id)
        summary = await _run_suggest_tick(namespace)
        assert _tick_count(summary, "missed_entity_created") >= 1

        suggests = await _pending_suggests(crm_client, auth_headers_system, namespace)
        missed = next(
            item
            for item in suggests
            if object_str(item.get("suggest_type"), field="suggest_type") == "missed_entity"
            and _entity_ids_list(item.get("target_entity_ids")) == [note_id]
        )

        second_summary = await _run_suggest_tick(namespace)
        assert _tick_count(second_summary, "missed_entity_created") == 0
        pending_after_second_tick = [
            item
            for item in await _pending_suggests(crm_client, auth_headers_system, namespace)
            if object_str(item.get("suggest_type"), field="suggest_type") == "missed_entity"
            and _entity_ids_list(item.get("target_entity_ids")) == [note_id]
        ]
        assert [_suggest_id(item) for item in pending_after_second_tick] == [_suggest_id(missed)]

        response = await crm_client.post(
            f"/crm/api/v1/namespaces/{namespace}/suggests/{_suggest_id(missed)}/resolve",
            headers=auth_headers_system,
        )
        assert response.status_code == 200, response.text
        assert object_str(_http_json(response).get("status"), field="status") == "resolved"

        note_after = await crm_client.get(
            f"/crm/api/v1/entities/{note_id}",
            headers=auth_headers_system,
        )
        assert note_after.status_code == 200, note_after.text
        attrs = object_dict(_http_json(note_after).get("attributes"), field="attributes")
        assert "ai_analysis_draft" not in attrs
        applied_at = attrs.get("ai_analysis_applied_at")
        assert isinstance(applied_at, str)
