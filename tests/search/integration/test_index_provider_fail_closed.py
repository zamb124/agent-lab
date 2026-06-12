"""IndexSearchProvider fail-closed integration tests (real RAG + search HTTP)."""

import asyncio
import time

import pytest

from tests.search.conftest import make_search_index_slug

pytestmark = pytest.mark.timeout(120, func_only=True)


async def _poll_index_search_ok(
    search_client,
    *,
    search_index_id: str,
    query: str,
    timeout_seconds: float = 90.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_status = None
    while time.monotonic() < deadline:
        response = await search_client.post(
            "/search/api/v1/search",
            json={
                "query": query,
                "limit": 5,
                "providers": ["index"],
                "index_ids": [search_index_id],
            },
        )
        last_status = response.status_code
        if response.status_code == 200:
            payload = response.json()
            index_status = payload.get("providers", {}).get("index", {})
            if index_status.get("ok") is True and payload.get("results"):
                return payload
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"index search timeout for index={search_index_id!r}, last_status={last_status}"
    )


async def _search_index_once(
    search_client,
    *,
    search_index_id: str,
    query: str,
) -> dict:
    response = await search_client.post(
        "/search/api/v1/search",
        json={
            "query": query,
            "limit": 5,
            "providers": ["index"],
            "index_ids": [search_index_id],
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_index_provider_fail_closed_empty_namespace(
    search_client,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    unique_id,
):
    _ = rag_worker, provider_litserve_service
    search_index_id = make_search_index_slug(unique_id)
    rag_namespace_id = f"{search_index_id}:ns"

    create_index = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"Empty index {unique_id}",
            "rag_namespace_id": rag_namespace_id,
            "rag_collection_id": search_index_id,
        },
    )
    assert create_index.status_code == 201

    namespace_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": rag_namespace_id, "description": "empty namespace test"},
        headers=auth_headers_system,
    )
    assert namespace_response.status_code in {201, 400}

    payload = await _search_index_once(
        search_client,
        search_index_id=search_index_id,
        query=f"empty_namespace_query_{unique_id}",
    )
    index_status = payload["providers"]["index"]
    assert index_status["ok"] is False
    assert index_status["error"] == "index returned no results"
    assert payload["results"] == []


@pytest.mark.asyncio
async def test_index_provider_fail_closed_missing_source_url(
    search_client,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    unique_id,
):
    _ = rag_worker, provider_litserve_service
    search_index_id = make_search_index_slug(unique_id)
    rag_namespace_id = f"{search_index_id}:ns"
    marker = f"no_source_url_marker_{unique_id}"
    doc_text = (
        f"Документ без source_url для fail-closed теста содержит маркер {marker}. "
        "Текст достаточно длинный для chunking и семантического поиска в RAG."
    )

    create_index = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"No source url {unique_id}",
            "rag_namespace_id": rag_namespace_id,
            "rag_collection_id": search_index_id,
        },
    )
    assert create_index.status_code == 201

    ingest = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/ingest-text",
        json={
            "text": doc_text,
            "document_name": "no-source-url.md",
            "metadata": {"collection_id": search_index_id},
        },
        headers=auth_headers_system,
    )
    assert ingest.status_code == 200

    rag_search = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/search",
        json={"query": doc_text, "limit": 3},
        headers=auth_headers_system,
    )
    assert rag_search.status_code == 200
    rag_results = rag_search.json().get("results", [])
    assert rag_results
    assert marker in " ".join(item.get("content", "") for item in rag_results)

    payload = await _search_index_once(
        search_client,
        search_index_id=search_index_id,
        query=doc_text,
    )
    index_status = payload["providers"]["index"]
    assert index_status["ok"] is False
    assert index_status["error"] == "index returned no results"
    assert payload["results"] == []


@pytest.mark.asyncio
async def test_index_provider_ok_with_source_url(
    search_client,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    unique_id,
):
    _ = rag_worker, provider_litserve_service
    search_index_id = make_search_index_slug(unique_id)
    rag_namespace_id = f"{search_index_id}:ns"
    source_url = f"https://integration.test/{unique_id}/fail-closed-ok"
    marker = f"fail_closed_ok_marker_{unique_id}"
    doc_text = (
        f"Документ с source_url для fail-closed ok path содержит маркер {marker}. "
        "Текст достаточно длинный для chunking и семантического поиска в RAG."
    )

    create_index = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"Source url ok {unique_id}",
            "rag_namespace_id": rag_namespace_id,
            "rag_collection_id": search_index_id,
        },
    )
    assert create_index.status_code == 201

    ingest = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/ingest-text",
        json={
            "text": doc_text,
            "document_name": "with-source-url.md",
            "metadata": {
                "source_url": source_url,
                "collection_id": search_index_id,
            },
        },
        headers=auth_headers_system,
    )
    assert ingest.status_code == 200

    payload = await _poll_index_search_ok(
        search_client,
        search_index_id=search_index_id,
        query=doc_text,
    )
    assert payload["providers"]["index"]["ok"] is True
    assert payload["results"]
    assert payload["results"][0]["url"] == source_url
    assert marker in payload["results"][0].get("snippet", "")
