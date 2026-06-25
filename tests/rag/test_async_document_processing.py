"""
Тесты асинхронной обработки документов через rag_worker.

Тестирует:
- Files API + index-file — возвращает pending и task_id
- GET /rag/api/v1/documents/{id}/status - статус обработки
- Polling механизм до завершения обработки
- Интеграция с document_processing_status таблицей
"""

import asyncio

import pytest

from tests.rag.helpers import upload_rag_document_bytes, wait_rag_document_status


@pytest.mark.asyncio
async def test_async_document_upload_returns_202(
    frontend_client,
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """Upload + index-file возвращает pending и task_id."""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    data = await upload_rag_document_bytes(
        frontend_client,
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename="async_test.txt",
        content=b"Test document for async processing",
        content_type="text/plain",
    )

    assert "document_id" in data
    assert "task_id" in data
    assert "status" in data
    assert data["status"] == "pending"
    assert "file" in data
    assert data["file"]["file_id"] == data["document_id"]


@pytest.mark.asyncio
async def test_document_status_endpoint(
    frontend_client,
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """GET /documents/{id}/status возвращает статус документа"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    upload_response = await upload_rag_document_bytes(
        frontend_client,
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename="status_test.txt",
        content=b"Test document for status check",
        content_type="text/plain",
    )
    document_id = upload_response["document_id"]

    status_response = await rag_client.get(
        f"/rag/api/v1/documents/{document_id}/status",
        headers=auth_headers_system,
    )

    assert status_response.status_code == 200
    status_data = status_response.json()

    assert status_data["document_id"] == document_id
    assert "task_id" in status_data
    assert "namespace_id" in status_data
    assert "document_name" in status_data
    assert "status" in status_data
    assert status_data["status"] in ["pending", "processing", "completed", "failed"]


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_async_document_processing_completes(
    frontend_client,
    rag_client,
    unique_namespace_name,
    taskiq_broker,
    auth_headers_system,
):
    """Документ успешно обрабатывается через worker и статус меняется на completed"""
    _ = taskiq_broker
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    upload_response = await upload_rag_document_bytes(
        frontend_client,
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename="complete_test.txt",
        content=b"Test document for complete processing flow",
        content_type="text/plain",
    )
    document_id = upload_response["document_id"]

    status_data = await wait_rag_document_status(
        rag_client,
        document_id,
        auth_headers_system,
    )
    assert status_data["completed_at"] is not None


@pytest.mark.asyncio
async def test_list_documents_includes_processing_status(
    frontend_client,
    rag_client,
    unique_namespace_name,
    auth_headers_system,
):
    """GET /documents возвращает и completed и processing документы"""
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
        filename="list_test.txt",
        content=b"Content",
        content_type="text/plain",
    )

    list_response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system,
    )

    assert list_response.status_code == 200
    data = list_response.json()

    assert "items" in data
    assert len(data["items"]) > 0

    for doc in data["items"]:
        assert "document_id" in doc
        assert "name" in doc
        assert "status" in doc
        assert doc["status"] in ["pending", "processing", "completed", "failed"]


@pytest.mark.asyncio
async def test_document_status_not_found(rag_client, auth_headers_system):
    """GET /documents/{id}/status возвращает 404 для несуществующего документа"""
    response = await rag_client.get(
        "/rag/api/v1/documents/nonexistent-document-id/status",
        headers=auth_headers_system,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_multiple_documents_processing(
    frontend_client,
    rag_client,
    unique_namespace_name,
    taskiq_broker,
    auth_headers_system,
):
    """Несколько документов могут обрабатываться параллельно"""
    _ = taskiq_broker
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    document_ids = []
    for i in range(3):
        response = await upload_rag_document_bytes(
            frontend_client,
            rag_client,
            auth_headers_system,
            namespace_id=namespace_id,
            filename=f"multi_test_{i}.txt",
            content=f"Content {i}".encode(),
            content_type="text/plain",
        )
        document_ids.append(response["document_id"])

    max_wait = 120
    interval = 0.25
    elapsed = 0
    completed_count = 0

    while elapsed < max_wait and completed_count < len(document_ids):
        completed_count = 0
        for doc_id in document_ids:
            status_response = await rag_client.get(
                f"/rag/api/v1/documents/{doc_id}/status",
                headers=auth_headers_system,
            )
            status_data = status_response.json()

            if status_data["status"] == "completed":
                completed_count += 1
            elif status_data["status"] == "failed":
                pytest.fail(f"Document {doc_id} processing failed")

        if completed_count == len(document_ids):
            break

        await asyncio.sleep(interval)
        elapsed += interval

    assert completed_count == len(document_ids), (
        f"Only {completed_count}/{len(document_ids)} documents completed"
    )
