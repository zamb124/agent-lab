"""RAG index-file API: индексация существующего FileRecord без повторной загрузки в S3."""

from __future__ import annotations

import asyncio
import hashlib
import io

import pytest

from apps.rag.container import get_rag_container
from tests.rag.helpers import upload_rag_document_bytes
from core.files.create_spec import FileSourceKind
from core.files.default_storage import get_default_storage
from core.files.models import FileRecord
from core.files.registry import default_retention_for_source
from core.files.s3_client import S3ClientFactory
from core.files.storage import retention_fields_from_spec

pytestmark = [pytest.mark.real_taskiq, pytest.mark.timeout(120)]


async def _persist_test_file_record(
    *,
    data: bytes,
    original_name: str,
    content_type: str,
    uploaded_by: str,
    company_id: str,
) -> FileRecord:
    retention = default_retention_for_source(FileSourceKind.RAG_DOCUMENT)
    retention_kind, ttl_seconds = retention_fields_from_spec(retention)
    storage = get_default_storage()
    return await storage.upload_bytes(
        data=data,
        original_name=original_name,
        content_type=content_type,
        uploaded_by=uploaded_by,
        company_id=company_id,
        is_public=False,
        retention_kind=retention_kind,
        ttl_seconds=ttl_seconds,
        metadata={"source_kind": FileSourceKind.RAG_DOCUMENT.value},
    )


async def _wait_rag_document_completed(
    rag_client,
    document_id: str,
    headers: dict[str, str],
    *,
    max_wait: float = 90.0,
) -> dict[str, object]:
    interval = 0.25
    elapsed = 0.0
    while elapsed < max_wait:
        status_response = await rag_client.get(
            f"/rag/api/v1/documents/{document_id}/status",
            headers=headers,
        )
        assert status_response.status_code == 200
        status_data = status_response.json()
        if status_data["status"] == "completed":
            return status_data
        if status_data["status"] == "failed":
            pytest.fail(status_data.get("error_message"))
        await asyncio.sleep(interval)
        elapsed += interval
    pytest.fail(f"index-file did not complete within {max_wait}s")


@pytest.mark.asyncio
async def test_index_file_returns_202_without_new_s3_object(
    rag_client,
    rag_worker,
    unique_namespace_name,
    auth_headers_system,
):
    _ = rag_worker
    container = get_rag_container()
    file_record = await _persist_test_file_record(
        data=b"Office catalog document body",
        original_name="catalog_doc.txt",
        content_type="text/plain",
        uploaded_by="system_admin",
        company_id="system",
    )

    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    assert ns_response.status_code == 201
    namespace_id = ns_response.json()["name"]

    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/index-file",
        json={
            "file_id": file_record.file_id,
            "metadata": {
                "source": "office",
                "ttl_seconds": 0,
            },
        },
        headers=auth_headers_system,
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload == {
        "document_id": file_record.file_id,
        "file_id": file_record.file_id,
        "status": "pending",
        "task_id": payload["task_id"],
    }
    assert payload["task_id"]

    still_there = await container.file_repository.get(file_record.file_id)
    assert still_there is not None
    assert still_there.s3_key == file_record.s3_key
    assert still_there.file_size == file_record.file_size


@pytest.mark.asyncio
async def test_index_file_processing_completes_and_searchable(
    rag_client,
    rag_worker,
    unique_namespace_name,
    auth_headers_system,
):
    _ = rag_worker
    needle = "index-file-worker-flow-needle"
    file_record = await _persist_test_file_record(
        data=f"Complete index-file worker flow {needle}".encode(),
        original_name="worker_flow.txt",
        content_type="text/plain",
        uploaded_by="system_admin",
        company_id="system",
    )

    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    upload_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/index-file",
        json={"file_id": file_record.file_id, "metadata": {"ttl_seconds": 0}},
        headers=auth_headers_system,
    )
    assert upload_response.status_code == 202
    document_id = upload_response.json()["document_id"]

    status_data = await _wait_rag_document_completed(
        rag_client,
        document_id,
        auth_headers_system,
    )
    assert status_data["document_id"] == file_record.file_id
    assert status_data["status"] == "completed"
    assert status_data["completed_at"] is not None

    search_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={"query": needle, "limit": 5},
        headers=auth_headers_system,
    )
    assert search_response.status_code == 200
    results = search_response.json()["results"]
    document_ids = {item.get("document_id") for item in results}
    assert file_record.file_id in document_ids


