"""index-file + rag_worker + search: typed RAGSearchResult на golden FileExtract."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.rag.models import RAGSearchResult
from tests.core.files.golden.bytes import (
    docx_heading_table_list_png,
    marker,
    pdf_scanned_raster,
    txt_bytes,
)
from tests.rag.helpers import upload_rag_document_bytes, wait_rag_document_status

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.real_taskiq,
    pytest.mark.timeout(180),
    pytest.mark.usefixtures("file_reader_billing_service"),
]

_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def _wait_completed(
    rag_client: AsyncClient,
    document_id: str,
    headers: dict[str, str],
) -> None:
    payload = await wait_rag_document_status(rag_client, document_id, headers)
    if payload["status"] != "completed":
        pytest.fail(f"index-file {document_id}: {payload}")


async def _search_hits(
    rag_client: AsyncClient,
    *,
    namespace_id: str,
    query: str,
    headers: dict[str, str],
) -> list[RAGSearchResult]:
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={"query": query, "limit": 10},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    hits: list[RAGSearchResult] = []
    for item in body["results"]:
        assert "metadata" not in item
        assert "indexing_runtime" not in item
        hit = RAGSearchResult.model_validate(item)
        assert "indexing_runtime" not in hit.attributes
        hits.append(hit)
    return hits


async def _index_golden(
    rag_client: AsyncClient,
    headers: dict[str, str],
    *,
    namespace_id: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> str:
    payload = await upload_rag_document_bytes(
        rag_client,
        headers,
        namespace_id=namespace_id,
        filename=filename,
        content=content,
        content_type=content_type,
    )
    document_id = payload["document_id"]
    await _wait_completed(rag_client, document_id, headers)
    return document_id


async def test_index_file_txt_search_typed_result(
    rag_client: AsyncClient,
    rag_worker,
    unique_namespace_name: str,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    _ = rag_worker
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    assert ns_response.status_code == 201
    namespace_id = ns_response.json()["name"]
    token = marker("GOLDEN_TXT", unique_id)
    document_id = await _index_golden(
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename=f"golden_txt_{unique_id}.txt",
        content=txt_bytes(unique_id),
        content_type="text/plain",
    )
    hits = await _search_hits(
        rag_client,
        namespace_id=namespace_id,
        query=token,
        headers=auth_headers_system,
    )
    matching = [hit for hit in hits if token in hit.content]
    assert matching
    hit = matching[0]
    assert hit.document_id == document_id
    assert isinstance(hit.page_index, int)
    assert isinstance(hit.page_label, str)
    assert hit.split.strategy


async def test_index_file_docx_image_heading_trail_and_files(
    rag_client: AsyncClient,
    rag_worker,
    unique_namespace_name: str,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    _ = rag_worker
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    assert ns_response.status_code == 201
    namespace_id = ns_response.json()["name"]
    token = marker("GOLDEN_DOCX", unique_id)
    document_id = await _index_golden(
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename=f"golden_docx_{unique_id}.docx",
        content=docx_heading_table_list_png(unique_id),
        content_type=_DOCX_TYPE,
    )
    hits = await _search_hits(
        rag_client,
        namespace_id=namespace_id,
        query=token,
        headers=auth_headers_system,
    )
    matching = [hit for hit in hits if token in hit.content]
    assert matching
    assert any(hit.document_id == document_id for hit in matching)
    assert any(hit.heading_trail for hit in matching)
    assert any(hit.files for hit in matching)
    for hit in matching:
        assert hit.split.strategy
        assert "metadata" not in hit.model_dump()


async def test_index_file_scanned_pdf_hybrid_search(
    rag_client: AsyncClient,
    rag_worker,
    unique_namespace_name: str,
    unique_id: str,
    auth_headers_system: dict[str, str],
    mock_llm_redis,
) -> None:
    _ = rag_worker
    await mock_llm_redis([{"type": "text", "content": "MOCK_VISION"}] * 5)
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    assert ns_response.status_code == 201
    namespace_id = ns_response.json()["name"]
    document_id = await _index_golden(
        rag_client,
        auth_headers_system,
        namespace_id=namespace_id,
        filename=f"golden_scan_{unique_id}.pdf",
        content=pdf_scanned_raster(unique_id),
        content_type="application/pdf",
    )
    hits = await _search_hits(
        rag_client,
        namespace_id=namespace_id,
        query="MOCK_VISION",
        headers=auth_headers_system,
    )
    matching = [
        hit
        for hit in hits
        if hit.document_id == document_id and "MOCK_VISION" in hit.content
    ]
    assert matching
    hit = matching[0]
    assert hit.page_index == 0
    assert hit.page_label == "page_1"
    assert hit.files
    assert hit.split.strategy
