"""Детерминированное обогащение поиска для public search flows."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from core.search import (
    SearchMode,
    SearchResultAction,
    SearchResultInsight,
    SearchResultInsightsRequest,
    SearchResultInsightsResponse,
    SearchSuggestion,
    SearchSuggestionKind,
    SearchSuggestRequest,
    SearchSuggestResponse,
    WebSearchResult,
)

_TOKEN_RE: re.Pattern[str] = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")
_STOP_WORDS: frozenset[str] = frozenset({
    "and",
    "for",
    "from",
    "the",
    "with",
    "как",
    "для",
    "или",
    "что",
    "это",
    "при",
    "про",
    "чем",
})


def _query_tokens(value: str) -> list[str]:
    out: list[str] = []
    for match in _TOKEN_RE.finditer(value.lower()):
        raw = match.group(0)
        if len(raw) < 3 or raw in _STOP_WORDS or raw in out:
            continue
        out.append(raw)
    return out


def _host(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url.strip()
    return parsed.netloc.lower() or url.strip()


def _result_rank(result: WebSearchResult, index: int) -> int:
    if result.rank > 0:
        return result.rank
    return result.provider_rank if result.provider_rank > 0 else index


def _score_by_position(position: int) -> float:
    return max(0.0, 1.0 - (float(position - 1) / 20.0))


class SearchSuggestionService:
    """Собирает типизированные подсказки для search UI и public_search flow."""

    def suggest(self, request: SearchSuggestRequest) -> SearchSuggestResponse:
        suggestions = self._suggestions(request)
        followups = self._followups(request)
        return SearchSuggestResponse(
            query=request.query,
            mode=request.mode,
            suggestions=suggestions[: request.limit],
            followups=followups[: request.limit],
        )

    def _suggestions(self, request: SearchSuggestRequest) -> list[SearchSuggestion]:
        query = request.query
        raw: list[tuple[str, SearchSuggestionKind, float]] = [
            (f"{query} официальные источники", "source_check", 0.94),
            (f"{query} сравнение вариантов", "compare", 0.89),
            (f"{query} Россия 2026", "refine", 0.84),
        ]
        if request.mode in ("deep", "research"):
            raw.append((f"{query} первоисточники и документы", "deep_dive", 0.92))
        if request.mode == "research":
            raw.append((f"{query} структурированный исследовательский отчет", "research_plan", 0.9))
        for host in self._top_hosts(request.results, remaining=request.limit):
            raw.append((f"проверить источник {host}", "source_check", 0.78))
        return _unique_suggestions(raw)

    def _followups(self, request: SearchSuggestRequest) -> list[SearchSuggestion]:
        query = request.query
        raw: list[tuple[str, SearchSuggestionKind, float]] = [
            (f"Какие выводы подтверждаются несколькими источниками по запросу «{query}»?", "follow_up", 0.91),
            (f"Какие есть противоречия в источниках по запросу «{query}»?", "follow_up", 0.86),
        ]
        if request.results:
            raw.append((f"Сравни топ-{min(3, len(request.results))} источника по надежности", "compare", 0.83))
        if request.mode != "quick":
            raw.append((f"Собери план глубокого исследования по запросу «{query}»", "research_plan", 0.88))
        return _unique_suggestions(raw)

    def _top_hosts(self, results: list[WebSearchResult], *, remaining: int) -> list[str]:
        hosts: list[str] = []
        for result in results:
            host = _host(result.url)
            if host and host not in hosts:
                hosts.append(host)
            if len(hosts) >= remaining:
                break
        return hosts


class SearchResultInsightService:
    """Собирает детерминированные подсказки релевантности и UI-действия по каждому результату."""

    def insights(self, request: SearchResultInsightsRequest) -> SearchResultInsightsResponse:
        query_terms = _query_tokens(request.query)
        items: list[SearchResultInsight] = []
        for index, result in enumerate(request.results[: request.limit], start=1):
            rank = _result_rank(result, index)
            matched_terms = self._matched_terms(query_terms, result)
            confidence = self._confidence(query_terms, matched_terms, rank)
            items.append(
                SearchResultInsight(
                    title=result.title,
                    url=result.url,
                    provider=result.provider,
                    rank=rank,
                    confidence=confidence,
                    matched_terms=matched_terms,
                    relevance_hint=self._hint(result, matched_terms, confidence),
                    actions=self._actions(request.mode, len(request.results)),
                )
            )
        return SearchResultInsightsResponse(
            query=request.query,
            mode=request.mode,
            insights=items,
        )

    def _matched_terms(self, query_terms: list[str], result: WebSearchResult) -> list[str]:
        text = f"{result.title} {result.snippet} {result.display_url}"
        result_terms = set(_query_tokens(text))
        return [term for term in query_terms if term in result_terms][:12]

    def _confidence(
        self,
        query_terms: list[str],
        matched_terms: list[str],
        rank: int,
    ) -> float:
        coverage = float(len(matched_terms)) / float(len(query_terms)) if query_terms else 0.0
        confidence = 0.3 + (coverage * 0.5) + (_score_by_position(rank) * 0.2)
        return round(min(1.0, confidence), 4)

    def _hint(
        self,
        result: WebSearchResult,
        matched_terms: list[str],
        confidence: float,
    ) -> str:
        host = _host(result.url)
        if matched_terms:
            terms = ", ".join(matched_terms[:5])
            return f"{host}: совпадение по ключевым словам {terms}; confidence {confidence:.2f}."
        return f"{host}: релевантность основана на позиции в выдаче {result.provider}; confidence {confidence:.2f}."

    def _actions(self, mode: SearchMode, result_count: int) -> list[SearchResultAction]:
        actions: list[SearchResultAction] = [
            "open_source",
            "summarize_source",
            "ask_source",
        ]
        if result_count > 1:
            actions.append("compare_sources")
        if mode != "quick":
            actions.append("extract_facts")
        return actions


def _unique_suggestions(
    raw: list[tuple[str, SearchSuggestionKind, float]]
) -> list[SearchSuggestion]:
    seen: set[str] = set()
    out: list[SearchSuggestion] = []
    for text, kind, score in sorted(raw, key=lambda item: -item[2]):
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(SearchSuggestion(text=text, kind=kind, score=score))
    return out
