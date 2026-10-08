"""Поиск по НПА: живой RAG и, если чанков нет, загрузка текста из IPS."""

from __future__ import annotations

import pytest

from apps.flows.tools.knowledge.pravo import pravo_document_rag_search
from core.clients.pravo import PravoClient
from core.clients.rag_client import RagClient

H64 = "007c57b8a5c11e0eb8e77ae8e75586909c5a0e5fb9ab0d295b8acc3344ac4ccf"


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_pravo_document_rag_search_uses_index_when_results_present(
    rag_service: object,
    unique_id: str,
) -> None:
    _ = rag_service
    namespace_id = f"pravo_hit_{unique_id}"
    collection_id = f"ips_{unique_id}"
    marker = f"PRAVO_HIT_{unique_id}"
    rag_document_id = PravoClient.rag_document_id(H64)
    client = RagClient()
    _ = await client.create_namespace(namespace_id, "pravo hit")
    _ = await client.ingest_text(
        namespace_id,
        f"фрагмент {marker}",
        document_name="act",
        document_id=rag_document_id,
        metadata={
            "collection_id": collection_id,
            "document_id": rag_document_id,
        },
    )

    out = await pravo_document_rag_search._func(
        namespace_id=namespace_id,
        collection_id=collection_id,
        document_ref=H64,
        query=marker,
        limit=3,
        force_refresh=False,
    )

    assert out["document_ingested"] is False
    assert out["pravo_document_hash"] == H64
    assert out["documents"][0]["indexed_into_rag_this_call"] is False
    results = out["results"]
    assert isinstance(results, list) and results
    assert any(marker in str(item.get("content")) for item in results if isinstance(item, dict))


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_pravo_document_rag_search_ingests_when_empty_then_searches(
    rag_service: object,
    unique_id: str,
) -> None:
    _ = rag_service
    namespace_id = f"pravo_miss_{unique_id}"
    client = RagClient()
    _ = await client.create_namespace(namespace_id, "pravo miss")

    out = await pravo_document_rag_search._func(
        namespace_id=namespace_id,
        collection_id=f"ips_{unique_id}",
        document_ref=H64,
        query="статья",
        limit=3,
        force_refresh=False,
    )

    assert out["document_ingested"] is True
    assert out["pravo_document_hash"] == H64
    documents = out["documents"]
    assert isinstance(documents, list) and len(documents) == 1
    assert documents[0]["indexed_into_rag_this_call"] is True
    text_character_count = documents[0]["text_character_count"]
    assert isinstance(text_character_count, int) and text_character_count > 0
    results = out["results"]
    assert isinstance(results, list) and results
