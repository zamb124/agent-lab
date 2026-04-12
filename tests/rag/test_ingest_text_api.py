"""
Тесты POST .../ingest-text и связки ingest-text + search.
"""

import pytest


@pytest.mark.asyncio
async def test_ingest_text_sync(rag_client, unique_namespace_name, auth_headers_system):
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    assert ns_response.status_code == 201
    namespace_id = ns_response.json()["name"]

    body = {
        "text": "Уникальный фрагмент для RAG ingest-text: alpha-beta-gamma-delta-epsilon-zeta.",
        "document_name": "note.txt",
        "metadata": {"source": "test"},
    }
    response = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/ingest-text",
        json=body,
        headers=auth_headers_system,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["namespace_id"] == namespace_id
    assert data["status"] == "completed"
    assert "document_id" in data
    assert data["document_name"] == "note.txt"


@pytest.mark.asyncio
async def test_ingest_text_then_search(rag_client, unique_namespace_name, auth_headers_system):
    ns_response = await rag_client.post(
        "/rag/api/v1/namespaces",
        json={"name": unique_namespace_name},
        headers=auth_headers_system,
    )
    namespace_id = ns_response.json()["name"]

    phrase = "ingest_text_search_marker_quartz_42"
    doc_text = f"Документ содержит маркер {phrase} для семантического поиска."
    ingest = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/ingest-text",
        json={"text": doc_text, "document_name": "marker.md"},
        headers=auth_headers_system,
    )
    assert ingest.status_code == 200

    listed = await rag_client.get(
        f"/rag/api/v1/namespaces/{namespace_id}/documents",
        headers=auth_headers_system,
    )
    assert listed.status_code == 200
    doc_names = [d.get("name") for d in listed.json().get("items", [])]
    assert "marker.md" in doc_names

    # Запрос совпадает с проиндексированным текстом чанка — при моке embeddings тот же вектор, топ-1 стабилен.
    search = await rag_client.post(
        f"/rag/api/v1/namespaces/{namespace_id}/search",
        json={"query": doc_text, "limit": 5},
        headers=auth_headers_system,
    )
    assert search.status_code == 200
    results = search.json().get("results", [])
    assert len(results) >= 1
    joined = " ".join(r.get("content", "") for r in results)
    assert phrase in joined


@pytest.mark.asyncio
async def test_ingest_text_unknown_namespace_returns_404(rag_client, auth_headers_system):
    response = await rag_client.post(
        "/rag/api/v1/namespaces/absolutely_missing_namespace_xyz_ingest/ingest-text",
        json={"text": "x"},
        headers=auth_headers_system,
    )
    assert response.status_code == 404
