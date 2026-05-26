"""TinyFish Search provider."""

from __future__ import annotations

import time

import httpx

from apps.search.config import SearchTinyFishConfig
from apps.search.providers.common import display_url, int_rank, provider_status, string_field
from core.http import ProxyStrategy, get_httpx_client
from core.search import MetaSearchProviderStatus, MetaSearchRequest, WebSearchResult
from core.types import parse_json_object, require_json_object


class TinyFishSearchProvider:
    """TinyFish Search adapter."""

    provider_id: str = "tinyfish"

    def __init__(self, config: SearchTinyFishConfig) -> None:
        self._config: SearchTinyFishConfig = config

    async def search(
        self,
        request: MetaSearchRequest,
    ) -> tuple[list[WebSearchResult], MetaSearchProviderStatus]:
        started = time.perf_counter()
        if not self._config.enabled:
            return [], provider_status(started, ok=False, error="tinyfish provider is disabled")
        api_key = self._config.api_key.strip()
        if not api_key:
            return [], provider_status(started, ok=False, error="tinyfish api key is not configured")

        params = {
            "query": request.query,
            "location": request.region.upper(),
            "language": request.language.lower(),
        }
        headers = {"X-API-Key": api_key}

        try:
            async with get_httpx_client(
                timeout=self._config.timeout_seconds,
                strategy=ProxyStrategy.SMART,
            ) as client:
                response = await client.get(self._config.base_url.rstrip("/"), headers=headers, params=params)
            if response.status_code >= 400:
                return [], provider_status(
                    started,
                    ok=False,
                    error=f"tinyfish returned HTTP {response.status_code}: {response.text[:300]}",
                )
            payload = parse_json_object(response.content, "tinyfish response")
        except (httpx.HTTPError, ValueError) as exc:
            return [], provider_status(started, ok=False, error=str(exc))

        results = parse_tinyfish_results(payload, limit=request.limit)
        return results, provider_status(started, ok=True, results_count=len(results))


def parse_tinyfish_results(payload: object, *, limit: int) -> list[WebSearchResult]:
    try:
        payload_object = require_json_object(payload, "tinyfish payload")
    except ValueError:
        return []
    raw_results = payload_object.get("results")
    if not isinstance(raw_results, list):
        return []

    results: list[WebSearchResult] = []
    for index, item_raw in enumerate(raw_results, start=1):
        try:
            item = require_json_object(item_raw, "tinyfish result")
        except ValueError:
            continue
        title = string_field(item.get("title"))
        url = string_field(item.get("url"))
        if not title or not url:
            continue
        snippet = string_field(item.get("snippet"))
        site_name = string_field(item.get("site_name"))
        results.append(
            WebSearchResult(
                title=title,
                url=url,
                snippet=snippet,
                display_url=site_name or display_url(url),
                provider=TinyFishSearchProvider.provider_id,
                provider_rank=int_rank(item.get("position"), default=index),
                source_type="organic",
            )
        )
        if len(results) >= limit:
            break
    return results
