"""index_search flows tool — real SearchClient, real search + RAG stack."""

import pytest

from apps.flows.tools.index_search import index_search
from tests.search.conftest import make_search_index_slug

pytestmark = pytest.mark.timeout(120, func_only=True)


@pytest.mark.asyncio
async def test_index_search_tool_calls_real_search_service(
    search_client,
    rag_client,
    rag_worker,
    provider_litserve_service,
    search_container,
    search_system_context,
    auth_headers_system,
    make_test_state,
    unique_id,
):
    _ = rag_worker, provider_litserve_service
    search_index_id = make_search_index_slug(unique_id)
    rag_namespace_id = f"{search_index_id}:ns"
    marker = f"index_search_tool_marker_{unique_id}"
    doc_text = (
        f"Flows tool index_search integration marker {marker}. "
        "Длинный текст для стабильного RAG chunk и platform index search."
    )

    create_index = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"Tool index {unique_id}",
            "rag_namespace_id": rag_namespace_id,
            "rag_collection_id": search_index_id,
        },
    )
    assert create_index.status_code == 201

    ingest = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/ingest-text",
        json={
            "text": doc_text,
            "document_name": "tool-test.md",
            "metadata": {
                "source_url": f"https://tool.test/{unique_id}",
                "collection_id": search_index_id,
            },
        },
        headers=auth_headers_system,
    )
    assert ingest.status_code == 200

    rag_ready = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/search",
        json={"query": doc_text, "limit": 1},
        headers=auth_headers_system,
    )
    assert rag_ready.status_code == 200
    assert rag_ready.json().get("results")

    payload = await index_search.run(
        {"query": doc_text, "search_index_ids": [search_index_id], "limit": 5},
        make_test_state(),
    )

    assert payload["success"] is True
    response = payload["response"]
    assert response["query"] == doc_text
    assert response["providers"]["index"]["ok"] is True
    assert response["results"]
    assert response["results"][0]["search_index_id"] == search_index_id
    assert marker in response["results"][0].get("snippet", "")


@pytest.mark.asyncio
async def test_index_search_tool_fail_closed_empty_index(
    search_client,
    rag_client,
    rag_worker,
    provider_litserve_service,
    search_system_context,
    make_test_state,
    auth_headers_system,
    unique_id,
):
    _ = rag_worker, provider_litserve_service, search_system_context
    search_index_id = make_search_index_slug(unique_id)
    rag_namespace_id = f"{search_index_id}:ns"

    create_index = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"Empty tool index {unique_id}",
            "rag_namespace_id": rag_namespace_id,
            "rag_collection_id": search_index_id,
        },
    )
    assert create_index.status_code == 201

    namespace_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": rag_namespace_id, "description": "empty tool index"},
        headers=auth_headers_system,
    )
    assert namespace_response.status_code in {201, 400}

    payload = await index_search.run(
        {
            "query": f"empty_tool_index_query_{unique_id}",
            "search_index_ids": [search_index_id],
            "limit": 5,
        },
        make_test_state(),
    )

    assert payload["success"] is True
    response = payload["response"]
    assert response["providers"]["index"]["ok"] is False
    assert response["providers"]["index"]["error"] == "index returned no results"
    assert response["results"] == []
