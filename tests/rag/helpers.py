"""Helpers для RAG API-тестов: chunked Files API на rag + index-file."""

from __future__ import annotations

import asyncio
from typing import Any

from httpx import AsyncClient

from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from tests.files.chunked_upload_helpers import chunked_upload_file

RAG_FILES_API_PREFIX = "/rag/api/v1/files"


def rag_document_upload_spec_json(namespace_id: str) -> str:
    spec = FileCreateSpec(
        source_kind=FileSourceKind.RAG_DOCUMENT,
        source_ref=FileSourceRef(namespace_id=namespace_id),
        retention=default_retention_for_source(FileSourceKind.RAG_DOCUMENT),
    )
    return spec.model_dump_json()


async def upload_rag_document_bytes(
    rag_client: AsyncClient,
    headers: dict[str, str],
    *,
    namespace_id: str,
    filename: str,
    content: bytes,
    content_type: str = "text/plain",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Загружает байты через chunked Files API на rag и ставит документ в очередь index-file."""
    upload_response = await chunked_upload_file(
        rag_client,
        headers,
        content=content,
        original_name=filename,
        content_type=content_type,
        spec_json=rag_document_upload_spec_json(namespace_id),
        files_api_prefix=RAG_FILES_API_PREFIX,
    )
    if upload_response.status_code != 200:
        raise AssertionError(
            f"RAG file upload failed: {upload_response.status_code} {upload_response.text}"
        )
    file_payload = upload_response.json()
    file_id = file_payload["file_id"]

    index_body: dict[str, Any] = {"file_id": file_id}
    if metadata is not None:
        index_body["metadata"] = metadata

    index_response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/documents/index-file",
        json=index_body,
        headers=headers,
    )
    if index_response.status_code != 202:
        raise AssertionError(
            f"RAG index-file failed: {index_response.status_code} {index_response.text}"
        )
    payload = index_response.json()
    payload["file"] = file_payload
    return payload


async def wait_rag_document_status(
    rag_client: AsyncClient,
    document_id: str,
    headers: dict[str, str],
    *,
    max_wait: float = 90.0,
    interval: float = 0.25,
) -> dict[str, Any]:
    elapsed = 0.0
    while elapsed < max_wait:
        status_response = await rag_client.get(
            f"/rag/api/v1/documents/{document_id}/status",
            headers=headers,
        )
        if status_response.status_code != 200:
            raise AssertionError(
                f"RAG status failed: {status_response.status_code} {status_response.text}"
            )
        payload = status_response.json()
        status = payload.get("status")
        if status in ("ready", "failed", "error"):
            return payload
        await asyncio.sleep(interval)
        elapsed += interval
    raise AssertionError(f"RAG document {document_id} status timeout after {max_wait}s")
