"""
Хелперы для тестов импорта базы знаний: загрузка файлов, ожидание воркера, откат.
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


async def wait_knowledge_import_terminal(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    import_id: str,
    *,
    timeout_sec: float = 20.0,
    poll_sec: float = 0.35,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = await crm_client.get(
            f"/crm/api/v1/knowledge-imports/{import_id}",
            headers=headers,
        )
        if response.status_code != 200:
            raise AssertionError(f"get import: {response.status_code} {response.text}")
        last = response.json()
        status = last.get("status")
        if status in ("completed", "failed", "cancelled"):
            if status == "failed":
                raise AssertionError(
                    f"import failed: {last.get('error_message')} chunk_errors={last.get('chunk_errors')}"
                )
            return last
        await asyncio.sleep(poll_sec)
    raise TimeoutError(f"knowledge import {import_id} не завершился: last={last}")


async def rollback_knowledge_import(
    crm_client: AsyncClient,
    headers: dict[str, Any],
    import_id: str,
) -> dict[str, Any]:
    response = await crm_client.post(
        f"/crm/api/v1/knowledge-imports/{import_id}/rollback",
        headers=headers,
    )
    if response.status_code != 200:
        raise AssertionError(f"rollback: {response.status_code} {response.text}")
    return response.json()


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
        et = str(row.get("entity_type") or "")
        out.append((eid, name, desc))
    return out


def combined_entity_blob(rows: list[tuple[str, str, str]]) -> str:
    return "\n".join(f"{n}\n{d}" for _, n, d in rows)
