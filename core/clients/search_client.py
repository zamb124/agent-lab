"""Typed HTTP client for search service."""

from __future__ import annotations

from core.clients.service_client import ServiceClient
from core.crawl.models import (
    CrawlDomain,
    CrawlDomainCreateRequest,
    CrawlDomainPatchRequest,
    CrawlDomainRunResponse,
    CrawlJobCreateRequest,
    CrawlJobQueuedResponse,
    CrawlProfilePatchRequest,
    CrawlProfileWithIndex,
    CrawlUrl,
    CrawlUrlAddRequest,
    UpsertStats,
)
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

    async def patch_crawl_profile(
        self,
        crawl_profile_id: str,
        body: CrawlProfilePatchRequest,
    ) -> CrawlProfileWithIndex:
        response = await self._client.patch(
            "search",
            f"/search/api/v1/crawl/profiles/{crawl_profile_id}",
            json=body.model_dump(mode="json", exclude_none=True),
        )
        return CrawlProfileWithIndex.model_validate(response)

    async def create_crawl_domain(
        self,
        crawl_profile_id: str,
        body: CrawlDomainCreateRequest,
    ) -> CrawlDomain:
        response = await self._client.post(
            "search",
            f"/search/api/v1/crawl/profiles/{crawl_profile_id}/domains",
            json=body.model_dump(mode="json"),
        )
        return CrawlDomain.model_validate(response)

    async def patch_crawl_domain(
        self,
        crawl_domain_id: str,
        crawl_profile_id: str,
        body: CrawlDomainPatchRequest,
    ) -> CrawlDomain:
        response = await self._client.patch(
            "search",
            f"/search/api/v1/crawl/domains/{crawl_domain_id}",
            params={"crawl_profile_id": crawl_profile_id},
            json=body.model_dump(mode="json", exclude_none=True),
        )
        return CrawlDomain.model_validate(response)

    async def delete_crawl_domain(self, crawl_domain_id: str, crawl_profile_id: str) -> None:
        _ = await self._client.delete(
            "search",
            f"/search/api/v1/crawl/domains/{crawl_domain_id}",
            params={"crawl_profile_id": crawl_profile_id},
        )

    async def add_crawl_domain_urls(
        self,
        crawl_domain_id: str,
        crawl_profile_id: str,
        body: CrawlUrlAddRequest,
    ) -> UpsertStats:
        response = await self._client.post(
            "search",
            f"/search/api/v1/crawl/domains/{crawl_domain_id}/urls",
            params={"crawl_profile_id": crawl_profile_id},
            json=body.model_dump(mode="json"),
        )
        return UpsertStats.model_validate(response)

    async def recrawl_crawl_url(self, crawl_url_id: str, crawl_profile_id: str) -> CrawlUrl:
        response = await self._client.post(
            "search",
            f"/search/api/v1/crawl/urls/{crawl_url_id}/recrawl",
            params={"crawl_profile_id": crawl_profile_id},
            json={},
        )
        return CrawlUrl.model_validate(response)
