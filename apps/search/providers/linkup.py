"""Search-провайдер Linkup."""

from __future__ import annotations

import time

import httpx

from apps.search.config import SearchLinkupConfig
from apps.search.providers.common import display_url, provider_status, string_field
from core.http import ProxyStrategy, get_httpx_client
from core.search import MetaSearchProviderStatus, MetaSearchRequest, WebSearchResult
from core.types import JsonObject, parse_json_object, require_json_object


class LinkupSearchProvider:
    """Linkup-адаптер для сырого вывода searchResults."""

    provider_id: str = "linkup"

    def __init__(self, config: SearchLinkupConfig) -> None:
        self._config: SearchLinkupConfig = config

    async def search(
        self,
        request: MetaSearchRequest,
    ) -> tuple[list[WebSearchResult], MetaSearchProviderStatus]:
        started = time.perf_counter()
        if not self._config.enabled:
            return [], provider_status(started, ok=False, error="linkup provider is disabled")
        api_key = self._config.api_key.strip()
        if not api_key:
            return [], provider_status(started, ok=False, error="linkup api key is not configured")

        url = f"{self._config.base_url.rstrip('/')}/v1/search"
        body: JsonObject = {
            "q": request.query,
            "depth": self._config.depth,
            "outputType": self._config.output_type,
            "includeImages": False,
            "maxResults": request.limit,
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
                    error=f"linkup returned HTTP {response.status_code}: {response.text[:300]}",
                )
            payload = parse_json_object(response.content, "linkup response")
        except (httpx.HTTPError, ValueError) as exc:
            return [], provider_status(started, ok=False, error=str(exc))

        results = parse_linkup_results(payload, limit=request.limit)
        return results, provider_status(started, ok=True, results_count=len(results))


def parse_linkup_results(payload: object, *, limit: int) -> list[WebSearchResult]:
    try:
        payload_object = require_json_object(payload, "linkup payload")
    except ValueError:
        return []
    raw_results = payload_object.get("results")
    if not isinstance(raw_results, list):
        return []

    results: list[WebSearchResult] = []
    for index, item_raw in enumerate(raw_results, start=1):
        try:
            item = require_json_object(item_raw, "linkup result")
        except ValueError:
            continue
        title = string_field(item.get("name"))
        url = string_field(item.get("url"))
        if not title or not url:
            continue
        results.append(
            WebSearchResult(
                title=title,
                url=url,
                snippet=string_field(item.get("content")),
                display_url=display_url(url),
                provider=LinkupSearchProvider.provider_id,
                provider_rank=index,
                source_type=string_field(item.get("type")) or "organic",
            )
        )
        if len(results) >= limit:
            break
    return results
