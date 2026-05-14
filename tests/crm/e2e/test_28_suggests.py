from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest

from apps.crm_worker.tasks.suggest_tasks import crm_generate_namespace_suggests_tick
from tests.fixtures.crm_test_setup import wait_for_crm_semantic_search_hit

pytestmark = [
    pytest.mark.real_taskiq,
    pytest.mark.timeout(180, func_only=True),
]

_META = {"dates_mentioned": [], "places_mentioned": [], "key_topics": []}


async def _create_entity(crm_client, headers: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    response = await crm_client.post("/crm/api/v1/entities/", json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


async def _run_suggest_tick(namespace: str) -> dict[str, Any]:
    task = await crm_generate_namespace_suggests_tick.kiq(
        company_id="system",
        namespace=namespace,
    )
    result = await task.wait_result(timeout=90)
    assert not result.is_err, f"Task failed: {result.error}"
    return result.return_value


async def _wait_note_analyze(crm_client, headers: dict[str, Any], note_id: str) -> dict[str, Any]:
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
    task_id = start.json()["task_id"]
    deadline = time.monotonic() + 90.0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = await crm_client.get(f"/crm/api/v1/tasks/{task_id}", headers=headers)
        assert response.status_code == 200, response.text
        last = response.json()
        if last.get("status") in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.4)
    assert last.get("status") == "completed", last
    return last


async def _suggests(
    crm_client,
    headers: dict[str, Any],
    namespace: str,
    *,
    status: str = "pending",
) -> list[dict[str, Any]]:
    response = await crm_client.get(
        f"/crm/api/v1/namespaces/{namespace}/suggests",
        params={"status": status},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _pending_suggests(crm_client, headers: dict[str, Any], namespace: str) -> list[dict[str, Any]]:
    return await _suggests(crm_client, headers, namespace, status="pending")


class TestSuggestsE2E:
    @pytest.mark.asyncio
    async def test_real_taskiq_generates_duplicate_suggest(
        self,
        crm_client,
        crm_worker,
        unique_id: str,
        auth_headers_system: dict[str, Any],
    ) -> None:
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
        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=marker,
            entity_type="contact",
            namespace=namespace,
            required_entity_ids={first["entity_id"], second["entity_id"]},
        )

        summary = await _run_suggest_tick(namespace)
        assert summary["duplicate_created"] >= 1

        target_ids = {first["entity_id"], second["entity_id"]}
        suggests = await _pending_suggests(crm_client, auth_headers_system, namespace)
        duplicate = next(
            item
            for item in suggests
            if item["suggest_type"] == "duplicate"
            and set(item["target_entity_ids"]) == target_ids
        )

        second_summary = await _run_suggest_tick(namespace)
        assert second_summary["duplicate_skipped_existing"] >= 1
        pending_after_second_tick = [
            item
            for item in await _pending_suggests(crm_client, auth_headers_system, namespace)
            if item["suggest_type"] == "duplicate"
            and set(item["target_entity_ids"]) == target_ids
        ]
        assert [item["id"] for item in pending_after_second_tick] == [duplicate["id"]]

        response = await crm_client.post(
            f"/crm/api/v1/namespaces/{namespace}/suggests/{duplicate['id']}/resolve",
            headers=auth_headers_system,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "resolved"

        first_after = await crm_client.get(
            f"/crm/api/v1/entities/{first['entity_id']}",
            headers=auth_headers_system,
        )
        second_after = await crm_client.get(
            f"/crm/api/v1/entities/{second['entity_id']}",
            headers=auth_headers_system,
        )
        assert {first_after.status_code, second_after.status_code} == {200, 404}

    @pytest.mark.asyncio
    async def test_real_taskiq_auto_resolves_duplicate_suggest(
        self,
        crm_client,
        crm_worker,
        unique_id: str,
        auth_headers_system: dict[str, Any],
    ) -> None:
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
        assert create_type.json()["auto_resolve_suggests"] is True

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
        await wait_for_crm_semantic_search_hit(
            crm_client,
            auth_headers_system,
            query=marker,
            entity_type=type_id,
            namespace=namespace,
            required_entity_ids={first["entity_id"], second["entity_id"]},
        )

        summary = await _run_suggest_tick(namespace)
        assert summary["duplicate_auto_resolved"] >= 1

        target_ids = {first["entity_id"], second["entity_id"]}
        all_suggests = await _suggests(crm_client, auth_headers_system, namespace, status="")
        auto_resolved = [
            item
            for item in all_suggests
            if item["suggest_type"] == "duplicate"
            and item["status"] == "auto_resolved"
            and set(item["target_entity_ids"]) == target_ids
        ]
        assert len(auto_resolved) == 1

        first_after = await crm_client.get(
            f"/crm/api/v1/entities/{first['entity_id']}",
            headers=auth_headers_system,
        )
        second_after = await crm_client.get(
            f"/crm/api/v1/entities/{second['entity_id']}",
            headers=auth_headers_system,
        )
        assert {first_after.status_code, second_after.status_code} == {200, 404}

    @pytest.mark.asyncio
    async def test_real_taskiq_generates_missed_entity_suggest_from_llm_draft(
        self,
        crm_client,
        crm_worker,
        mock_llm_redis,
        unique_id: str,
        auth_headers_system: dict[str, Any],
    ) -> None:
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
        await mock_llm_redis(
            [
                {
                    "type": "text",
                    "content": json.dumps(
                        {
                            "note": {
                                "entity_type": "note",
                                "name": note["name"],
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
                                }
                            ],
                            "relationships": [],
                            "metadata": _META,
                            "attachment_summaries": [],
                        }
                    ),
                }
            ]
        )

        await _wait_note_analyze(crm_client, auth_headers_system, note["entity_id"])
        summary = await _run_suggest_tick(namespace)
        assert summary["missed_entity_created"] >= 1

        suggests = await _pending_suggests(crm_client, auth_headers_system, namespace)
        missed = next(
            item
            for item in suggests
            if item["suggest_type"] == "missed_entity"
            and item["target_entity_ids"] == [note["entity_id"]]
        )

        second_summary = await _run_suggest_tick(namespace)
        assert second_summary["missed_entity_created"] == 0
        pending_after_second_tick = [
            item
            for item in await _pending_suggests(crm_client, auth_headers_system, namespace)
            if item["suggest_type"] == "missed_entity"
            and item["target_entity_ids"] == [note["entity_id"]]
        ]
        assert [item["id"] for item in pending_after_second_tick] == [missed["id"]]

        response = await crm_client.post(
            f"/crm/api/v1/namespaces/{namespace}/suggests/{missed['id']}/resolve",
            headers=auth_headers_system,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "resolved"

        note_after = await crm_client.get(
            f"/crm/api/v1/entities/{note['entity_id']}",
            headers=auth_headers_system,
        )
        assert note_after.status_code == 200, note_after.text
        attrs = note_after.json()["attributes"]
        assert "ai_analysis_draft" not in attrs
        assert isinstance(attrs.get("ai_analysis_applied_at"), str)
