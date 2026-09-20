"""
Тесты API провайдеров RAG Service.

Тестирует:
- GET /rag/api/v1/providers - список провайдеров и current_provider из конфига
"""

import pytest


@pytest.mark.asyncio
async def test_list_providers(rag_client, auth_headers_system):
    """GET /providers возвращает список провайдеров"""
    response = await rag_client.get("/rag/api/v1/providers", headers=auth_headers_system)
    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert "current_provider" in data
    assert len(data["items"]) > 0

    provider = data["items"][0]
    assert "name" in provider
    assert "enabled" in provider
    assert "is_default" in provider
    assert "type" in provider


@pytest.mark.asyncio
async def test_list_providers_pgvector_present(rag_client, auth_headers_system):
    """Список провайдеров содержит pgvector"""
    response = await rag_client.get("/rag/api/v1/providers", headers=auth_headers_system)
    assert response.status_code == 200
    data = response.json()

    pgvector = next((p for p in data["items"] if p["name"] == "pgvector"), None)

    assert pgvector is not None
    assert pgvector["enabled"] is True
