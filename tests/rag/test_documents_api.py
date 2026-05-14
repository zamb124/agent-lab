"""
Тесты API документов RAG Service.

Тестирует:
- POST /rag/api/v1/namespaces/{id}/documents - загрузка документа
- GET /rag/api/v1/namespaces/{id}/documents - список документов
- DELETE /rag/api/v1/namespaces/{id}/documents/{doc_id} - удаление документа
"""

from io import BytesIO

import pytest


@pytest.mark.asyncio
async def test_upload_document(rag_client, unique_namespace_name, auth_headers_system):
    """POST /namespaces/{id}/documents загружает текстовый файл"""
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]

    # Загружаем текстовый файл
    content = b"Test document content for RAG testing. This is a sample document."
    files = {"file": ("test.txt", BytesIO(content), "text/plain")}

    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    assert response.status_code == 202
    data = response.json()

    assert "document_id" in data
    assert "task_id" in data
    assert "status" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_upload_document_pdf(rag_client, unique_namespace_name, auth_headers_system):
    """POST /namespaces/{id}/documents загружает PDF файл"""
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]

    # Загружаем PDF (минимальный валидный PDF)
    pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n%%EOF"
    files = {"file": ("test.pdf", BytesIO(pdf_content), "application/pdf")}

    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    assert response.status_code == 202  # Async processing


@pytest.mark.asyncio
async def test_list_documents(rag_client, unique_namespace_name, auth_headers_system):
    """GET /namespaces/{id}/documents возвращает документы"""
    # Создаем namespace и загружаем документ
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]

    files = {"file": ("test.txt", BytesIO(b"Content for testing"), "text/plain")}
    await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )

    # Получаем список
    response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system
    )
    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert "total" in data
    assert len(data["items"]) > 0
    assert data["items"][0].get("namespace") == namespace_id


@pytest.mark.asyncio
async def test_list_documents_empty_namespace(rag_client, unique_namespace_name, auth_headers_system):
    """GET /namespaces/{id}/documents для пустого namespace возвращает пустой список"""
    # Создаем namespace без документов
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]

    # Получаем список
    response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system
    )
    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert len(data["items"]) == 0


@pytest.mark.asyncio
async def test_list_documents_with_limit(rag_client, unique_namespace_name, auth_headers_system):
    """GET /namespaces/{id}/documents?limit=5 ограничивает количество документов"""
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]

    # Загружаем несколько документов
    for i in range(3):
        files = {"file": (f"test{i}.txt", BytesIO(f"Content {i}".encode()), "text/plain")}
        await rag_client.post(
            f"/rag/api/v1/namespaces/{namespace_id}/documents",
            files=files,
            headers=auth_headers_system
        )

    # Получаем список с лимитом
    response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents?limit=2",
        headers=auth_headers_system
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) <= 2


@pytest.mark.asyncio
async def test_delete_document(rag_client, unique_namespace_name, auth_headers_system):
    """DELETE /namespaces/{id}/documents/{doc_id} удаляет документ"""
    # Создаем namespace и загружаем документ
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]

    files = {"file": ("test.txt", BytesIO(b"Content"), "text/plain")}
    doc_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    document_id = doc_response.json()["document_id"]

    # Документ можно удалять сразу после загрузки
    # Удаление работает для документов в любом статусе (pending/processing/completed)
    delete_response = await rag_client.delete(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/{document_id}",
        headers=auth_headers_system
    )
    assert delete_response.status_code == 200  # Document deleted successfully


@pytest.mark.asyncio
async def test_delete_nonexistent_document(rag_client, unique_namespace_name, auth_headers_system):
    """DELETE /namespaces/{id}/documents/{doc_id} с несуществующим ID возвращает 404"""
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]

    # Пытаемся удалить несуществующий документ
    response = await rag_client.delete(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/nonexistent_doc_id",
        headers=auth_headers_system
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_multiple_documents(rag_client, unique_namespace_name, auth_headers_system     ):
    """Загрузка нескольких документов в один namespace"""
    # Создаем namespace
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]

    # Загружаем несколько документов
    doc_ids = []
    for i in range(3):
        files = {"file": (f"doc{i}.txt", BytesIO(f"Document {i} content".encode()), "text/plain")}
        response = await rag_client.post(
            f"/rag/api/v1/namespaces/{namespace_id}/documents",
                files=files,
            headers=auth_headers_system
        )
        assert response.status_code == 202  # Async processing
        doc_ids.append(response.json()["document_id"])

    # Проверяем что все документы в списке
    list_response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system
    )
    assert list_response.status_code == 200
    documents = list_response.json()["items"]

    assert len(documents) >= 3

