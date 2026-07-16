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
    CrawlDomainCreateRequest,
    CrawlDomainCreateResponse,
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

    async def create_domain(self, body: CrawlDomainCreateRequest) -> CrawlDomainCreateResponse:
        from apps.search.db.crawl_repositories import normalize_crawl_domain
        from apps.search.services.crawl.seed_loader import import_manual_domains

        profile_bundle = await self._crawl_profile_repository.get_with_index(body.crawl_profile_id)
        if not profile_bundle.profile.enabled:
            raise ValueError(f"crawl profile disabled: {body.crawl_profile_id}")

        normalized_domain = normalize_crawl_domain(body.domain)
        if normalized_domain in profile_bundle.profile.denylist_domains:
            raise ValueError(f"domain is denylisted: {normalized_domain}")

        existing = await self._crawl_domain_repository.get_by_domain(
            body.crawl_profile_id,
            normalized_domain,
        )
        if existing is not None:
            raise ValueError(f"domain already exists: {existing.domain}")

        seed_result = await import_manual_domains(
            body.crawl_profile_id,
            crawl_domain_repository=self._crawl_domain_repository,
            domains=[normalized_domain],
        )
        if seed_result.imported < 1:
            raise ValueError(f"failed to create domain: {normalized_domain}")

        created = await self._crawl_domain_repository.get_by_domain(
            body.crawl_profile_id,
            normalized_domain,
        )
        if created is None:
            raise ValueError(f"domain not found after create: {normalized_domain}")

        run_response: CrawlDomainRunResponse | None = None
        if body.run_now:
            run_response = await self.run_domain(created.crawl_domain_id, body.crawl_profile_id)

        return CrawlDomainCreateResponse(domain=created, created=True, run=run_response)
