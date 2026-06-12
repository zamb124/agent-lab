"""Typed HTTP client for search service."""

from __future__ import annotations

from core.clients.service_client import ServiceClient
from core.crawl.models import CrawlDomainRunResponse, CrawlJobCreateRequest, CrawlJobQueuedResponse
from core.search.models import MetaSearchRequest, MetaSearchResponse


class SearchClient:
    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._client: ServiceClient = service_client if service_client is not None else ServiceClient()

    async def search(self, request: MetaSearchRequest) -> MetaSearchResponse:
        response = await self._client.post(
            "search",
            "/search/api/v1/search",
            json=request.model_dump(mode="json"),
        )
        return MetaSearchResponse.model_validate(response)

    async def queue_crawl_job(self, body: CrawlJobCreateRequest) -> CrawlJobQueuedResponse:
        response = await self._client.post(
            "search",
            "/search/api/v1/crawl/jobs",
            json=body.model_dump(mode="json"),
        )
        return CrawlJobQueuedResponse.model_validate(response)

    async def run_crawl_domain(self, crawl_domain_id: str, crawl_profile_id: str) -> CrawlDomainRunResponse:
        response = await self._client.post(
            "search",
            f"/search/api/v1/crawl/domains/{crawl_domain_id}/run",
            params={"crawl_profile_id": crawl_profile_id},
            json={},
        )
        return CrawlDomainRunResponse.model_validate(response)
