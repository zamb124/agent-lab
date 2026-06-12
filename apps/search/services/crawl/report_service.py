"""Read-only crawl report aggregation for admin dashboards."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.search.db.crawl_repositories import (
    CrawlDomainRepository,
    CrawlJobRepository,
    CrawlProfileRepository,
    CrawlUrlRepository,
)
from core.crawl.models import (
    CrawlDomain,
    CrawlJob,
    CrawlProfileSummary,
    CrawlProfileWithIndex,
    CrawlUrlListItem,
)
from core.pagination import OffsetPage


class CrawlReportService:
    def __init__(
        self,
        crawl_profile_repository: CrawlProfileRepository,
        crawl_domain_repository: CrawlDomainRepository,
        crawl_url_repository: CrawlUrlRepository,
        crawl_job_repository: CrawlJobRepository,
    ) -> None:
        self._crawl_profile_repository: CrawlProfileRepository = crawl_profile_repository
        self._crawl_domain_repository: CrawlDomainRepository = crawl_domain_repository
        self._crawl_url_repository: CrawlUrlRepository = crawl_url_repository
        self._crawl_job_repository: CrawlJobRepository = crawl_job_repository

    async def list_profiles(self, *, limit: int, offset: int) -> OffsetPage[CrawlProfileWithIndex]:
        return await self._crawl_profile_repository.list_page(limit=limit, offset=offset)

    async def list_domains(
        self,
        *,
        crawl_profile_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlDomain]:
        _ = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        return await self._crawl_domain_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def get_profile_summary(self, crawl_profile_id: str) -> CrawlProfileSummary:
        profile = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        now = datetime.now(UTC)
        domain_counts = await self._crawl_domain_repository.count_by_status(crawl_profile_id)
        url_counts = await self._crawl_url_repository.count_by_status_for_profile(crawl_profile_id)
        domains_total = await self._crawl_domain_repository.count_for_profile(crawl_profile_id)
        domains_due = await self._crawl_domain_repository.count_due(crawl_profile_id, now=now)
        running_job = await self._crawl_job_repository.get_running(crawl_profile_id)
        latest_job = await self._crawl_job_repository.get_latest(crawl_profile_id)
        return CrawlProfileSummary(
            profile=profile,
            domain_counts=domain_counts,
            url_counts=url_counts,
            domains_total=domains_total,
            domains_due=domains_due,
            latest_job=latest_job,
            running_job=running_job,
        )

    async def list_jobs(
        self,
        *,
        crawl_profile_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlJob]:
        _ = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        return await self._crawl_job_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def list_urls(
        self,
        *,
        crawl_profile_id: str,
        crawl_status: str | None,
        domain: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlUrlListItem]:
        _ = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        return await self._crawl_url_repository.list_page_for_profile(
            crawl_profile_id=crawl_profile_id,
            crawl_status=crawl_status,
            domain=domain,
            limit=limit,
            offset=offset,
        )
