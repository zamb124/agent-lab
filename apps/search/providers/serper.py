"""Serper.dev Google Search provider."""

from __future__ import annotations

import time

import httpx

from apps.search.config import SearchSerperConfig
from apps.search.providers.common import display_url, int_rank, provider_status, string_field
from core.http import ProxyStrategy, get_httpx_client
from core.search import MetaSearchProviderStatus, MetaSearchRequest, WebSearchResult
from core.types import JsonObject, parse_json_object, require_json_object


class SerperSearchProvider:
    """Thin Serper adapter. It intentionally returns only normalized organic results."""

    provider_id: str = "serper"

    def __init__(self, config: SearchSerperConfig) -> None:
        self._config: SearchSerperConfig = config

    async def search(
        self,
        request: MetaSearchRequest,
    ) -> tuple[list[WebSearchResult], MetaSearchProviderStatus]:
        started = time.perf_counter()
        if not self._config.enabled:
            return [], provider_status(started, ok=False, error="serper provider is disabled")
        api_key = self._config.api_key.strip()
        if not api_key:
            return [], provider_status(started, ok=False, error="serper api key is not configured")

        url = f"{self._config.base_url.rstrip('/')}/search"
        body: JsonObject = {
            "q": request.query,
            "num": request.limit,
            "gl": request.region.lower(),
            "hl": request.language.lower(),
            "autocorrect": True,
        }
        headers = {
            "X-API-KEY": api_key,
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
                    error=f"serper returned HTTP {response.status_code}: {response.text[:300]}",
                )
            payload = parse_json_object(response.content, "serper response")
        except (httpx.HTTPError, ValueError) as exc:
            return [], provider_status(started, ok=False, error=str(exc))

        results = parse_serper_results(payload, limit=request.limit)
        return results, provider_status(started, ok=True, results_count=len(results))


def parse_serper_results(payload: object, *, limit: int) -> list[WebSearchResult]:
    try:
        payload_object = require_json_object(payload, "serper payload")
    except ValueError:
        return []
    organic_raw = payload_object.get("organic")
    if not isinstance(organic_raw, list):
        return []

    results: list[WebSearchResult] = []
    for index, item_raw in enumerate(organic_raw, start=1):
        try:
            item = require_json_object(item_raw, "serper organic result")
        except ValueError:
            continue
        title = string_field(item.get("title"))
        url = string_field(item.get("link"))
        if not title or not url:
            continue
        results.append(
            WebSearchResult(
                title=title,
                url=url,
                snippet=string_field(item.get("snippet")),
                display_url=display_url(url),
                provider=SerperSearchProvider.provider_id,
                provider_rank=int_rank(item.get("position"), default=index),
                published_at=string_field(item.get("date")) or None,
                source_type="organic",
            )
        )
        if len(results) >= limit:
            break
    return results
