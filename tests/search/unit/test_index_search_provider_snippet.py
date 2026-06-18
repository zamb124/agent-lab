from __future__ import annotations

from apps.search.providers.index import (
    _resolve_index_snippet,
    _resolve_index_title,
)


def test_resolve_index_snippet_prefers_page_summary_for_enriched_pages() -> None:
    snippet = _resolve_index_snippet(
        content=".",
        metadata={
            "llm_enriched": True,
            "page_summary": "Краткое описание страницы про проверку VIN и историю автомобиля.",
        },
        snippet_limit=500,
    )
    assert snippet == "Краткое описание страницы про проверку VIN и историю автомобиля."


def test_resolve_index_snippet_uses_page_summary_when_chunk_is_too_short() -> None:
    snippet = _resolve_index_snippet(
        content="blog/company/66083)",
        metadata={
            "page_summary": "Блог компании о технологиях и продуктах Яндекса.",
        },
        snippet_limit=500,
    )
    assert snippet == "Блог компании о технологиях и продуктах Яндекса."


def test_resolve_index_snippet_keeps_long_raw_chunk_without_summary() -> None:
    chunk = (
        "Документ для platform index search содержит уникальный маркер marker_123. "
        "Текст достаточно длинный для chunking и семантического поиска в RAG."
    )
    snippet = _resolve_index_snippet(
        content=chunk,
        metadata={},
        snippet_limit=500,
    )
    assert snippet == chunk


def test_resolve_index_title_prefers_page_title_metadata() -> None:
    title = _resolve_index_title(
        document_name="fallback.md",
        metadata={"page_title": "Будущее близко: стираем языковые границы"},
    )
    assert title == "Будущее близко: стираем языковые границы"
