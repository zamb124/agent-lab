"""Meta-search orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from apps.search.config import SearchIntegrationConfig
from apps.search.providers import (
    LinkupSearchProvider,
    SearchProvider,
    SerperSearchProvider,
    TavilySearchProvider,
    TinyFishSearchProvider,
)
from apps.search.services.provider_availability import ProviderAvailabilityStore
from core.search import (
    MetaSearchProviderStatus,
    MetaSearchRequest,
    MetaSearchResponse,
    WebSearchResult,
)

_PROVIDER_ALIASES: dict[str, str] = {
    "auto": "auto",
    "google": "serper",
    "tiny": "tinyfish",
    "tinyfish": "tinyfish",
    "linkup": "linkup",
    "serper_google": "serper",
    "serper": "serper",
    "tavily": "tavily",
    "travily": "tavily",
    "tvly": "tavily",
}

_TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "yclid",
    "mc_cid",
    "mc_eid",
}

ProviderSearchOutcome = tuple[list[WebSearchResult], MetaSearchProviderStatus]


def _canonical_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_PARAMS
    ]
    path = parsed.path.rstrip("/") or parsed.path
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            urlencode(query),
            "",
        )
    )


def _rank_results(
    candidates: dict[str, WebSearchResult],
    scores: dict[str, float],
    limit: int,
) -> list[WebSearchResult]:
    ordered = sorted(
        candidates.items(),
        key=lambda item: (-scores[item[0]], item[1].provider_rank, item[1].title),
    )
    out: list[WebSearchResult] = []
    for rank, (key, result) in enumerate(ordered[:limit], start=1):
        out.append(result.model_copy(update={"rank": rank, "score": round(scores[key], 6)}))
    return out


class MetaSearchService:
    """Small provider router with deterministic dedupe and ranking."""

    def __init__(
        self,
        search_config: SearchIntegrationConfig,
        availability_store: ProviderAvailabilityStore,
    ) -> None:
        self._config: SearchIntegrationConfig = search_config
        self._availability_store: ProviderAvailabilityStore = availability_store
        self._providers: dict[str, SearchProvider] = {
            "tinyfish": TinyFishSearchProvider(search_config.tinyfish),
            "linkup": LinkupSearchProvider(search_config.linkup),
            "serper": SerperSearchProvider(search_config.serper),
            "tavily": TavilySearchProvider(search_config.tavily),
        }

    async def search(self, request: MetaSearchRequest) -> MetaSearchResponse:
        provider_ids = self._resolve_provider_sequence(request.providers)
        if request.provider_strategy == "first_available":
            return await self._search_first_available(request, provider_ids)
        return await self._search_merge(request, provider_ids)

    async def _search_first_available(
        self,
        request: MetaSearchRequest,
        provider_ids: list[str],
    ) -> MetaSearchResponse:
        statuses: dict[str, MetaSearchProviderStatus] = {}
        for provider_id in provider_ids:
            if provider_id not in self._providers:
                statuses[provider_id] = self._unsupported_status(provider_id)
                continue
            unavailable_status = await self._unavailable_skip_status(provider_id)
            if unavailable_status is not None:
                statuses[provider_id] = unavailable_status
                continue

            provider = self._providers[provider_id]
            results, status = await provider.search(request)
            status = status.model_copy(update={"selected": True})
            statuses[provider_id] = status
            if status.ok:
                _ = await self._availability_store.mark_available(provider_id)
                ranked = self._collect_ranked([(provider_id, results)], request.limit)
                return MetaSearchResponse(query=request.query, results=ranked, providers=statuses)
            _ = await self._availability_store.mark_unavailable(
                provider_id,
                status.error or "unknown error",
            )

        return MetaSearchResponse(query=request.query, results=[], providers=statuses)

    async def _search_merge(
        self,
        request: MetaSearchRequest,
        provider_ids: list[str],
    ) -> MetaSearchResponse:
        statuses: dict[str, MetaSearchProviderStatus] = {}
        tasks: list[tuple[str, Awaitable[ProviderSearchOutcome]]] = []
        for provider_id in provider_ids:
            if provider_id not in self._providers:
                statuses[provider_id] = self._unsupported_status(provider_id)
                continue
            unavailable_status = await self._unavailable_skip_status(provider_id)
            if unavailable_status is not None:
                statuses[provider_id] = unavailable_status
                continue
            provider = self._providers[provider_id]
            tasks.append((provider_id, provider.search(request)))

        provider_results: list[tuple[str, list[WebSearchResult]]] = []
        if tasks:
            gathered = await asyncio.gather(*(task for _, task in tasks))
            for (provider_id, _), (results, status) in zip(tasks, gathered, strict=True):
                selected_status = status.model_copy(update={"selected": True})
                statuses[provider_id] = selected_status
                if selected_status.ok:
                    _ = await self._availability_store.mark_available(provider_id)
                    provider_results.append((provider_id, results))
                else:
                    _ = await self._availability_store.mark_unavailable(
                        provider_id,
                        selected_status.error or "unknown error",
                    )

        ranked = self._collect_ranked(provider_results, request.limit)
        return MetaSearchResponse(query=request.query, results=ranked, providers=statuses)

    async def _unavailable_skip_status(self, provider_id: str) -> MetaSearchProviderStatus | None:
        record = await self._availability_store.get(provider_id)
        if record is None or record.available:
            return None
        return MetaSearchProviderStatus(
            ok=False,
            error=record.last_error,
            skipped=True,
            skip_reason="provider marked unavailable in redis",
        )

    def _collect_ranked(
        self,
        provider_results: list[tuple[str, list[WebSearchResult]]],
        limit: int,
    ) -> list[WebSearchResult]:
        candidates: dict[str, WebSearchResult] = {}
        scores: dict[str, float] = {}
        for _, results in provider_results:
            for result in results:
                key = _canonical_url(result.url)
                score = 1.0 / (60.0 + float(result.provider_rank))
                if key not in candidates:
                    candidates[key] = result
                    scores[key] = score
                    continue
                scores[key] += score
                existing = candidates[key]
                if result.snippet and not existing.snippet:
                    candidates[key] = result
        return _rank_results(candidates, scores, limit)

    def _resolve_provider_sequence(self, raw: list[str]) -> list[str]:
        provider_ids = self._normalize_provider_ids(raw)
        if "auto" not in provider_ids:
            return provider_ids
        out: list[str] = []
        for provider_id in self._config.provider_order:
            if provider_id and provider_id not in out:
                out.append(provider_id)
        for provider_id in provider_ids:
            if provider_id != "auto" and provider_id not in out:
                out.append(provider_id)
        return out

    def _normalize_provider_ids(self, raw: list[str]) -> list[str]:
        out: list[str] = []
        for item in raw:
            raw_provider_id = item.strip().lower()
            provider_id = (
                _PROVIDER_ALIASES[raw_provider_id]
                if raw_provider_id in _PROVIDER_ALIASES
                else raw_provider_id
            )
            if provider_id and provider_id not in out:
                out.append(provider_id)
        return out or ["auto"]

    def _unsupported_status(self, provider_id: str) -> MetaSearchProviderStatus:
        return MetaSearchProviderStatus(
            ok=False,
            error=f"unsupported search provider: {provider_id}",
        )
