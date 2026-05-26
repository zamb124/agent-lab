from apps.search.services.enrichment import (
    SearchResultInsightService,
    SearchSuggestionService,
    _unique_suggestions,
)
from core.search import SearchResultInsightsRequest, SearchSuggestRequest, WebSearchResult


def _result(
    *,
    title: str = "Humanitec Search Platform",
    url: str = "https://example.com/search",
    snippet: str = "Humanitec public search platform with documents",
    rank: int = 1,
    provider_rank: int = 1,
) -> WebSearchResult:
    return WebSearchResult(
        title=title,
        url=url,
        snippet=snippet,
        display_url=url,
        provider="serper",
        provider_rank=provider_rank,
        rank=rank,
        source_type="organic",
    )


def test_search_suggestion_service_builds_quick_suggestions_without_results() -> None:
    response = SearchSuggestionService().suggest(
        SearchSuggestRequest(query="Humanitec поиск", mode="quick", limit=3)
    )

    assert response.mode == "quick"
    assert [item.kind for item in response.suggestions] == [
        "source_check",
        "compare",
        "refine",
    ]
    assert all("Humanitec поиск" in item.text for item in response.suggestions)
    assert [item.kind for item in response.followups] == ["follow_up", "follow_up"]


def test_search_suggestion_service_adds_research_and_source_hints() -> None:
    response = SearchSuggestionService().suggest(
        SearchSuggestRequest(
            query="AI поиск",
            mode="research",
            limit=7,
            results=[
                _result(url="https://example.com/a"),
                _result(url="https://docs.example.com/b"),
                _result(url="https://example.com/c"),
            ],
        )
    )

    assert {item.kind for item in response.suggestions} >= {
        "research_plan",
        "deep_dive",
        "source_check",
    }
    assert any(item.text == "проверить источник docs.example.com" for item in response.suggestions)
    assert response.followups[-1].kind == "compare"

    limited = SearchSuggestionService().suggest(
        SearchSuggestRequest(
            query="AI поиск",
            mode="quick",
            limit=1,
            results=[
                _result(url="https://one.example/a"),
                _result(url="https://two.example/b"),
            ],
        )
    )
    assert len(limited.suggestions) == 1


def test_search_result_insight_service_scores_matches_and_actions() -> None:
    response = SearchResultInsightService().insights(
        SearchResultInsightsRequest(
            query="Humanitec документы",
            mode="deep",
            results=[
                _result(),
                _result(
                    title="Other result",
                    url="https://other.example/page",
                    snippet="Different content",
                    rank=2,
                    provider_rank=2,
                ),
            ],
        )
    )

    first = response.insights[0]
    second = response.insights[1]
    assert first.matched_terms == ["humanitec"]
    assert first.confidence > second.confidence
    assert first.actions == [
        "open_source",
        "summarize_source",
        "ask_source",
        "compare_sources",
        "extract_facts",
    ]
    assert "совпадение по ключевым словам" in first.relevance_hint
    assert "релевантность основана на позиции" in second.relevance_hint


def test_search_result_insight_service_handles_empty_terms_and_invalid_url() -> None:
    response = SearchResultInsightService().insights(
        SearchResultInsightsRequest(
            query="to",
            mode="quick",
            limit=1,
            results=[
                _result(
                    title="Short",
                    url="http://[",
                    snippet="No searchable match",
                    rank=0,
                    provider_rank=4,
                )
            ],
        )
    )

    insight = response.insights[0]
    assert insight.rank == 4
    assert insight.matched_terms == []
    assert insight.actions == ["open_source", "summarize_source", "ask_source"]
    assert insight.relevance_hint.startswith("http://[:")


def test_unique_suggestions_orders_and_deduplicates() -> None:
    suggestions = _unique_suggestions(
        [
            ("one", "refine", 0.4),
            ("two", "compare", 0.9),
            ("one", "source_check", 0.8),
        ]
    )

    assert [item.text for item in suggestions] == ["two", "one"]
    assert suggestions[1].kind == "source_check"
