"""
Хелперы для тестов: загрузка файлов, ожидание задач, откат.

Задачи теперь трекируются через /crm/api/v1/tasks/*.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from typing import cast

from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_str, optional_object_dict


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


async def crm_upload_bytes(
    crm_client: AsyncClient,
    headers: dict[str, str],
    filename: str,
    content: bytes,
) -> str:
    files = {"file": (filename, content, "application/octet-stream")}
    response = await crm_client.post("/crm/api/v1/files/", files=files, headers=headers)
    if response.status_code != 200:
        raise AssertionError(f"upload {filename}: {response.status_code} {response.text}")
    payload = _http_json(response)
    return object_str(payload.get("file_id"), field="file_id").strip()


async def wait_task_terminal(
    crm_client: AsyncClient,
    headers: dict[str, str],
    task_id: str,
    *,
    timeout_sec: float = 60.0,
    poll_sec: float = 0.35,
    fail_on_failed: bool = True,
) -> dict[str, object]:
    """Ждём терминального статуса задачи через GET /tasks/{task_id}."""
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = await crm_client.get(
            f"/crm/api/v1/tasks/{task_id}",
            headers=headers,
        )
        if response.status_code != 200:
            raise AssertionError(f"GET task: {response.status_code} {response.text}")
        last = _http_json(response)
        status = last.get("status")
        if status in ("completed", "failed", "cancelled", "rolled_back"):
            if fail_on_failed and status == "failed":
                error_message = last.get("error_message")
                raise AssertionError(f"task failed: {error_message}")
            return last
        await asyncio.sleep(poll_sec)
    raise TimeoutError(f"task {task_id} не завершился за {timeout_sec}s: last={last}")


async def rollback_task(
    crm_client: AsyncClient,
    headers: dict[str, str],
    task_id: str,
) -> dict[str, object]:
    response = await crm_client.post(
        f"/crm/api/v1/tasks/{task_id}/rollback",
        headers=headers,
    )
    if response.status_code != 200:
        raise AssertionError(f"rollback: {response.status_code} {response.text}")
    return _http_json(response)


async def start_analyze_and_wait(
    crm_client: AsyncClient,
    headers: dict[str, str],
    note_id: str,
    *,
    timeout_sec: float = 30.0,
    fail_on_failed: bool = True,
    extra_params: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Запускает анализ заметки и ждёт завершения.

    Возвращает (task_row, ai_analysis_draft со стороны ноты).
    """
    body: dict[str, object] = {"note_id": note_id}
    if extra_params is not None:
        body.update(extra_params)
    start_resp = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json=body,
        headers=headers,
    )
    if start_resp.status_code != 202:
        raise AssertionError(f"start analyze: {start_resp.status_code} {start_resp.text}")
    start_body = _http_json(start_resp)
    analyze_task_id = object_str(start_body.get("task_id"), field="task_id").strip()

    task = await wait_task_terminal(
        crm_client,
        headers,
        analyze_task_id,
        timeout_sec=timeout_sec,
        fail_on_failed=fail_on_failed,
    )

    note_resp = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=headers)
    if note_resp.status_code != 200:
        raise AssertionError(f"GET note: {note_resp.status_code} {note_resp.text}")
    note_body = _http_json(note_resp)
    attributes = object_dict(note_body.get("attributes"), field="attributes")
    draft_value = attributes.get("ai_analysis_draft")
    draft = optional_object_dict(draft_value) if draft_value is not None else {}
    return task, draft


async def fetch_entity_texts(
    crm_client: AsyncClient,
    headers: dict[str, str],
    entity_ids: Iterable[str],
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for entity_id in entity_ids:
        entity_id = entity_id.strip()
        if not entity_id:
            continue
        response = await crm_client.get(
            f"/crm/api/v1/entities/{entity_id}",
            headers=headers,
        )
        if response.status_code != 200:
            raise AssertionError(
                f"get entity {entity_id}: {response.status_code} {response.text}"
            )
        row = _http_json(response)
        name = object_str(row.get("name") or "", field="name")
        description = object_str(row.get("description") or "", field="description")
        out.append((entity_id, name, description))
    return out


def combined_entity_blob(rows: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"{name}\n{description}" for _entity_id, name, description in rows)