@pytest.mark.asyncio
async def test_index_only_delete_preserves_file_record(
    rag_client,
    rag_worker,
    unique_namespace_name,
    auth_headers_system,
):
    _ = rag_worker
    container = get_rag_container()
    file_record = await _persist_test_file_record(
        data=b"Index delete preserves bytes",
        original_name="preserve_me.txt",
        content_type="text/plain",
        uploaded_by="system_admin",
        company_id="system",
    )

    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    index_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/index-file",
        json={"file_id": file_record.file_id, "metadata": {"ttl_seconds": 0}},
        headers=auth_headers_system,
    )
    assert index_response.status_code == 202
    document_id = index_response.json()["document_id"]
    await _wait_rag_document_completed(rag_client, document_id, auth_headers_system)

    delete_response = await rag_client.delete(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/{document_id}/index",
        headers=auth_headers_system,
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["success"] is True

    still_there = await container.file_repository.get(file_record.file_id)
    assert still_there is not None
    assert still_there.s3_key == file_record.s3_key

    status_response = await rag_client.get(
        f"/rag/api/v1/documents/{document_id}/status",
        headers=auth_headers_system,
    )
    assert status_response.status_code == 404


@pytest.mark.asyncio
async def test_index_file_reindex_replaces_chunks(
    rag_client,
    rag_worker,
    unique_namespace_name,
    auth_headers_system,
):
    _ = rag_worker
    container = get_rag_container()
    first_body = b"first version of indexed text"
    file_record = await _persist_test_file_record(
        data=first_body,
        original_name="reindex.txt",
        content_type="text/plain",
        uploaded_by="system_admin",
        company_id="system",
    )

    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    first_index = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/index-file",
        json={"file_id": file_record.file_id, "metadata": {"ttl_seconds": 0}},
        headers=auth_headers_system,
    )
    assert first_index.status_code == 202
    document_id = first_index.json()["document_id"]
    await _wait_rag_document_completed(rag_client, document_id, auth_headers_system)

    second_body = b"second version replaces chunks in vector index"
    updated = file_record.model_copy(
        update={
            "file_size": len(second_body),
        },
    )
    s3_client = S3ClientFactory.create_client_for_bucket(updated.s3_bucket)
    try:
        _ = await s3_client.upload_bytes(
            data=second_body,
            key=updated.s3_key,
            content_type=updated.content_type or "text/plain",
            public=updated.is_public,
        )
    finally:
        await s3_client.close()

    persisted = updated.model_copy(update={"checksum": hashlib.sha256(second_body).hexdigest()})
    _ = await container.file_repository.set(persisted)

    second_index = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/index-file",
        json={"file_id": file_record.file_id, "metadata": {"ttl_seconds": 0}},
        headers=auth_headers_system,
    )
    assert second_index.status_code == 202
    await _wait_rag_document_completed(rag_client, document_id, auth_headers_system)

    search_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={"query": "second version replaces chunks", "limit": 5},
        headers=auth_headers_system,
    )
    assert search_response.status_code == 200
    results = search_response.json()["results"]
    assert results
    assert results[0]["document_id"] == file_record.file_id


@pytest.mark.asyncio
async def test_index_file_rejects_foreign_company_file(
    rag_client,
    rag_worker,
    unique_namespace_name,
    auth_headers_system,
):
    _ = rag_worker
    file_record = await _persist_test_file_record(
        data=b"foreign",
        original_name="foreign.txt",
        content_type="text/plain",
        uploaded_by="system_admin",
        company_id="other-company-id",
    )

    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/index-file",
        json={"file_id": file_record.file_id, "metadata": {"ttl_seconds": 0}},
        headers=auth_headers_system,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_full_delete_document_removes_file_record_but_index_only_does_not(
    frontend_client,
    rag_client,
    rag_worker,
    unique_namespace_name,
    auth_headers_system,
):
    _ = rag_worker
    container = get_rag_container()
    file_record = await _persist_test_file_record(
        data=b"compare delete modes",
        original_name="delete_modes.txt",
        content_type="text/plain",
        uploaded_by="system_admin",
        company_id="system",
    )

    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    index_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/index-file",
        json={"file_id": file_record.file_id, "metadata": {"ttl_seconds": 0}},
        headers=auth_headers_system,
    )
    document_id = index_response.json()["document_id"]
    await _wait_rag_document_completed(rag_client, document_id, auth_headers_system)

    index_only_delete = await rag_client.delete(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/{document_id}/index",
        headers=auth_headers_system,
    )
    assert index_only_delete.status_code == 200
    preserved = await container.file_repository.get(file_record.file_id)
    assert preserved is not None

    reindex = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/index-file",
        json={"file_id": file_record.file_id, "metadata": {"ttl_seconds": 0}},
        headers=auth_headers_system,
    )
    assert reindex.status_code == 202
    await _wait_rag_document_completed(rag_client, reindex.json()["document_id"], auth_headers_system)

    rag_owned = await upload_rag_document_bytes(
        frontend_client,
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename="other.txt",
        content=b"other",
        content_type="text/plain",
    )
    rag_owned_document_id = rag_owned["document_id"]

    full_delete = await rag_client.delete(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/{rag_owned_document_id}",
        headers=auth_headers_system,
    )
    assert full_delete.status_code == 200

    removed = await container.file_repository.get(rag_owned_document_id)
    assert removed is None

    peer_still_there = await container.file_repository.get(file_record.file_id)
    assert peer_still_there is not None
