"""
Тесты API namespaces RAG Service.

Тестирует:
- POST /rag/api/v1/namespaces - создание namespace
- GET /rag/api/v1/namespaces - список namespaces
- DELETE /rag/api/v1/namespaces/{id} - удаление namespace
"""

import pytest


async def _namespace_names(rag_client, headers, *, provider: str | None = None) -> set[str]:
    names: set[str] = set()
    offset = 0
    limit = 200
    while True:
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if provider is not None:
            params["provider"] = provider
        response = await rag_client.get(
            "/rag/api/v1/namespaces",
            headers=headers,
            params=params,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        items = data["items"]
        if not isinstance(items, list):
            raise AssertionError("namespaces items must be a list")
        for item in items:
            name = item["name"]
            if not isinstance(name, str):
                raise AssertionError("namespace name must be a string")
            names.add(name)
        total = data["total"]
        if not isinstance(total, int):
            raise AssertionError("namespaces total must be an int")
        if len(items) < limit or offset + limit >= total:
            return names
        offset += limit


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
    names = await _namespace_names(rag_client, auth_headers_system)
    assert unique_namespace_name in names


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
    names = await _namespace_names(
        rag_client, auth_headers_system, provider="pgvector"
    )
    assert unique_namespace_name in names


@pytest.mark.asyncio
async def test_delete_namespace(
    frontend_client,
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """DELETE /namespaces/{id} удаляет namespace вместе с документами"""
    create_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = create_response.json()["name"]

    from tests.rag.helpers import upload_rag_document_bytes

    await upload_rag_document_bytes(
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename="test.txt",
        content=b"test content for delete",
        content_type="text/plain",
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


