"""HTTP-facing crawl admin orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.search.db.crawl_repositories import (
    CrawlDomainRepository,
    CrawlJobRepository,
    CrawlProfileRepository,
    CrawlUrlRepository,
)
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from core.crawl.models import (
    CrawlDomain,
    CrawlDomainCreateRequest,
    CrawlDomainPatchRequest,
    CrawlDomainRunResponse,
    CrawlJob,
    CrawlJobCreateRequest,
    CrawlOrchestratorTickResult,
    CrawlProfileCreateRequest,
    CrawlProfilePatchRequest,
    CrawlProfileWithIndex,
    CrawlUrl,
    CrawlUrlAddRequest,
    SeedImportRequest,
    SeedImportResult,
    UpsertStats,
)
from core.pagination import OffsetPage


class SearchCrawlService:
    def __init__(
        self,
        crawl_profile_repository: CrawlProfileRepository,
        crawl_domain_repository: CrawlDomainRepository,
        crawl_url_repository: CrawlUrlRepository,
        crawl_job_repository: CrawlJobRepository,
        crawl_orchestrator_service: CrawlOrchestratorService,
    ) -> None:
        self._crawl_profile_repository: CrawlProfileRepository = crawl_profile_repository
        self._crawl_domain_repository: CrawlDomainRepository = crawl_domain_repository
        self._crawl_url_repository: CrawlUrlRepository = crawl_url_repository
        self._crawl_job_repository: CrawlJobRepository = crawl_job_repository
        self._crawl_orchestrator_service: CrawlOrchestratorService = crawl_orchestrator_service

    async def create_profile(self, body: CrawlProfileCreateRequest) -> CrawlProfileWithIndex:
        return await self._crawl_profile_repository.create(body)

    async def patch_profile(
        self,
        crawl_profile_id: str,
        body: CrawlProfilePatchRequest,
    ) -> CrawlProfileWithIndex:
        return await self._crawl_profile_repository.patch(crawl_profile_id, body)

    async def list_profiles(self, *, limit: int, offset: int) -> OffsetPage[CrawlProfileWithIndex]:
        return await self._crawl_profile_repository.list_page(limit=limit, offset=offset)

    async def create_domain(
        self,
        crawl_profile_id: str,
        body: CrawlDomainCreateRequest,
    ) -> CrawlDomain:
        _ = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        domain = await self._crawl_domain_repository.create(
            crawl_profile_id,
            body,
            next_crawl_after=datetime.now(UTC),
        )
        if body.seed_urls:
            _ = await self._crawl_url_repository.add_manual_urls(
                domain.crawl_domain_id,
                body.seed_urls,
            )
        return domain

    async def patch_domain(
        self,
        crawl_domain_id: str,
        crawl_profile_id: str,
        body: CrawlDomainPatchRequest,
    ) -> CrawlDomain:
        domain = await self._crawl_domain_repository.get(crawl_domain_id)
        if domain.crawl_profile_id != crawl_profile_id:
            raise ValueError("crawl_domain_id does not belong to crawl_profile_id")
        return await self._crawl_domain_repository.patch(crawl_domain_id, body)

    async def delete_domain(self, crawl_domain_id: str, crawl_profile_id: str) -> None:
        domain = await self._crawl_domain_repository.get(crawl_domain_id)
        if domain.crawl_profile_id != crawl_profile_id:
            raise ValueError("crawl_domain_id does not belong to crawl_profile_id")
        await self._crawl_domain_repository.delete(crawl_domain_id)

    async def add_domain_urls(
        self,
        crawl_domain_id: str,
        crawl_profile_id: str,
        body: CrawlUrlAddRequest,
    ) -> UpsertStats:
        domain = await self._crawl_domain_repository.get(crawl_domain_id)
        if domain.crawl_profile_id != crawl_profile_id:
            raise ValueError("crawl_domain_id does not belong to crawl_profile_id")
        return await self._crawl_url_repository.add_manual_urls(crawl_domain_id, body.urls)

    async def recrawl_url(self, crawl_url_id: str, crawl_profile_id: str) -> CrawlUrl:
        _, _, _ = await self._crawl_url_repository.get_for_profile(crawl_url_id, crawl_profile_id)
        return await self._crawl_url_repository.requeue_url(crawl_url_id)

    async def start_job(self, body: CrawlJobCreateRequest) -> CrawlOrchestratorTickResult:
        return await self._crawl_orchestrator_service.run_tick(
            crawl_profile_id=body.crawl_profile_id,
            trigger=body.trigger,
            schedule_task_id=None,
        )

    async def get_job(self, crawl_job_id: str) -> CrawlJob:
        return await self._crawl_job_repository.get(crawl_job_id)

    async def import_seed(self, body: SeedImportRequest) -> SeedImportResult:
        return await self._crawl_orchestrator_service.import_seed(body)

    async def run_domain(self, crawl_domain_id: str, crawl_profile_id: str) -> CrawlDomainRunResponse:
        return await self._crawl_orchestrator_service.run_single_domain(
            crawl_domain_id,
            crawl_profile_id,
        )
