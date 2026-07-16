"""Invariant: vector_pointer search ignores content for snippet."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.search.providers.index import IndexSearchProvider, _build_snippet
from core.rag.models import RAGSearchResult
from core.search.index_models import SearchIndexDefinition, SearchIndexRetrievalConfig


def test_vector_pointer_snippet_uses_metadata_not_content() -> None:
    rag_result = RAGSearchResult(
        chunk_id="c1",
        document_id="runet:doc1",
        document_name="Page title",
        content="SECRET CONTENT THAT MUST NOT APPEAR IN SNIPPET",
        score=0.95,
        namespace="runet",
        metadata={
            "doc_type": "vector_pointer",
            "source_url": "https://habr.com/ru/articles/1",
            "section_title": "Деплой Kubernetes",
            "salient_terms": ["ingress", "nginx", "tls"],
            "meta_description": "Краткое описание страницы",
        },
    )
    snippet = _build_snippet(rag_result, snippet_limit=300, is_pointer=True)
    assert "SECRET CONTENT" not in snippet
    assert "Деплой Kubernetes" in snippet
    assert "ingress" in snippet


def test_chunk_mirror_snippet_uses_content() -> None:
    rag_result = RAGSearchResult(
        chunk_id="c1",
        document_id="runet:doc1",
        document_name="Page title",
        content="VISIBLE CHUNK TEXT",
        score=0.5,
        namespace="runet",
        metadata={"source_url": "https://habr.com/ru/articles/1"},
    )
    snippet = _build_snippet(rag_result, snippet_limit=100, is_pointer=False)
    assert snippet == "VISIBLE CHUNK TEXT"


def test_map_result_sets_doc_type_vector_pointer() -> None:
    provider = IndexSearchProvider(
        config=type("Cfg", (), {"enabled": True, "max_indexes_per_request": 3, "registry_cache_ttl_seconds": 0})(),  # type: ignore[arg-type]
        search_index_repository=type("Repo", (), {})(),  # type: ignore[arg-type]
        rag_client=type("Rag", (), {})(),  # type: ignore[arg-type]
        build_system_context=lambda _trace: None,  # type: ignore[arg-type]
    )
    definition = SearchIndexDefinition(
        search_index_id="runet",
        company_id="system",
        display_name="Runet",
        rag_namespace_id="runet",
        rag_collection_id="default",
        enabled=True,
        search_enabled=True,
        retrieval=SearchIndexRetrievalConfig(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mapped = provider._map_result(
        RAGSearchResult(
            chunk_id="c1",
            document_id="runet:doc1",
            document_name="HTML title",
            content=".",
            score=0.5,
            namespace="runet",
            metadata={
                "doc_type": "vector_pointer",
                "source_url": "https://habr.com/ru/articles/1",
                "html_title": "HTML title",
                "salient_terms": ["k8s"],
            },
        ),
        definition=definition,
        provider_rank=1,
    )
    assert mapped is not None
    assert mapped.doc_type == "vector_pointer"
    assert mapped.salient_terms == ["k8s"]
    assert "k8s" in mapped.snippet
