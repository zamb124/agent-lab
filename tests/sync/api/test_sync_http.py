"""Интеграционные тесты Sync HTTP API (ASGI, Bearer, реальный sync worker)."""

from __future__ import annotations

import pytest

from tests.sync.api._helpers import seed_namespace_via_repo


@pytest.mark.asyncio
async def test_http_list_namespaces_returns_default(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    """`GET /sync/api/v1/namespaces` возвращает namespace из shared KV.

    `NamespaceRepository.list` лениво создаёт `default` namespace, если у
    компании ещё нет ни одного, поэтому пустой список не ожидается.
    """
    r = await sync_client.get("/sync/api/v1/namespaces", headers=sync_auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert any(item["name"] == "default" for item in body["items"])


@pytest.mark.asyncio
async def test_http_put_namespace_sync_settings(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    name = f"ns_{unique_id}_settings"
    await seed_namespace_via_repo(company_id, name)
    r = await sync_client.put(
        f"/sync/api/v1/namespaces/{name}",
        headers=sync_auth_headers,
        json={
            "sync_settings": {
                "transcribe_voice_messages": True,
                "speech_to_chat_enabled": False,
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == name
    assert body["sync_settings"]["transcribe_voice_messages"] is True
    assert body["sync_settings"]["speech_to_chat_enabled"] is False


@pytest.mark.asyncio
async def test_http_put_namespace_not_found(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    r = await sync_client.put(
        f"/sync/api/v1/namespaces/missing_{unique_id}",
        headers=sync_auth_headers,
        json={"sync_settings": None},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_http_list_channels_empty(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get("/sync/api/v1/channels/", headers=sync_auth_headers)
    assert r.status_code == 200
    assert r.json()["items"] == []
