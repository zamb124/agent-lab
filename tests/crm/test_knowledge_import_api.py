"""Проверки валидации REST без запуска воркера импорта."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.timeout(20, func_only=True)


@pytest.mark.asyncio
async def test_start_import_chunk_max_chars_pydantic(crm_client, auth_headers_system, unique_id) -> None:
    ns = f"g_{unique_id}"
    response = await crm_client.post(
        "/crm/api/v1/tasks/knowledge-import",
        json={
            "namespace": ns,
            "mode": "notes_only",
            "source_text": "hello",
            "chunk_max_chars": 500,
        },
        headers=auth_headers_system,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_start_import_empty_source(crm_client, auth_headers_system, unique_id) -> None:
    ns = f"g_{unique_id}"
    response = await crm_client.post(
        "/crm/api/v1/tasks/knowledge-import",
        json={
            "namespace": ns,
            "mode": "notes_only",
            "source_text": "   ",
        },
        headers=auth_headers_system,
    )
    assert response.status_code == 400
    detail = str(response.json().get("detail", "")).lower()
    assert "пуст" in detail or "файл" in detail or "текст" in detail


@pytest.mark.asyncio
async def test_start_import_rejects_single_file_id_field(crm_client, auth_headers_system, unique_id) -> None:
    ns = f"g_{unique_id}"
    response = await crm_client.post(
        "/crm/api/v1/tasks/knowledge-import",
        json={
            "namespace": ns,
            "mode": "notes_only",
            "source_file_id": "00000000-0000-0000-0000-000000000001",
            "source_file_ids": ["00000000-0000-0000-0000-000000000002"],
        },
        headers=auth_headers_system,
    )
    assert response.status_code == 422
    assert "source_file_id" in response.text
