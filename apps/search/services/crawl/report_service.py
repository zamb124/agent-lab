"""Read-only crawl report aggregation for admin dashboards."""

from __future__ import annotations

from datetime import UTC, datetime

from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.crawl.models import (
    CrawlDomain,
    CrawlJob,
    CrawlProfile,
    CrawlProfileSummary,
    CrawlProfileWithIndex,
    CrawlUrl,
    CrawlUrlDetail,
    CrawlUrlIndexedContent,
    CrawlUrlListItem,
)
from core.crawl.report_projection import filter_metadata_from_rag_metadata
from core.logging import get_logger
from core.pagination import OffsetPage

logger = get_logger(__name__)


class CrawlReportService:
    def __init__(self, rag_client: RagClient) -> None:
        self._rag_client: RagClient = rag_client

    async def list_profiles(self, *, limit: int, offset: int) -> OffsetPage[CrawlProfileWithIndex]:
        return await CrawlProfile.with_index_page_by_crawl_profile_id(limit=limit, offset=offset)

    async def list_domains(
        self,
        *,
        crawl_profile_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlDomain]:
        _ = await CrawlProfile.require_with_index(crawl_profile_id)
        return await CrawlDomain.page_by_domain(
            crawl_profile_id=crawl_profile_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def get_profile_summary(self, crawl_profile_id: str) -> CrawlProfileSummary:
        profile = await CrawlProfile.require_with_index(crawl_profile_id)
        now = datetime.now(UTC)
        domain_counts = await CrawlDomain.count_by_status(crawl_profile_id)
        url_counts = await CrawlUrl.count_by_status_for_profile(crawl_profile_id)
        domains_total = await CrawlDomain.count_for_profile(crawl_profile_id)
        domains_due = await CrawlDomain.count_due(crawl_profile_id, now=now)
        running_job = await CrawlJob.active_for_profile(crawl_profile_id)
        latest_job = await CrawlJob.latest_for_profile(crawl_profile_id)
        content_type_counts = await CrawlUrl.count_by_enrichment_content_type(crawl_profile_id)
        primary_topic_counts = await CrawlUrl.count_by_enrichment_primary_topic(crawl_profile_id)
        urls_enriched_total = await CrawlUrl.count_enriched_for_profile(crawl_profile_id)
        urls_enrichment_pending = await CrawlUrl.count_enrichment_pending_for_profile(
            crawl_profile_id,
            llm_enrichment_enabled=profile.profile.llm_enrichment_enabled,
        )
        return CrawlProfileSummary(
            profile=profile,
            domain_counts=domain_counts,
            url_counts=url_counts,
            domains_total=domains_total,
            domains_due=domains_due,
            latest_job=latest_job,
            running_job=running_job,
            content_type_counts=content_type_counts,
            primary_topic_counts=primary_topic_counts,
            urls_enriched_total=urls_enriched_total,
            urls_enrichment_pending=urls_enrichment_pending,
        )

    async def list_jobs(
        self,
        *,
        crawl_profile_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlJob]:
        _ = await CrawlProfile.require_with_index(crawl_profile_id)
        return await CrawlJob.page_by_started_at_desc(
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
        content_type: str | None,
        primary_topic: str | None,
        enriched_only: bool | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlUrlListItem]:
        _ = await CrawlProfile.require_with_index(crawl_profile_id)
        return await CrawlUrl.list_page_for_profile(
            crawl_profile_id=crawl_profile_id,
            crawl_status=crawl_status,
            domain=domain,
            content_type=content_type,
            primary_topic=primary_topic,
            enriched_only=enriched_only,
            limit=limit,
            offset=offset,
        )

    async def get_url_detail(
        self,
        crawl_url_id: str,
        crawl_profile_id: str,
    ) -> CrawlUrlDetail:
        profile = await CrawlProfile.require_with_index(crawl_profile_id)
        url_item, extract_title, extract_markdown = await CrawlUrl.require_for_profile(
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
                    "search.crawl.url.detail.indexed.content",
                    namespace=rag_namespace_id,
                    document_id=document_id,
                    error=message,
                )
                return None
            raise
        page_summary_raw = rag_content.metadata.get("page_summary")
        page_summary: str | None = None
        if isinstance(page_summary_raw, str) and page_summary_raw.strip():
            page_summary = page_summary_raw.strip()
        llm_enriched_raw = rag_content.metadata.get("llm_enriched")
        llm_enriched = llm_enriched_raw is True
        filter_metadata = None
        if llm_enriched:
            filter_metadata = filter_metadata_from_rag_metadata(rag_content.metadata)
        return CrawlUrlIndexedContent(
            document_id=rag_content.document_id,
            document_name=rag_content.document_name,
            markdown=rag_content.markdown,
            page_summary=page_summary,
            llm_enriched=llm_enriched,
            chunks_count=rag_content.chunks_count,
            filter_metadata=filter_metadata,
            metadata=rag_content.metadata,
        )
