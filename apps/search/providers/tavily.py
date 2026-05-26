"""Tavily Search provider."""

from __future__ import annotations

import time

import httpx

from apps.search.config import SearchTavilyConfig
from apps.search.providers.common import display_url, provider_status, string_field
from core.http import ProxyStrategy, get_httpx_client
from core.search import MetaSearchProviderStatus, MetaSearchRequest, WebSearchResult
from core.types import JsonObject, parse_json_object, require_json_object


class TavilySearchProvider:
    """Tavily adapter for LLM-oriented search results."""

    provider_id: str = "tavily"

    def __init__(self, config: SearchTavilyConfig) -> None:
        self._config: SearchTavilyConfig = config

    async def search(
        self,
        request: MetaSearchRequest,
    ) -> tuple[list[WebSearchResult], MetaSearchProviderStatus]:
        started = time.perf_counter()
        if not self._config.enabled:
            return [], provider_status(started, ok=False, error="tavily provider is disabled")
        api_key = self._config.api_key.strip()
        if not api_key:
            return [], provider_status(started, ok=False, error="tavily api key is not configured")

        url = f"{self._config.base_url.rstrip('/')}/search"
        body: JsonObject = {
            "query": request.query,
            "max_results": request.limit,
            "search_depth": self._config.search_depth,
            "topic": self._config.topic,
            "include_answer": self._config.include_answer,
            "include_images": False,
            "include_raw_content": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with get_httpx_client(
                timeout=self._config.timeout_seconds,
                strategy=ProxyStrategy.SMART,
            ) as client:
                response = await client.post(url, headers=headers, json=body)
            if response.status_code >= 400:
                return [], provider_status(
                    started,
                    ok=False,
                    error=f"tavily returned HTTP {response.status_code}: {response.text[:300]}",
                )
            payload = parse_json_object(response.content, "tavily response")
        except (httpx.HTTPError, ValueError) as exc:
            return [], provider_status(started, ok=False, error=str(exc))

        results = parse_tavily_results(payload, limit=request.limit)
        return results, provider_status(started, ok=True, results_count=len(results))


def parse_tavily_results(payload: object, *, limit: int) -> list[WebSearchResult]:
    try:
        payload_object = require_json_object(payload, "tavily payload")
    except ValueError:
        return []
    raw_results = payload_object.get("results")
    if not isinstance(raw_results, list):
        return []

    results: list[WebSearchResult] = []
    for index, item_raw in enumerate(raw_results, start=1):
        try:
            item = require_json_object(item_raw, "tavily result")
        except ValueError:
            continue
        title = string_field(item.get("title"))
        url = string_field(item.get("url"))
        if not title or not url:
            continue
        results.append(
            WebSearchResult(
                title=title,
                url=url,
                snippet=string_field(item.get("content")),
                display_url=display_url(url),
                provider=TavilySearchProvider.provider_id,
                provider_rank=index,
                score=_score(item.get("score")),
                published_at=string_field(item.get("published_date")) or None,
                source_type="organic",
            )
        )
        if len(results) >= limit:
            break
    return results


def _score(value: object) -> float:
    if isinstance(value, int | float) and value >= 0:
        return float(value)
    return 0.0
