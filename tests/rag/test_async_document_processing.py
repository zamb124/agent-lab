"""
Тесты асинхронной обработки документов через rag_worker.

Тестирует:
- POST /rag/api/v1/namespaces/{id}/documents - возвращает 202 и task_id
- GET /rag/api/v1/documents/{id}/status - статус обработки
- Polling механизм до завершения обработки
- Интеграция с document_processing_status таблицей
"""

import pytest
import asyncio
from io import BytesIO


@pytest.mark.asyncio
async def test_async_document_upload_returns_202(rag_client, unique_namespace_name, auth_headers_system):
    """POST /namespaces/{id}/documents возвращает 202 Accepted с task_id"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    content = b"Test document for async processing"
    files = {"file": ("async_test.txt", BytesIO(content), "text/plain")}
    
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    
    assert response.status_code == 202
    data = response.json()
    
    assert {
        "status": data["status"],
        "file_links_doc": data["file"]["file_id"] == data["document_id"],
        "keys": sorted(k for k in ("document_id", "task_id", "status", "file") if k in data),
    } == {
        "status": "pending",
        "file_links_doc": True,
        "keys": sorted(["document_id", "file", "status", "task_id"]),
    }


@pytest.mark.asyncio
async def test_document_status_endpoint(rag_client, unique_namespace_name, auth_headers_system):
    """GET /documents/{id}/status возвращает статус документа"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    content = b"Test document for status check"
    files = {"file": ("status_test.txt", BytesIO(content), "text/plain")}
    
    upload_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    document_id = upload_response.json()["document_id"]
    
    status_response = await rag_client.get(
        f"/rag/api/v1/documents/{document_id}/status",
        headers=auth_headers_system
    )
    
    assert status_response.status_code == 200
    status_data = status_response.json()
    
    assert {k: status_data[k] for k in ("document_id", "namespace_id", "document_name")} == {
        "document_id": document_id,
        "namespace_id": namespace_id,
        "document_name": "status_test.txt",
    }
    assert {
        "has_task_id": "task_id" in status_data,
        "has_document_name": "document_name" in status_data,
        "status_ok": status_data["status"] in ["pending", "processing", "completed", "failed"],
    } == {"has_task_id": True, "has_document_name": True, "status_ok": True}


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_async_document_processing_completes(rag_client, unique_namespace_name, taskiq_broker, auth_headers_system):
    """Документ успешно обрабатывается через worker и статус меняется на completed"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    content = b"Test document for complete processing flow"
    files = {"file": ("complete_test.txt", BytesIO(content), "text/plain")}
    
    upload_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    document_id = upload_response.json()["document_id"]
    print(f"\n[TEST] Created document_id: {document_id}")
    
    max_wait = 90
    interval = 0.25
    elapsed = 0
    
    while elapsed < max_wait:
        status_response = await rag_client.get(
            f"/rag/api/v1/documents/{document_id}/status",
            headers=auth_headers_system
        )
        status_data = status_response.json()
        print(f"[TEST] Poll {elapsed}s: status={status_data['status']}, doc_id={status_data['document_id']}")
        
        if status_data["status"] == "completed":
            assert {
                "has_s3_key": status_data["s3_key"] is not None,
                "has_s3_bucket": status_data["s3_bucket"] is not None,
                "has_completed_at": status_data["completed_at"] is not None,
            } == {"has_s3_key": True, "has_s3_bucket": True, "has_completed_at": True}
            break
            
        elif status_data["status"] == "failed":
            pytest.fail(f"Document processing failed: {status_data.get('error_message')}")
            
        await asyncio.sleep(interval)
        elapsed += interval
    else:
        pytest.fail(f"Document processing did not complete within {max_wait} seconds")


@pytest.mark.asyncio
async def test_list_documents_includes_processing_status(rag_client, unique_namespace_name, auth_headers_system):
    """GET /documents возвращает и completed и processing документы"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    files = {"file": ("list_test.txt", BytesIO(b"Content"), "text/plain")}
    await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        files=files,
        headers=auth_headers_system
    )
    
    list_response = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system
    )
    
    assert list_response.status_code == 200
    data = list_response.json()
    
    assert {k: k in data for k in ("documents", "summary")} == {"documents": True, "summary": True}
    assert len(data["documents"]) > 0

    rows = [
        {
            "has_document_id": "document_id" in doc,
            "has_name": "name" in doc,
            "status_valid": doc["status"] in ["pending", "processing", "completed", "failed"],
        }
        for doc in data["documents"]
    ]
    assert rows == [
        {"has_document_id": True, "has_name": True, "status_valid": True} for _ in data["documents"]
    ]


@pytest.mark.asyncio
async def test_document_status_not_found(rag_client, auth_headers_system):
    """GET /documents/{id}/status возвращает 404 для несуществующего документа"""
    response = await rag_client.get(
        "/rag/api/v1/documents/nonexistent-document-id/status",
        headers=auth_headers_system
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.real_taskiq
async def test_multiple_documents_processing(rag_client, unique_namespace_name, taskiq_broker, auth_headers_system):
    """Несколько документов могут обрабатываться параллельно"""
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system
    )
    namespace_id = ns_response.json()["name"]
    
    document_ids = []
    for i in range(3):
        files = {"file": (f"multi_test_{i}.txt", BytesIO(f"Content {i}".encode()), "text/plain")}
        response = await rag_client.post(
            f"/rag/api/v1/namespaces/{namespace_id}/documents",
            files=files,
            headers=auth_headers_system
        )
        document_ids.append(response.json()["document_id"])
    
    max_wait = 120
    interval = 0.25
    elapsed = 0
    completed_count = 0
    
    while elapsed < max_wait and completed_count < len(document_ids):
        completed_count = 0
        for doc_id in document_ids:
            status_response = await rag_client.get(
                f"/rag/api/v1/documents/{doc_id}/status",
                headers=auth_headers_system
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
    
    assert completed_count == len(document_ids), f"Only {completed_count}/{len(document_ids)} documents completed"

