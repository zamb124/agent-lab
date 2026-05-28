"""Проверки валидации REST без запуска воркера импорта."""

from __future__ import annotations

from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_str

pytestmark = pytest.mark.timeout(20, func_only=True)


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


@pytest.mark.asyncio
async def test_start_import_chunk_max_chars_pydantic(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
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
async def test_start_import_empty_source(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
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
    body = _http_json(response)
    detail = object_str(body.get("detail", ""), field="detail").lower()
    assert "пуст" in detail or "файл" in detail or "текст" in detail


@pytest.mark.asyncio
async def test_start_import_rejects_single_file_id_field(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
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
