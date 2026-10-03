"""Таблица краула."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic, execute_raw
from pydantic import Field

from core.crawl.models.contracts import (
    CrawlFetchTransport,
    CrawlPageFilterMetadata,
    CrawlStatusCount,
    CrawlStructuralSignals,
    CrawlUrlEnrichmentSnapshot,
    CrawlUrlStatus,
    SitemapEntry,
    UpsertStats,
    canonicalize_url,
)
from core.crawl.models.crawl_domain import CrawlDomain
from core.models import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.pagination import OffsetPage
from core.rag.models import RAGMetadata
from core.types import JsonValue, parse_json_object, require_json_object


class CrawlUrl(PlatformModel):
    """URL обхода. Таблица ``crawl_urls``."""

    __database_alias__: ClassVar[str | None] = "search"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "crawl_urls"
        unique_together: list[tuple[str, str]] = [("crawl_domain_id", "canonical_url")]
        indexes: list[Index] = [
            Index(["crawl_domain_id", "crawl_status"]),
        ]

    crawl_url_id: str = DbField(db_pk=True, max_length=36)
    crawl_domain_id: str = DbField(max_length=36)
    url: str = DbField(db_type="TEXT")
    canonical_url: str = DbField(db_type="TEXT")
    crawl_status: CrawlUrlStatus = DbField(db_type="TEXT")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    sitemap_lastmod: datetime | None = DbField(default=None)
    content_hash: str | None = DbField(default=None, max_length=64)
    extract_content_hash: str | None = DbField(default=None, max_length=64)
    enriched_content_hash: str | None = DbField(default=None, max_length=64)
    enrichment_model: str | None = DbField(default=None, max_length=128)
    enrichment_prompt_version: str | None = DbField(default=None, max_length=32)
    fetch_transport: CrawlFetchTransport | None = DbField(default=None, db_type="TEXT")
    document_id: str | None = DbField(default=None, max_length=255)
    fetch_attempts: int = DbField(default=0)
    next_retry_after: datetime | None = DbField(default=None)
    extract_markdown: str | None = DbField(default=None, db_type="TEXT")
    extract_title: str | None = DbField(default=None, db_type="TEXT")
    extract_structural_signals: CrawlStructuralSignals | None = DbField(default=None, db_type="JSONB")
    enrichment_snapshot: CrawlUrlEnrichmentSnapshot | None = DbField(default=None, db_type="JSONB")
    last_error: str | None = DbField(default=None, db_type="TEXT")
    last_crawled_at: datetime | None = DbField(default=None)

    @classmethod
    async def upsert_from_sitemap(
        cls,
        crawl_domain_id: str,
        entries: list[SitemapEntry],
    ) -> UpsertStats:
        inserted = 0
        updated = 0
        now = datetime.now(UTC)
        async with atomic(using="search"):
            for entry in entries:
                canonical = canonicalize_url(entry.url)
                existing = await cls.objects.filter(
                    crawl_domain_id=crawl_domain_id,
                    canonical_url=canonical,
                ).get_or_none()
                if existing is None:
                    _ = await cls.objects.create(
                        instance=cls(
                            crawl_url_id=str(uuid.uuid4()),
                            crawl_domain_id=crawl_domain_id,
                            url=entry.url,
                            canonical_url=canonical,
                            sitemap_lastmod=entry.lastmod,
                            crawl_status="pending",
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    inserted += 1
                    continue
                if entry.lastmod is not None:
                    lastmod_advanced = (
                        existing.sitemap_lastmod is None or entry.lastmod > existing.sitemap_lastmod
                    )
                    crawled_before_lastmod = (
                        existing.last_crawled_at is None or entry.lastmod > existing.last_crawled_at
                    )
                    if (
                        lastmod_advanced
                        and crawled_before_lastmod
                        and existing.crawl_status in ("indexed", "skipped", "failed")
                    ):
                        existing.crawl_status = "pending"
                        existing.fetch_attempts = 0
                        existing.next_retry_after = None
                    existing.sitemap_lastmod = entry.lastmod
                existing.updated_at = now
                _ = await existing.save()
                updated += 1
        return UpsertStats(inserted=inserted, updated=updated)

    @classmethod
    async def count_pending(cls, crawl_domain_id: str) -> int:
        return await cls.objects.filter(
            crawl_domain_id=crawl_domain_id,
            crawl_status="pending",
        ).count()

    @classmethod
    async def count_pending_for_profile(cls, crawl_profile_id: str) -> int:
        return await CrawlDomain.scalar_count(
            "SELECT count(*)::int AS total FROM crawl_urls "
            + "JOIN crawl_domains ON crawl_urls.crawl_domain_id = crawl_domains.crawl_domain_id "
            + "WHERE crawl_domains.crawl_profile_id = $1 AND crawl_urls.crawl_status = 'pending'",
            [crawl_profile_id],
        )

    @classmethod
    async def claim_pending_batch(cls, crawl_domain_id: str, limit: int) -> list[Self]:
        now = datetime.now(UTC)
        async with atomic(using="search"):
            id_rows = await execute_raw(
                "SELECT crawl_url_id FROM crawl_urls "
                + "WHERE crawl_domain_id = $1 AND crawl_status = 'pending' "
                + "ORDER BY sitemap_lastmod DESC NULLS LAST, created_at DESC LIMIT $2",
                [crawl_domain_id, limit],
                using="search",
            )
            ids: list[str] = []
            for row in id_rows:
                crawl_url_id = require_json_object(row, "crawl_url")["crawl_url_id"]
                if not isinstance(crawl_url_id, str):
                    raise TypeError("crawl_url_id must be str")
                ids.append(crawl_url_id)
            if len(ids) == 0:
                return []
            _ = await cls.objects.filter(crawl_url_id__in=ids).update(
                using="search",
                crawl_status="fetching",
                updated_at=now,
            )
            return await cls.objects.filter(crawl_url_id__in=ids).all()

    @classmethod
    async def mark_indexed(
        cls,
        crawl_url_id: str,
        document_id: str,
        extract_content_hash: str,
        fetch_transport: str | None = None,
        *,
        extract_markdown: str,
        extract_title: str,
        extract_structural_signals: CrawlStructuralSignals,
        enriched_content_hash: str | None = None,
        enrichment_model: str | None = None,
        enrichment_prompt_version: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        transport: CrawlFetchTransport | None = None
        if fetch_transport == "http" or fetch_transport == "browser":
            transport = fetch_transport
        _ = await cls.objects.filter(crawl_url_id=crawl_url_id).update(
            using="search",
            crawl_status="indexed",
            document_id=document_id,
            content_hash=extract_content_hash,
            extract_content_hash=extract_content_hash,
            extract_markdown=extract_markdown,
            extract_title=extract_title,
            extract_structural_signals=extract_structural_signals.model_dump(mode="json"),
            enriched_content_hash=enriched_content_hash,
            enrichment_model=enrichment_model,
            enrichment_prompt_version=enrichment_prompt_version,
            fetch_transport=transport,
            fetch_attempts=0,
            next_retry_after=None,
            last_crawled_at=now,
            updated_at=now,
            last_error=None,
        )

    @classmethod
    async def mark_enriched(
        cls,
        crawl_url_id: str,
        *,
        enriched_content_hash: str,
        enrichment_model: str,
        enrichment_prompt_version: str,
        enrichment_snapshot: CrawlUrlEnrichmentSnapshot,
    ) -> None:
        _ = await cls.objects.filter(crawl_url_id=crawl_url_id).update(
            using="search",
            enriched_content_hash=enriched_content_hash,
            enrichment_model=enrichment_model,
            enrichment_prompt_version=enrichment_prompt_version,
            enrichment_snapshot=enrichment_snapshot.model_dump(mode="json"),
            updated_at=datetime.now(UTC),
            last_error=None,
        )

    @classmethod
    async def mark_enrichment_failed(cls, crawl_url_id: str, error: str) -> None:
        _ = await cls.objects.filter(crawl_url_id=crawl_url_id).update(
            using="search",
            last_error=error,
            updated_at=datetime.now(UTC),
        )

    @classmethod
    async def get_layer1_snapshot(
        cls,
        crawl_url_id: str,
    ) -> tuple[str, str, str, str, str, CrawlStructuralSignals]:
        row = await cls.get(crawl_url_id)
        if row is None:
            raise ValueError(f"crawl url not found: {crawl_url_id}")
        if row.extract_markdown is None or row.extract_markdown.strip() == "":
            raise ValueError(f"extract_markdown is missing for crawl_url_id={crawl_url_id}")
        if row.extract_title is None or row.extract_title.strip() == "":
            raise ValueError(f"extract_title is missing for crawl_url_id={crawl_url_id}")
        if row.extract_content_hash is None or row.extract_content_hash.strip() == "":
            raise ValueError(f"extract_content_hash is missing for crawl_url_id={crawl_url_id}")
        signals = row.extract_structural_signals
        if signals is None:
            signals = CrawlStructuralSignals()
        return (
            row.url,
            row.canonical_url,
            row.extract_markdown,
            row.extract_title,
            row.extract_content_hash,
            signals,
        )

    @classmethod
    async def mark_failed(
        cls,
        crawl_url_id: str,
        error: str,
        *,
        retry_base_seconds: int,
        max_attempts: int,
    ) -> None:
        if retry_base_seconds < 1:
            raise ValueError("retry_base_seconds must be >= 1")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        async with atomic(using="search"):
            row = await cls.get(crawl_url_id)
            if row is None:
                raise ValueError(f"crawl url not found: {crawl_url_id}")
            now = datetime.now(UTC)
            attempts = row.fetch_attempts + 1
            next_retry_after: datetime | None = None
            if attempts < max_attempts:
                backoff_seconds = min(retry_base_seconds * (1 << (attempts - 1)), 86400)
                next_retry_after = now + timedelta(seconds=backoff_seconds)
            updated = await cls.objects.filter(
                crawl_url_id=crawl_url_id,
                fetch_attempts=row.fetch_attempts,
            ).update(
                using="search",
                crawl_status="failed",
                last_error=error,
                fetch_attempts=attempts,
                next_retry_after=next_retry_after,
                updated_at=now,
            )
        if updated != 1:
            raise ValueError(f"crawl url not found: {crawl_url_id}")

    @classmethod
    async def mark_skipped(
        cls,
        crawl_url_id: str,
        extract_content_hash: str | None,
        *,
        enriched_content_hash: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        if extract_content_hash is not None and enriched_content_hash is not None:
            _ = await cls.objects.filter(crawl_url_id=crawl_url_id).update(
                using="search",
                crawl_status="skipped",
                updated_at=now,
                last_crawled_at=now,
                fetch_attempts=0,
                next_retry_after=None,
                content_hash=extract_content_hash,
                extract_content_hash=extract_content_hash,
                enriched_content_hash=enriched_content_hash,
            )
            return
        if extract_content_hash is not None:
            _ = await cls.objects.filter(crawl_url_id=crawl_url_id).update(
                using="search",
                crawl_status="skipped",
                updated_at=now,
                last_crawled_at=now,
                fetch_attempts=0,
                next_retry_after=None,
                content_hash=extract_content_hash,
                extract_content_hash=extract_content_hash,
            )
            return
        if enriched_content_hash is not None:
            _ = await cls.objects.filter(crawl_url_id=crawl_url_id).update(
                using="search",
                crawl_status="skipped",
                updated_at=now,
                last_crawled_at=now,
                fetch_attempts=0,
                next_retry_after=None,
                enriched_content_hash=enriched_content_hash,
            )
            return
        _ = await cls.objects.filter(crawl_url_id=crawl_url_id).update(
            using="search",
            crawl_status="skipped",
            updated_at=now,
            last_crawled_at=now,
            fetch_attempts=0,
            next_retry_after=None,
        )

    @classmethod
    async def mark_gone(cls, crawl_url_id: str, *, error: str) -> None:
        """Страница окончательно недоступна: URL выводится из очереди до нового sitemap_lastmod."""
        now = datetime.now(UTC)
        _ = await cls.objects.filter(crawl_url_id=crawl_url_id).update(
            using="search",
            crawl_status="skipped",
            document_id=None,
            last_error=error,
            fetch_attempts=0,
            next_retry_after=None,
            last_crawled_at=now,
            updated_at=now,
        )

    @classmethod
    async def domain_change_stats(
        cls,
        crawl_domain_id: str,
        *,
        since: datetime,
    ) -> tuple[int, int]:
        counts = await CrawlDomain.grouped_counts(
            "SELECT crawl_status AS status, count(*)::int AS total FROM crawl_urls "
            + "WHERE crawl_domain_id = $1 AND crawl_status IN ('indexed', 'skipped') "
            + "AND last_crawled_at IS NOT NULL AND last_crawled_at >= $2 GROUP BY crawl_status",
            [crawl_domain_id, since],
        )
        changed = 0
        unchanged = 0
        for item in counts:
            if item.status == "indexed":
                changed = item.count
            elif item.status == "skipped":
                unchanged = item.count
        return changed, unchanged

    @classmethod
    async def reclaim_stale_fetching(cls, *, stale_before: datetime) -> int:
        return await cls.objects.filter(
            crawl_status="fetching",
            updated_at__lt=stale_before,
        ).update(using="search", crawl_status="pending", updated_at=datetime.now(UTC))

    @classmethod
    async def requeue_failed_urls(cls) -> int:
        now = datetime.now(UTC)
        ready = cls.objects.filter(
            crawl_status="failed",
            next_retry_after__isnull=False,
            next_retry_after__lte=now,
        )
        async with atomic(using="search"):
            ready_count = await ready.count()
            if ready_count == 0:
                return 0
            _ = await ready.update(
                using="search",
                crawl_status="pending",
                last_error=None,
                next_retry_after=None,
                updated_at=now,
            )
        return ready_count

    @classmethod
    async def add_manual_urls(cls, crawl_domain_id: str, urls: list[str]) -> UpsertStats:
        inserted = 0
        updated = 0
        now = datetime.now(UTC)
        async with atomic(using="search"):
            for raw_url in urls:
                canonical = canonicalize_url(raw_url)
                existing = await cls.objects.filter(
                    crawl_domain_id=crawl_domain_id,
                    canonical_url=canonical,
                ).get_or_none()
                if existing is None:
                    _ = await cls.objects.create(
                        instance=cls(
                            crawl_url_id=str(uuid.uuid4()),
                            crawl_domain_id=crawl_domain_id,
                            url=raw_url.strip(),
                            canonical_url=canonical,
                            crawl_status="pending",
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    inserted += 1
                    continue
                existing.crawl_status = "pending"
                existing.fetch_attempts = 0
                existing.next_retry_after = None
                existing.last_error = None
                existing.updated_at = now
                _ = await existing.save()
                updated += 1
        return UpsertStats(inserted=inserted, updated=updated)

    @classmethod
    async def requeue_url(cls, crawl_url_id: str) -> Self:
        row = await cls.get(crawl_url_id)
        if row is None:
            raise ValueError(f"crawl url not found: {crawl_url_id}")
        row.crawl_status = "pending"
        row.fetch_attempts = 0
        row.next_retry_after = None
        row.last_error = None
        row.updated_at = datetime.now(UTC)
        _ = await row.save()
        return row

    @classmethod
    async def requeue_indexed_for_content_recheck(cls, crawl_url_id: str) -> None:
        _ = await cls.objects.filter(
            crawl_url_id=crawl_url_id,
            crawl_status="indexed",
        ).update(using="search", crawl_status="pending", updated_at=datetime.now(UTC))

    @classmethod
    async def list_indexed_missing_enrichment(
        cls,
        crawl_profile_id: str,
        *,
        limit: int,
    ) -> list[str]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        rows = await execute_raw(
            "SELECT crawl_url_id FROM crawl_urls "
            + "JOIN crawl_domains ON crawl_urls.crawl_domain_id = crawl_domains.crawl_domain_id "
            + "WHERE crawl_domains.crawl_profile_id = $1 AND crawl_urls.crawl_status = 'indexed' "
            + "AND crawl_urls.enriched_content_hash IS NULL AND crawl_urls.document_id IS NOT NULL "
            + "AND crawl_urls.extract_markdown IS NOT NULL "
            + "ORDER BY (crawl_urls.last_error IS NOT NULL) DESC, crawl_urls.updated_at LIMIT $2",
            [crawl_profile_id, limit],
            using="search",
        )
        ids: list[str] = []
        for row in rows:
            crawl_url_id = require_json_object(row, "crawl_url")["crawl_url_id"]
            if not isinstance(crawl_url_id, str):
                raise TypeError("crawl_url_id must be str")
            ids.append(crawl_url_id)
        return ids

    @classmethod
    async def requeue_indexed_missing_enrichment(cls, crawl_profile_id: str) -> int:
        crawl_url_ids = await cls.list_indexed_missing_enrichment(crawl_profile_id, limit=10_000)
        return len(crawl_url_ids)

    @classmethod
    async def count_by_status_for_profile(cls, crawl_profile_id: str) -> list[CrawlStatusCount]:
        return await CrawlDomain.grouped_counts(
            "SELECT crawl_urls.crawl_status AS status, count(*)::int AS total FROM crawl_urls "
            + "JOIN crawl_domains ON crawl_urls.crawl_domain_id = crawl_domains.crawl_domain_id "
            + "WHERE crawl_domains.crawl_profile_id = $1 GROUP BY crawl_urls.crawl_status",
            [crawl_profile_id],
        )

    @classmethod
    async def list_page_for_profile(
        cls,
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
        clauses = ["crawl_domains.crawl_profile_id = $1"]
        params: list[str | int | datetime] = [crawl_profile_id]
        if crawl_status is not None:
            params.append(crawl_status)
            clauses.append(f"crawl_urls.crawl_status = ${len(params)}")
        if domain is not None:
            params.append(domain)
            clauses.append(f"crawl_domains.domain = ${len(params)}")
        if content_type is not None:
            params.append(content_type)
            clauses.append(
                "crawl_urls.enrichment_snapshot #>> '{filter_metadata,content_type}' "
                + f"= ${len(params)}"
            )
        if primary_topic is not None:
            params.append(primary_topic)
            clauses.append(
                "crawl_urls.enrichment_snapshot #>> '{filter_metadata,primary_topic}' "
                + f"= ${len(params)}"
            )
        if enriched_only is True:
            clauses.append("crawl_urls.enriched_content_hash IS NOT NULL")
        if enriched_only is False:
            clauses.append("crawl_urls.enriched_content_hash IS NULL")
        where_sql = " AND ".join(clauses)
        total = await CrawlDomain.scalar_count(
            "SELECT count(*)::int AS total FROM crawl_urls "
            + "JOIN crawl_domains ON crawl_urls.crawl_domain_id = crawl_domains.crawl_domain_id "
            + f"WHERE {where_sql}",
            params,
        )
        params.append(limit)
        limit_placeholder = f"${len(params)}"
        params.append(offset)
        offset_placeholder = f"${len(params)}"
        rows = await execute_raw(
            "SELECT row_to_json(crawl_urls) AS url, crawl_domains.domain AS domain FROM crawl_urls "
            + "JOIN crawl_domains ON crawl_urls.crawl_domain_id = crawl_domains.crawl_domain_id "
            + f"WHERE {where_sql} ORDER BY crawl_urls.updated_at DESC "
            + f"LIMIT {limit_placeholder} OFFSET {offset_placeholder}",
            params,
            using="search",
        )
        items: list[CrawlUrlListItem] = []
        for row in rows:
            parsed = require_json_object(row, "crawl_url")
            domain_name = parsed["domain"]
            if not isinstance(domain_name, str):
                raise TypeError("crawl domain must be str")
            items.append(_list_item(_domain_from_url(parsed["url"]), domain_name))
        return OffsetPage[CrawlUrlListItem](items=items, total=total, limit=limit, offset=offset)

    @classmethod
    async def count_enriched_for_profile(cls, crawl_profile_id: str) -> int:
        return await CrawlDomain.scalar_count(
            "SELECT count(*)::int AS total FROM crawl_urls "
            + "JOIN crawl_domains ON crawl_urls.crawl_domain_id = crawl_domains.crawl_domain_id "
            + "WHERE crawl_domains.crawl_profile_id = $1 "
            + "AND crawl_urls.enriched_content_hash IS NOT NULL",
            [crawl_profile_id],
        )

    @classmethod
    async def count_enrichment_pending_for_profile(
        cls,
        crawl_profile_id: str,
        *,
        llm_enrichment_enabled: bool,
    ) -> int:
        if not llm_enrichment_enabled:
            return 0
        return await CrawlDomain.scalar_count(
            "SELECT count(*)::int AS total FROM crawl_urls "
            + "JOIN crawl_domains ON crawl_urls.crawl_domain_id = crawl_domains.crawl_domain_id "
            + "WHERE crawl_domains.crawl_profile_id = $1 AND crawl_urls.crawl_status = 'indexed' "
            + "AND crawl_urls.enriched_content_hash IS NULL",
            [crawl_profile_id],
        )

    @classmethod
    async def count_by_enrichment_content_type(cls, crawl_profile_id: str) -> list[CrawlStatusCount]:
        return await CrawlDomain.grouped_counts(
            "SELECT crawl_urls.enrichment_snapshot #>> '{filter_metadata,content_type}' AS status, "
            + "count(*)::int AS total FROM crawl_urls "
            + "JOIN crawl_domains ON crawl_urls.crawl_domain_id = crawl_domains.crawl_domain_id "
            + "WHERE crawl_domains.crawl_profile_id = $1 AND crawl_urls.enrichment_snapshot IS NOT NULL "
            + "AND crawl_urls.enrichment_snapshot #>> '{filter_metadata,content_type}' IS NOT NULL "
            + "GROUP BY 1 ORDER BY count(*) DESC LIMIT 12",
            [crawl_profile_id],
        )

    @classmethod
    async def count_by_enrichment_primary_topic(cls, crawl_profile_id: str) -> list[CrawlStatusCount]:
        return await CrawlDomain.grouped_counts(
            "SELECT crawl_urls.enrichment_snapshot #>> '{filter_metadata,primary_topic}' AS status, "
            + "count(*)::int AS total FROM crawl_urls "
            + "JOIN crawl_domains ON crawl_urls.crawl_domain_id = crawl_domains.crawl_domain_id "
            + "WHERE crawl_domains.crawl_profile_id = $1 AND crawl_urls.enrichment_snapshot IS NOT NULL "
            + "AND crawl_urls.enrichment_snapshot #>> '{filter_metadata,primary_topic}' IS NOT NULL "
            + "GROUP BY 1 ORDER BY count(*) DESC LIMIT 12",
            [crawl_profile_id],
        )

    @classmethod
    async def get_for_profile(
        cls,
        crawl_url_id: str,
        crawl_profile_id: str,
    ) -> tuple[CrawlUrlListItem, str | None, str | None]:
        rows = await execute_raw(
            "SELECT row_to_json(crawl_urls) AS url, crawl_domains.domain AS domain FROM crawl_urls "
            + "JOIN crawl_domains ON crawl_urls.crawl_domain_id = crawl_domains.crawl_domain_id "
            + "WHERE crawl_urls.crawl_url_id = $1 AND crawl_domains.crawl_profile_id = $2",
            [crawl_url_id, crawl_profile_id],
            using="search",
        )
        if len(rows) == 0:
            raise ValueError(f"crawl url not found: crawl_url_id={crawl_url_id}")
        parsed = require_json_object(rows[0], "crawl_url")
        domain_name = parsed["domain"]
        if not isinstance(domain_name, str):
            raise TypeError("crawl domain must be str")
        url = _domain_from_url(parsed["url"])
        return _list_item(url, domain_name), url.extract_title, url.extract_markdown

class CrawlUrlListItem(CrawlUrl):
    domain: str
    structural_signals: CrawlStructuralSignals = Field(default_factory=CrawlStructuralSignals)
    enrichment_snapshot: CrawlUrlEnrichmentSnapshot | None = None

class CrawlUrlIndexedContent(StrictBaseModel):
    document_id: str
    document_name: str
    markdown: str
    page_summary: str | None = None
    llm_enriched: bool = False
    chunks_count: int
    filter_metadata: CrawlPageFilterMetadata | None = None
    metadata: RAGMetadata = Field(default_factory=dict)

class CrawlUrlDetail(StrictBaseModel):
    url: CrawlUrlListItem
    extract_title: str | None = None
    extract_markdown: str | None = None
    indexed_content: CrawlUrlIndexedContent | None = None

def _list_item(url: CrawlUrl, domain: str) -> CrawlUrlListItem:
    signals = url.extract_structural_signals
    if signals is None:
        signals = CrawlStructuralSignals()
    return CrawlUrlListItem.model_validate(
        {
            **url.model_dump(),
            "domain": domain,
            "structural_signals": signals.model_dump(mode="json"),
            "enrichment_snapshot": (
                None
                if url.enrichment_snapshot is None
                else url.enrichment_snapshot.model_dump(mode="json")
            ),
        }
    )

def _domain_from_url(raw: JsonValue) -> CrawlUrl:
    if isinstance(raw, str):
        payload = parse_json_object(raw, "crawl_url")
    else:
        payload = require_json_object(raw, "crawl_url")
    return CrawlUrl.model_validate(payload)
