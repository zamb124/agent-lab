"""
Хелперы для тестов: загрузка файлов, ожидание задач, откат.

Задачи теперь трекируются через /crm/api/v1/tasks/*.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Iterable

from httpx import AsyncClient


async def crm_upload_bytes(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    filename: str,
    content: bytes,
) -> str:
    files = {"file": (filename, content, "application/octet-stream")}
    response = await crm_client.post("/crm/api/v1/files/", files=files, headers=headers)
    if response.status_code != 200:
        raise AssertionError(f"upload {filename}: {response.status_code} {response.text}")
    payload = response.json()
    file_id = payload.get("file_id")
    if not isinstance(file_id, str) or not file_id.strip():
        raise AssertionError(f"upload response без file_id: {payload}")
    return file_id.strip()


async def wait_task_terminal(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    task_id: str,
    *,
    timeout_sec: float = 60.0,
    poll_sec: float = 0.35,
    fail_on_failed: bool = True,
) -> dict[str, Any]:
    """Ждём терминального статуса задачи через GET /tasks/{task_id}."""
    deadline = time.monotonic() + timeout_sec
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = await crm_client.get(
            f"/crm/api/v1/tasks/{task_id}",
            headers=headers,
        )
        if response.status_code != 200:
            raise AssertionError(f"GET task: {response.status_code} {response.text}")
        last = response.json()
        status = last.get("status")
        if status in ("completed", "failed", "cancelled", "rolled_back"):
            if fail_on_failed and status == "failed":
                raise AssertionError(
                    f"task failed: {last.get('error_message')}"
                )
            return last
        await asyncio.sleep(poll_sec)
    raise TimeoutError(f"task {task_id} не завершился за {timeout_sec}s: last={last}")


async def rollback_task(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    response = await crm_client.post(
        f"/crm/api/v1/tasks/{task_id}/rollback",
        headers=headers,
    )
    if response.status_code != 200:
        raise AssertionError(f"rollback: {response.status_code} {response.text}")
    return response.json()


async def start_analyze_and_wait(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    note_id: str,
    *,
    timeout_sec: float = 30.0,
    fail_on_failed: bool = True,
    **extra_params: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Запускает анализ заметки и ждёт завершения.

    Возвращает (task_row, ai_analysis_draft со стороны ноты).
    """
    body = {"note_id": note_id, **extra_params}
    start_resp = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json=body,
        headers=headers,
    )
    if start_resp.status_code != 202:
        raise AssertionError(f"start analyze: {start_resp.status_code} {start_resp.text}")
    task_id = start_resp.json().get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise AssertionError(f"нет task_id: {start_resp.json()}")

    task = await wait_task_terminal(
        crm_client, headers, task_id,
        timeout_sec=timeout_sec,
        fail_on_failed=fail_on_failed,
    )

    note_resp = await crm_client.get(f"/crm/api/v1/entities/{note_id}", headers=headers)
    if note_resp.status_code != 200:
        raise AssertionError(f"GET note: {note_resp.status_code} {note_resp.text}")
    draft = note_resp.json().get("attributes", {}).get("ai_analysis_draft") or {}
    return task, draft


async def fetch_entity_texts(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    entity_ids: Iterable[str],
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for eid in entity_ids:
        eid = str(eid).strip()
        if not eid:
            continue
        r = await crm_client.get(f"/crm/api/v1/entities/{eid}", headers=headers)
        if r.status_code != 200:
            raise AssertionError(f"get entity {eid}: {r.status_code} {r.text}")
        row = r.json()
        name = str(row.get("name") or "")
        desc = str(row.get("description") or "")
        out.append((eid, name, desc))
    return out


def combined_entity_blob(rows: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"{n}\n{d}" for _, n, d in rows)
