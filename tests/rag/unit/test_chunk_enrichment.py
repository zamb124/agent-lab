"""Контракт обогащения чанка (RAG-70): no-op и сериализация в metadata."""

import pytest

from core.rag.services.chunk_enrichment import (
    ChunkEnrichmentContext,
    ChunkEnrichmentResult,
    NoOpChunkEnricher,
)


@pytest.mark.asyncio
async def test_noop_enricher_marks_skipped_and_stable_json_shape():
    """NoOpChunkEnricher не вызывает LLM и возвращает предсказуемый контракт для chunk_enrichment."""
    enricher = NoOpChunkEnricher()
    ctx = ChunkEnrichmentContext(
        namespace_id="ns-1",
        document_id="doc-1",
        document_name="a.txt",
        chunk_index=0,
        total_chunks=3,
        chunk_text="hello",
    )
    result = await enricher.enrich(ctx)
    dumped = result.model_dump(mode="json", exclude_none=True)
    assert {
        "is_result": isinstance(result, ChunkEnrichmentResult),
        "skipped": result.skipped,
        "schema_version": result.schema_version,
        "dumped": dumped,
    } == {
        "is_result": True,
        "skipped": True,
        "schema_version": 1,
        "dumped": {"schema_version": 1, "skipped": True, "extra": {}},
    }
