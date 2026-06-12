"""Strict integration tests for platform index search (real Postgres, Redis, RAG, HTTP)."""

import asyncio
import time

import pytest

from tests.search.conftest import make_search_index_slug

pytestmark = pytest.mark.timeout(120, func_only=True)


async def _poll_index_search(
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


@pytest.mark.asyncio
async def test_search_indexes_registry_crud(search_client, unique_id):
    search_index_id = make_search_index_slug(unique_id)
    rag_namespace_id = f"{search_index_id}:ns"

    create_response = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"Test Index {unique_id}",
            "description": "integration test index",
            "rag_namespace_id": rag_namespace_id,
            "rag_collection_id": search_index_id,
            "search_enabled": True,
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["search_index_id"] == search_index_id
    assert created["rag_namespace_id"] == rag_namespace_id
    assert created["company_id"] == "system"

    get_response = await search_client.get(f"/search/api/v1/search-indexes/{search_index_id}")
    assert get_response.status_code == 200
    assert get_response.json()["display_name"] == f"Test Index {unique_id}"

    batch_response = await search_client.post(
        "/search/api/v1/search-indexes/batch-get",
        json={"search_index_ids": [search_index_id]},
    )
    assert batch_response.status_code == 200
    batch_items = batch_response.json()
    assert len(batch_items) == 1
    assert batch_items[0]["search_index_id"] == search_index_id

    patch_response = await search_client.patch(
        f"/search/api/v1/search-indexes/{search_index_id}",
        json={"description": "patched description"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["description"] == "patched description"


@pytest.mark.asyncio
async def test_index_search_finds_rag_content_with_source_url(
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
    source_url = f"https://integration.test/{unique_id}/page"
    marker = f"platform_index_marker_{unique_id}"
    doc_text = (
        f"Документ для platform index search содержит уникальный маркер {marker}. "
        "Текст достаточно длинный для chunking и семантического поиска в RAG."
    )

    create_index = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"Index {unique_id}",
            "rag_namespace_id": rag_namespace_id,
            "rag_collection_id": search_index_id,
        },
    )
    assert create_index.status_code == 201

    ingest = await rag_client.post(
        f"/rag/api/v1/namespaces/{rag_namespace_id}/ingest-text",
        json={
            "text": doc_text,
            "document_name": "integration.md",
            "metadata": {
                "source_url": source_url,
                "collection_id": search_index_id,
            },
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

    search_payload = await _poll_index_search(
        search_client,
        search_index_id=search_index_id,
        query=doc_text,
    )
    assert search_payload["providers"]["index"]["ok"] is True
    assert search_payload["results"]
    top = search_payload["results"][0]
    assert top["search_index_id"] == search_index_id
    assert top["source_type"] == "platform_index"
    assert top["url"] == source_url
    assert marker in top.get("snippet", "")


@pytest.mark.asyncio
async def test_search_providers_snapshot_includes_runet_seed(search_client):
    response = await search_client.get("/search/api/v1/providers")
    assert response.status_code == 200
    payload = response.json()
    assert payload["index_enabled"] is True
    assert "runet" in payload["default_index_ids"]

    runet_index = await search_client.get("/search/api/v1/search-indexes/runet")
    assert runet_index.status_code == 200
    runet_payload = runet_index.json()
    assert runet_payload["search_index_id"] == "runet"
    assert runet_payload["rag_namespace_id"] == "runet:platform"
    assert runet_payload["search_enabled"] is True


@pytest.mark.asyncio
async def test_meta_search_runet_alias_resolves_to_index_provider(
    search_client,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    unique_id,
):
    _ = rag_worker, provider_litserve_service
    marker = f"runet_alias_marker_{unique_id}"
    doc_text = f"Runet alias test document with marker {marker} for index provider resolution."

    namespace_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": "runet:platform", "description": "runet platform index"},
        headers=auth_headers_system,
    )
    assert namespace_response.status_code in {201, 400}

    ingest = await rag_client.post(
        "/rag/api/v1/namespaces/runet:platform/ingest-text",
        json={
            "text": doc_text,
            "document_name": f"runet-alias-{unique_id}.md",
            "metadata": {
                "source_url": f"https://runet-alias.test/{unique_id}",
                "collection_id": "runet",
            },
        },
        headers=auth_headers_system,
    )
    assert ingest.status_code == 200

    payload = await _poll_index_search(
        search_client,
        search_index_id="runet",
        query=doc_text,
    )
    assert payload["providers"]["index"]["ok"] is True
    assert any(marker in item.get("snippet", "") for item in payload["results"])

    alias_response = await search_client.post(
        "/search/api/v1/search",
        json={
            "query": doc_text,
            "limit": 5,
            "providers": ["runet"],
        },
    )
    assert alias_response.status_code == 200
    alias_payload = alias_response.json()
    assert alias_payload["providers"]["index"]["ok"] is True
    assert any(marker in item.get("snippet", "") for item in alias_payload["results"])


@pytest.mark.asyncio
async def test_runet_only_does_not_fallback_to_serp(
    search_client,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    unique_id,
):
    _ = rag_worker, provider_litserve_service
    namespace_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": "runet:platform", "description": "runet platform index"},
        headers=auth_headers_system,
    )
    assert namespace_response.status_code in {201, 400}

    response = await search_client.post(
        "/search/api/v1/search",
        json={
            "query": f"runet_only_empty_query_{unique_id}",
            "limit": 5,
            "providers": ["runet"],
            "provider_strategy": "first_available",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert set(payload["providers"].keys()) == {"index"}
    assert "tavily" not in payload["providers"]
    assert "serper" not in payload["providers"]
    index_status = payload["providers"]["index"]
    if not payload["results"]:
        assert index_status["ok"] is False
        assert index_status["error"] == "index returned no results"
    assert payload["results"] == [] or index_status["ok"] is True


@pytest.mark.asyncio
async def test_auto_falls_back_when_index_empty(
    search_client,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    unique_id,
    monkeypatch,
):
    from apps.search.config import reset_search_settings
    from apps.search.container import reset_search_container

    _ = rag_worker, provider_litserve_service
    search_index_id = make_search_index_slug(f"auto_{unique_id}")
    rag_namespace_id = f"{search_index_id}:ns"

    create_index = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"Auto fallback empty {unique_id}",
            "rag_namespace_id": rag_namespace_id,
            "rag_collection_id": search_index_id,
        },
    )
    assert create_index.status_code == 201

    namespace_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": rag_namespace_id, "description": "auto fallback empty index"},
        headers=auth_headers_system,
    )
    assert namespace_response.status_code in {201, 400}

    monkeypatch.setenv("SEARCH__INDEX__DEFAULT_INDEX_IDS", f'["{search_index_id}"]')
    reset_search_settings()
    reset_search_container()

    response = await search_client.post(
        "/search/api/v1/search",
        json={
            "query": f"Tavily Search API official documentation {unique_id}",
            "limit": 5,
            "providers": ["auto"],
            "provider_strategy": "first_available",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    index_status = payload["providers"]["index"]
    assert index_status["ok"] is False
    assert index_status["error"] == "index returned no results"
    serp_provider_ids = ("tinyfish", "linkup", "serper", "tavily")
    assert any(payload["providers"][provider_id]["ok"] is True for provider_id in serp_provider_ids)
    assert payload["results"]


@pytest.mark.asyncio
async def test_empty_index_does_not_mark_index_unavailable_in_redis(
    search_client,
    rag_client,
    rag_worker,
    provider_litserve_service,
    auth_headers_system,
    unique_id,
):
    _ = rag_worker, provider_litserve_service
    search_index_id = make_search_index_slug(f"empty_avail_{unique_id}")
    rag_namespace_id = f"{search_index_id}:ns"

    create_index = await search_client.post(
        "/search/api/v1/search-indexes",
        json={
            "search_index_id": search_index_id,
            "display_name": f"Empty availability {unique_id}",
            "rag_namespace_id": rag_namespace_id,
            "rag_collection_id": search_index_id,
        },
    )
    assert create_index.status_code == 201

    namespace_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": rag_namespace_id, "description": "empty index availability test"},
        headers=auth_headers_system,
    )
    assert namespace_response.status_code in {201, 400}

    query = f"empty_index_availability_{unique_id}"
    search_payload = {
        "query": query,
        "limit": 5,
        "providers": ["index"],
        "index_ids": [search_index_id],
        "provider_strategy": "first_available",
    }

    first = await search_client.post("/search/api/v1/search", json=search_payload)
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["providers"]["index"]["ok"] is False
    assert first_payload["providers"]["index"]["error"] == "index returned no results"
    assert first_payload["providers"]["index"].get("skipped") is not True

    second = await search_client.post("/search/api/v1/search", json=search_payload)
    assert second.status_code == 200
    second_payload = second.json()
    index_status = second_payload["providers"]["index"]
    assert index_status["ok"] is False
    assert index_status["error"] == "index returned no results"
    assert index_status.get("skipped") is not True
    assert index_status.get("skip_reason") != "provider marked unavailable in redis"
