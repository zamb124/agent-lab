"""
Тесты API провайдеров RAG Service.

Тестирует:
- GET /rag/api/v1/providers - список провайдеров
- POST /rag/api/v1/providers/switch - переключение провайдера
"""

import pytest


@pytest.mark.asyncio
async def test_list_providers(rag_client, auth_headers_system):
    """GET /providers возвращает список провайдеров"""
    response = await rag_client.get("/rag/api/v1/providers", headers=auth_headers_system)
    assert response.status_code == 200
    data = response.json()
    
    assert "providers" in data
    assert "current_provider" in data
    assert len(data["providers"]) > 0
    
    # Проверяем структуру провайдера
    provider = data["providers"][0]
    assert "name" in provider
    assert "enabled" in provider
    assert "is_default" in provider
    assert "type" in provider


@pytest.mark.asyncio
async def test_list_providers_chromadb_present(rag_client, auth_headers_system):
    """Список провайдеров содержит chromadb"""
    response = await rag_client.get("/rag/api/v1/providers", headers=auth_headers_system)
    assert response.status_code == 200
    data = response.json()
    
    providers = data["providers"]
    chromadb = next((p for p in providers if p["name"] == "chromadb"), None)
    
    assert chromadb is not None
    assert chromadb["enabled"] is True


@pytest.mark.asyncio
async def test_switch_provider_chromadb(rag_client, auth_headers_system):
    """POST /providers/switch переключает на chromadb"""
    response = await rag_client.post(
        "/rag/api/v1/providers/switch",
        json={"provider_name": "chromadb"},
        headers=auth_headers_system
    )
    assert response.status_code == 200
    data = response.json()
    
    assert data["success"] is True
    assert data["provider"] == "chromadb"
    assert "message" in data


@pytest.mark.asyncio
async def test_switch_provider_invalid(rag_client, auth_headers_system):
    """POST /providers/switch с невалидным провайдером возвращает ошибку"""
    response = await rag_client.post(
        "/rag/api/v1/providers/switch",
        json={"provider_name": "invalid_provider"},
        headers=auth_headers_system
    )
    assert response.status_code == 400
    data = response.json()
    
    assert "detail" in data
    assert "invalid_provider" in data["detail"].lower()


@pytest.mark.asyncio
async def test_switch_provider_missing_name(rag_client, auth_headers_system):
    """POST /providers/switch без имени провайдера возвращает ошибку валидации"""
    response = await rag_client.post(
        "/rag/api/v1/providers/switch",
        json={},
        headers=auth_headers_system
    )
    assert response.status_code == 422

