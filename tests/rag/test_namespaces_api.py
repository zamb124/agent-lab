"""
Тесты API namespaces RAG Service.

Тестирует:
- POST /rag/api/v1/namespaces - создание namespace
- GET /rag/api/v1/namespaces - список namespaces
- DELETE /rag/api/v1/namespaces/{id} - удаление namespace
"""

import pytest


@pytest.mark.asyncio
async def test_create_namespace(rag_client, unique_namespace_name, auth_headers_system):
    """POST /namespaces создает namespace в pgvector"""
    response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={
            "name": unique_namespace_name,
            "description": "Test namespace"
        },
        headers=auth_headers_system
    )
    assert response.status_code == 201
    data = response.json()
    
    assert data["name"] == unique_namespace_name
    assert "name" in data
    assert data["description"] == "Test namespace"


@pytest.mark.asyncio
async def test_create_namespace_minimal(rag_client, unique_namespace_name, auth_headers_system):
    """POST /namespaces создает namespace без description"""
    response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    assert response.status_code == 201
    data = response.json()
    
    assert data["name"] == unique_namespace_name
    assert "name" in data


@pytest.mark.asyncio
async def test_list_namespaces(rag_client, unique_namespace_name, auth_headers_system):
    """GET /namespaces возвращает созданные namespaces"""
    # Создаем namespace
    await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    
    # Получаем список
    response = await rag_client.get("/rag/api/v1/namespaces", headers=auth_headers_system)
    assert response.status_code == 200
    data = response.json()
    
    assert "items" in data
    assert len(data["items"]) > 0, f"Namespaces list is empty: {data}"
    assert any(ns["name"] == unique_namespace_name for ns in data["items"]), f"Namespace {unique_namespace_name} not found in {[ns['name'] for ns in data['items']]}"


@pytest.mark.asyncio
async def test_list_namespaces_with_provider_param(rag_client, unique_namespace_name, auth_headers_system):
    """GET /namespaces?provider=pgvector возвращает namespaces для конкретного провайдера"""
    # Создаем namespace
    await rag_client.post(
        "/rag/api/v1/namespaces?provider=pgvector",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    
    # Получаем список с параметром провайдера
    response = await rag_client.get("/rag/api/v1/namespaces?provider=pgvector", headers=auth_headers_system)
    assert response.status_code == 200
    data = response.json()
    
    assert any(ns["name"] == unique_namespace_name for ns in data["items"])


@pytest.mark.asyncio
async def test_delete_namespace(rag_client, unique_namespace_name, auth_headers_system):
    """DELETE /namespaces/{id} удаляет namespace вместе с документами"""
    from io import BytesIO

    # Создаем namespace
    create_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = create_response.json()["name"]

    # Загружаем документ, чтобы namespace реально существовал в pgvector
    files = {"file": ("test.txt", BytesIO(b"test content for delete"), "text/plain")}
    await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system,
    )

    # Удаляем
    delete_response = await rag_client.delete(
        f"/rag/api/v1/namespaces/{namespace_id}",
        headers=auth_headers_system
    )
    assert delete_response.status_code == 200
    data = delete_response.json()

    assert data["success"] is True
    assert data["name"] == namespace_id


@pytest.mark.asyncio
async def test_delete_nonexistent_namespace(rag_client, auth_headers_system):
    """DELETE /namespaces/{id} с несуществующим ID возвращает 404"""
    # Используем правильный формат namespace_id: company_id:name
    response = await rag_client.delete(
        "/rag/api/v1/namespaces/nonexistent_namespace",
        headers=auth_headers_system
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_namespace_duplicate_name(rag_client, unique_namespace_name, auth_headers_system):
    """Создание namespace с дублирующимся именем (поведение зависит от провайдера)"""
    # Создаем первый namespace
    response1 = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    assert response1.status_code == 201
    
    # Пытаемся создать второй с тем же именем
    response2 = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    # pgvector может разрешить дубликаты или вернуть ошибку
    # Проверяем что ответ валидный (201 или 400)
    assert response2.status_code in [201, 400]


