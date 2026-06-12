"""HTTP-facing crawl admin orchestration."""

from __future__ import annotations

from apps.search.db.crawl_repositories import (
    CrawlDomainRepository,
    CrawlJobRepository,
    CrawlProfileRepository,
    CrawlUrlRepository,
)
from apps.search.services.crawl.orchestrator_service import CrawlOrchestratorService
from core.crawl.models import (
    CrawlDomainRunResponse,
    CrawlJob,
    CrawlJobCreateRequest,
    CrawlOrchestratorTickResult,
    CrawlProfileCreateRequest,
    CrawlProfileWithIndex,
    SeedImportRequest,
    SeedImportResult,
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

    async def list_profiles(self, *, limit: int, offset: int) -> OffsetPage[CrawlProfileWithIndex]:
        return await self._crawl_profile_repository.list_page(limit=limit, offset=offset)

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
