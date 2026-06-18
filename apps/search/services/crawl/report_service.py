"""Read-only crawl report aggregation for admin dashboards."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.search.db.crawl_repositories import (
    CrawlDomainRepository,
    CrawlJobRepository,
    CrawlProfileRepository,
    CrawlUrlRepository,
)
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.crawl.models import (
    CrawlDomain,
    CrawlJob,
    CrawlProfileSummary,
    CrawlProfileWithIndex,
    CrawlUrlDetail,
    CrawlUrlIndexedContent,
    CrawlUrlListItem,
)
from core.logging import get_logger
from core.pagination import OffsetPage

logger = get_logger(__name__)


class CrawlReportService:
    def __init__(
        self,
        crawl_profile_repository: CrawlProfileRepository,
        crawl_domain_repository: CrawlDomainRepository,
        crawl_url_repository: CrawlUrlRepository,
        crawl_job_repository: CrawlJobRepository,
        rag_client: RagClient,
    ) -> None:
        self._crawl_profile_repository: CrawlProfileRepository = crawl_profile_repository
        self._crawl_domain_repository: CrawlDomainRepository = crawl_domain_repository
        self._crawl_url_repository: CrawlUrlRepository = crawl_url_repository
        self._crawl_job_repository: CrawlJobRepository = crawl_job_repository
        self._rag_client: RagClient = rag_client

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

    async def get_url_detail(
        self,
        crawl_url_id: str,
        crawl_profile_id: str,
    ) -> CrawlUrlDetail:
        profile = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        url_item, extract_title, extract_markdown = await self._crawl_url_repository.get_for_profile(
            crawl_url_id,
            crawl_profile_id,
        )
        indexed_content = await self._load_indexed_content(
            document_id=url_item.document_id,
            rag_namespace_id=profile.search_index.rag_namespace_id,
        )
        return CrawlUrlDetail(
            url=url_item,
            extract_title=extract_title,
            extract_markdown=extract_markdown,
            indexed_content=indexed_content,
        )

    async def _load_indexed_content(
        self,
        *,
        document_id: str | None,
        rag_namespace_id: str,
    ) -> CrawlUrlIndexedContent | None:
        if document_id is None:
            return None
        try:
            rag_content = await self._rag_client.get_namespace_document_content(
                rag_namespace_id,
                document_id,
            )
        except ServiceClientError as exc:
            message = str(exc)
            if message.startswith("HTTP 404") or message.startswith("HTTP 501"):
                logger.warning(
                    "crawl url detail: indexed content unavailable namespace=%s document_id=%s error=%s",
                    rag_namespace_id,
                    document_id,
                    message,
                )
                return None
            raise
        page_summary_raw = rag_content.metadata.get("page_summary")
        page_summary: str | None = None
        if isinstance(page_summary_raw, str) and page_summary_raw.strip():
            page_summary = page_summary_raw.strip()
        llm_enriched_raw = rag_content.metadata.get("llm_enriched")
        llm_enriched = llm_enriched_raw is True
        return CrawlUrlIndexedContent(
            document_id=rag_content.document_id,
            document_name=rag_content.document_name,
            markdown=rag_content.markdown,
            page_summary=page_summary,
            llm_enriched=llm_enriched,
            chunks_count=rag_content.chunks_count,
            metadata=rag_content.metadata,
        )
