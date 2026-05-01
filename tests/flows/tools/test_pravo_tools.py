"""
Тесты тулов pravo (без реального HTTP/RAG: моки).
"""

from unittest.mock import AsyncMock, patch

import pytest

from apps.flows.tools.pravo import pravo_document_rag_search
from core.clients.pravo import PravoLegislationDocument

H64 = "007c57b8a5c11e0eb8e77ae8e75586909c5a0e5fb9ab0d295b8acc3344ac4ccf"
async def test_pravo_document_rag_search_uses_index_when_results_present() -> None:
    search_payload = {
        "results": [{"content": "фрагмент", "score": 0.9, "document_id": "x"}],
        "query": "срок",
        "namespace_id": "law",
        "provider": "pgvector",
    }
    with patch("apps.flows.tools.pravo.RagClient") as rc:
        inst = rc.return_value
        inst.search = AsyncMock(return_value=search_payload)
        inst.ingest_text = AsyncMock()
        out = await pravo_document_rag_search._func(
            namespace_id="law",
            collection_id="ips_rf",
            document_ref=H64,
            query="срок исковой давности",
            limit=3,
            force_refresh=False,
        )
    assert out["success"] is True
    assert out["document_ingested"] is False
    assert out["pravo_document_hash"] == H64
    inst.search.assert_awaited_once()
    inst.ingest_text.assert_not_called()


@pytest.mark.asyncio
async def test_pravo_document_rag_search_ingests_when_empty_then_searches() -> None:
    final_search = {
        "results": [{"content": "статья 196 ГК РФ", "score": 0.88, "document_id": "z"}],
        "query": "срок",
        "namespace_id": "law",
        "provider": "pgvector",
    }
    doc = PravoLegislationDocument(
        text="Полный текст акта с упоминанием срока.",
        source_url=f"https://ips.pravo.gov.ru/api/ips/legislation/document?baseid=None&hash={H64}",
        document_hash=H64,
        title="Тестовый документ",
    )
    with patch("apps.flows.tools.pravo.RagClient") as rc:
        inst = rc.return_value
        inst.search = AsyncMock(side_effect=[{"results": []}, final_search])
        inst.ingest_text = AsyncMock(return_value={"document_id": "z", "status": "completed"})
        with patch(
            "apps.flows.tools.pravo.fetch_legislation_document",
            new_callable=AsyncMock,
            return_value=doc,
        ):
            out = await pravo_document_rag_search._func(
                namespace_id="law",
                collection_id="ips_rf",
                document_ref=H64,
                query="срок",
                limit=5,
                force_refresh=False,
            )
    assert out["success"] is True
    assert out["document_ingested"] is True
    assert out["results"]
    assert inst.search.await_count == 2
    inst.ingest_text.assert_awaited_once()
