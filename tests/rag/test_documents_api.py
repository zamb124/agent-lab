"""
Тесты API документов RAG Service.

Тестирует:
- POST /frontend/api/v1/files/ + POST .../documents/index-file — загрузка документа
- GET /rag/api/v1/namespaces/{id}/documents - список документов
- DELETE /rag/api/v1/namespaces/{id}/documents/{doc_id} - удаление документа
"""

from io import BytesIO
from pathlib import Path

import pytest

from tests.rag.helpers import upload_rag_document_bytes


@pytest.mark.asyncio
async def test_upload_document(
    frontend_client,
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """Upload через Files API + index-file возвращает pending и task_id."""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    content = b"Test document content for RAG testing. This is a sample document."
    data = await upload_rag_document_bytes(
        frontend_client,
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename="test.txt",
        content=content,
        content_type="text/plain",
    )

    assert "document_id" in data
    assert "task_id" in data
    assert "status" in data
    assert data["status"] == "pending"
    assert data["file_id"] == data["document_id"]


@pytest.mark.asyncio
async def test_upload_document_pdf(
    frontend_client,
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """PDF загружается через Files API + index-file."""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    pdf_path = (
        Path(__file__).resolve().parents[1]
        / "core"
        / "files"
        / "example-docs"
        / "pdf"
        / "header-test-doc.pdf"
    )
    pdf_content = pdf_path.read_bytes()
    data = await upload_rag_document_bytes(
        frontend_client,
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename="test.pdf",
        content=pdf_content,
        content_type="application/pdf",
    )
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_list_documents(
    frontend_client,
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """GET /namespaces/{id}/documents возвращает документы"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    await upload_rag_document_bytes(
        frontend_client,
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename="test.txt",
        content=b"Content for testing",
        content_type="text/plain",
    )

    response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system,
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
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system,
    )
    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert len(data["items"]) == 0


@pytest.mark.asyncio
async def test_list_documents_with_limit(
    frontend_client,
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """GET /namespaces/{id}/documents?limit=5 ограничивает количество документов"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    for i in range(3):
        await upload_rag_document_bytes(
            frontend_client,
            rag_client,
            auth_headers_system,
            namespace_id=namespace_id,
            filename=f"test{i}.txt",
            content=f"Content {i}".encode(),
            content_type="text/plain",
        )

    response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents?limit=2",
        headers=auth_headers_system,
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) <= 2


@pytest.mark.asyncio
async def test_delete_document(
    frontend_client,
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """DELETE /namespaces/{id}/documents/{doc_id} удаляет документ"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    doc_response = await upload_rag_document_bytes(
        frontend_client,
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename="test.txt",
        content=b"Content",
        content_type="text/plain",
    )
    document_id = doc_response["document_id"]

    delete_response = await rag_client.delete(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/{document_id}",
        headers=auth_headers_system,
    )
    assert delete_response.status_code == 200


@pytest.mark.asyncio
async def test_delete_nonexistent_document(rag_client, unique_namespace_name, auth_headers_system):
    """DELETE /namespaces/{id}/documents/{doc_id} с несуществующим ID возвращает 404"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    response = await rag_client.delete(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/nonexistent_doc_id",
        headers=auth_headers_system,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_multiple_documents(
    frontend_client,
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """Загрузка нескольких документов в один namespace"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    doc_ids = []
    for i in range(3):
        response = await upload_rag_document_bytes(
            frontend_client,
            rag_client,
            auth_headers_system,
            namespace_id=namespace_id,
            filename=f"doc{i}.txt",
            content=f"Document {i} content".encode(),
            content_type="text/plain",
        )
        assert response["status"] == "pending"
        doc_ids.append(response["document_id"])

    list_response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system,
    )
    assert list_response.status_code == 200
    documents = list_response.json()["items"]

    assert len(documents) >= 3


@pytest.mark.asyncio
async def test_get_document_content(
    rag_client,
    unique_namespace_name,
    auth_headers_system,
    provider_litserve_service,
    rag_worker,
):
    """GET /namespaces/{id}/documents/{doc_id}/content возвращает склеенный markdown."""
    _ = provider_litserve_service, rag_worker
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]
    marker = "document_content_marker_alpha"
    ingest = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/ingest-text",
        json={
            "text": f"First chunk paragraph with {marker}. Second paragraph for content endpoint.",
            "document_name": "content-test.md",
            "metadata": {"page_summary": "Test summary"},
        },
        headers=auth_headers_system,
    )
    assert ingest.status_code == 200
    document_id = ingest.json()["document_id"]

    response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/{document_id}/content",
        headers=auth_headers_system,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == document_id
    assert payload["document_name"] == "content-test.md"
    assert marker in payload["markdown"]
    assert payload["chunks_count"] >= 1
    assert payload["metadata"]["page_summary"] == "Test summary"


@pytest.mark.asyncio
async def test_get_document_content_not_found(
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """GET content для несуществующего document_id возвращает 404."""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/missing_doc_id/content",
        headers=auth_headers_system,
    )
    assert response.status_code == 404
