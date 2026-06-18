"""Index search provider dedup unit tests."""

import pytest

from apps.search.providers.index import _dedupe_rag_results, _rag_document_dedup_key
from core.rag.models import RAGSearchResult

pytestmark = pytest.mark.unit


def _rag_result(
    *,
    document_id: str,
    source_url: str,
    canonical_url: str | None,
    score: float,
    content: str,
) -> RAGSearchResult:
    metadata = {"source_url": source_url}
    if canonical_url is not None:
        metadata["canonical_url"] = canonical_url
    return RAGSearchResult(
        chunk_id=f"chunk:{document_id}:{score}",
        document_id=document_id,
        document_name=f"Doc {document_id}",
        namespace="runet:platform",
        content=content,
        score=score,
        metadata=metadata,
    )


def test_rag_document_dedup_key_prefers_canonical_url() -> None:
    rag_result = _rag_result(
        document_id="doc-1",
        source_url="https://example.com/a?utm=1",
        canonical_url="https://example.com/a",
        score=0.9,
        content="chunk a",
    )
    assert _rag_document_dedup_key(rag_result) == "https://example.com/a"


def test_dedupe_rag_results_keeps_best_score_per_document() -> None:
    ranked = _dedupe_rag_results(
        [
            _rag_result(
                document_id="doc-1",
                source_url="https://example.com/page",
                canonical_url="https://example.com/page",
                score=0.4,
                content="low",
            ),
            _rag_result(
                document_id="doc-1",
                source_url="https://example.com/page#section",
                canonical_url="https://example.com/page",
                score=0.9,
                content="high",
            ),
            _rag_result(
                document_id="doc-2",
                source_url="https://example.com/other",
                canonical_url="https://example.com/other",
                score=0.7,
                content="other",
            ),
        ]
    )
    assert len(ranked) == 2
    assert ranked[0].score == 0.9
    assert ranked[0].content == "high"
    assert ranked[1].document_id == "doc-2"
