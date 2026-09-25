"""Crawl and index pipeline DTOs."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from typing import ClassVar, Literal, Self, TypedDict
from urllib.parse import urlsplit, urlunsplit

from oxyde import F, Index, atomic, execute_raw
from oxyde import Field as DbField
from pydantic import Field, field_validator

from core.models import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.pagination import OffsetPage
from core.rag.models import RAGMetadata
from core.search.index_models import SearchIndexDefinition
from core.types import JsonValue, parse_json_object, require_json_object

CrawlJobTrigger = Literal["scheduler", "manual", "api"]
CrawlJobStatus = Literal["running", "completed", "failed"]
CrawlDomainStatus = Literal["active", "paused", "blocked", "error"]
CrawlUrlStatus = Literal["pending", "fetching", "indexed", "failed", "skipped"]
CrawlSeedSource = Literal["tranco", "manual", "cloudflare_radar"]
CrawlFetchTransport = Literal["http", "browser"]

CrawlContentType = Literal[
    "article",
    "news",
    "blog",
    "product",
    "documentation",
    "tutorial",
    "guide",
    "faq",
    "review",
    "interview",
    "opinion",
    "press_release",
    "research",
    "case_study",
    "changelog",
    "support",
    "catalog",
    "landing",
    "reference",
    "wiki",
    "tool",
    "forum",
    "legal",
    "event",
    "recipe",
    "obituary",
    "report",
    "transcript",
    "directory",
    "portfolio",
    "other",
]

CrawlPageAudience = Literal["general", "professional", "developer", "consumer", "internal"]

# Дефолтные фильтры обхода: служебные пути и бинарные расширения, бесполезные для индекса.
DEFAULT_CRAWL_EXCLUDE_URL_PATTERNS: list[str] = [r"/(cart|checkout|login|auth|search)(/|$)"]
DEFAULT_CRAWL_EXCLUDE_EXTENSIONS: list[str] = ["pdf", "zip", "jpg", "jpeg", "png", "gif"]

CrawlPageFreshnessRelevance = Literal["evergreen", "time_sensitive", "archival"]

CrawlDatePrecision = Literal["day", "month", "year"]


class SitemapEntry(StrictBaseModel):
    url: str
    lastmod: datetime | None = None


class CrawlStructuralSignals(StrictBaseModel):
    title: str | None = None
    description: str | None = None
    date_published: date | None = None
    date_modified: date | None = None
    author: str | None = None
    publisher: str | None = None
    og_image_url: str | None = None
    language: str | None = None
    content_type_hint: CrawlContentType | None = None
    category_hints: list[str] = Field(default_factory=list)
    topic_hints: list[str] = Field(default_factory=list)


class CrawlFetchResult(StrictBaseModel):
    url: str
    canonical_url: str
    markdown: str
    title: str
    heading_trail: list[str] = Field(default_factory=list)
    content_hash: str
    fetch_transport: CrawlFetchTransport = "http"
    structural_signals: CrawlStructuralSignals = Field(default_factory=CrawlStructuralSignals)


class CrawlPageFilterMetadata(StrictBaseModel):
    content_type: CrawlContentType
    date_published: date | None = None
    date_modified: date | None = None
    date_precision: CrawlDatePrecision | None = None
    primary_topic: str = Field(..., min_length=1, max_length=64)
    topic_tags: list[str] = Field(..., min_length=2, max_length=5)
    category_path: list[str] = Field(default_factory=list, max_length=3)
    language: str = Field(..., min_length=2, max_length=8)
    audience: CrawlPageAudience
    freshness_relevance: CrawlPageFreshnessRelevance | None = None

    @field_validator("topic_tags")
    @classmethod
    def _topic_tags_sorted_unique(cls, topic_tags: list[str]) -> list[str]:
        normalized: list[str] = []
        for tag in topic_tags:
            token = tag.strip().lower()
            if not token:
                raise ValueError("topic_tags must not contain empty values")
            if token not in normalized:
                normalized.append(token)
        normalized.sort()
        if len(normalized) < 2:
            raise ValueError("topic_tags must contain at least 2 unique items")
        return normalized

    @field_validator("category_path")
    @classmethod
    def _category_path_normalized(cls, category_path: list[str]) -> list[str]:
        if not category_path:
            return []
        normalized = [segment.strip().lower() for segment in category_path if segment.strip()]
        if not normalized:
            raise ValueError("category_path must not contain only empty segments")
        if len(normalized) > 3:
            raise ValueError("category_path must have at most 3 levels")
        return normalized


class CrawlPageRetrievalAugment(StrictBaseModel):
    contextual_prefix: str = Field(..., min_length=20, max_length=2000)
    answerable_questions: list[str] = Field(..., min_length=3, max_length=7)
    lexical_keywords: list[str] = Field(..., min_length=5, max_length=12)
    entity_names: list[str] = Field(default_factory=list, max_length=10)


class CrawlEnrichedChunk(StrictBaseModel):
    hierarchy: list[str] = Field(default_factory=list)
    body: str = Field(..., min_length=1)
    filter_metadata: CrawlPageFilterMetadata
    retrieval_augment: CrawlPageRetrievalAugment


class CrawlEnrichedPageLLMOutput(StrictBaseModel):
    page_title: str = Field(..., min_length=1)
    page_summary: str = Field(..., min_length=1)
    chunks: list[CrawlEnrichedChunk] = Field(..., min_length=1, max_length=1)
    extraction_notes: list[str] = Field(default_factory=list, max_length=3)


class CrawlEnrichedPage(StrictBaseModel):
    page_title: str
    page_summary: str
    chunks: list[CrawlEnrichedChunk]
    extraction_notes: list[str] = Field(default_factory=list)
    enrichment_model: str
    enrichment_prompt_version: str

    @field_validator("chunks")
    @classmethod
    def _chunks_not_empty(cls, chunks: list[CrawlEnrichedChunk]) -> list[CrawlEnrichedChunk]:
        if not chunks:
            raise ValueError("chunks must not be empty")
        return chunks

    @classmethod
    def from_llm_output(
        cls,
        output: CrawlEnrichedPageLLMOutput,
        *,
        enrichment_model: str,
        enrichment_prompt_version: str,
    ) -> CrawlEnrichedPage:
        return cls(
            page_title=output.page_title,
            page_summary=output.page_summary,
            chunks=output.chunks,
            extraction_notes=output.extraction_notes,
            enrichment_model=enrichment_model,
            enrichment_prompt_version=enrichment_prompt_version,
        )

    def to_ingest_markdown(self) -> str:
        chunk = self.chunks[0]
        filter_metadata = chunk.filter_metadata
        retrieval_augment = chunk.retrieval_augment
        topic_line = ", ".join(filter_metadata.topic_tags)
        lines: list[str] = [
            retrieval_augment.contextual_prefix.strip(),
            "",
            f"## {self.page_title.strip()}",
            f"*{self.page_summary.strip()}*",
            "",
            "### Topics",
            f"{filter_metadata.primary_topic} · {topic_line}",
            "",
            "### Content",
            chunk.body.strip(),
            "",
            "### Questions this page answers",
        ]
        for index, question in enumerate(retrieval_augment.answerable_questions, start=1):
            lines.append(f"{index}. {question.strip()}")
        lines.extend(
            [
                "",
                "### Keywords",
                ", ".join(keyword.strip() for keyword in retrieval_augment.lexical_keywords),
            ]
        )
        return "\n".join(lines).strip()


class CrawlIngestPayload(StrictBaseModel):
    fetched: CrawlFetchResult
    enriched_page: CrawlEnrichedPage | None = None

    @property
    def ingest_markdown(self) -> str:
        if self.enriched_page is not None:
            return self.enriched_page.to_ingest_markdown()
        return self.fetched.markdown

    @property
    def ingest_title(self) -> str:
        if self.enriched_page is not None:
            return self.enriched_page.page_title
        return self.fetched.title


class CrawlDomainSeed(StrictBaseModel):
    domain: str
    domain_rank: int | None = None
    category: str = "unknown"



def _normalize_domain(domain: str) -> str:
    value = domain.strip().lower()
    if value.startswith("http://") or value.startswith("https://"):
        value = urlsplit(value).netloc.lower()
    if value.startswith("www."):
        value = value[4:]
    if not value:
        raise ValueError("domain is required")
    return value


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"invalid url: {url}")
    path = parsed.path.rstrip("/") or parsed.path
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


class CrawlProfile(PlatformModel):
    """Профиль обхода. Таблица ``crawl_profiles``."""

    __database_alias__: ClassVar[str | None] = "search"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "crawl_profiles"
        indexes: list[Index] = [
            Index(["search_index_id"]),
        ]

    crawl_profile_id: str = DbField(db_pk=True, max_length=64)
    search_index_id: str = DbField(max_length=64)
    seed_source: str = DbField(max_length=32)
    refresh_interval_seconds: int = DbField()
    max_urls_per_domain_per_tick: int = DbField()
    max_domains_per_tick: int = DbField()
    max_urls_per_batch: int = DbField()
    http_concurrency: int = DbField()
    browser_fallback_enabled: bool = DbField()
    sitemap_stale_after_seconds: int = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    enabled: bool = DbField(default=True)
    denylist_domains: list[str] = DbField(default_factory=list, db_type="JSONB")
    include_url_patterns: list[str] = DbField(default_factory=list, db_type="JSONB")
    exclude_url_patterns: list[str] = DbField(default_factory=list, db_type="JSONB")
    exclude_extensions: list[str] = DbField(default_factory=list, db_type="JSONB")
    llm_enrichment_enabled: bool = DbField(default=False)
    enrichment_model: str | None = DbField(default=None, max_length=128)

    @classmethod
    async def get_with_index(cls, crawl_profile_id: str) -> CrawlProfileWithIndex:
        profile = await cls.objects.filter(crawl_profile_id=crawl_profile_id).get_or_none()
        if profile is None:
            raise ValueError(f"crawl profile not found: {crawl_profile_id}")
        search_index = await SearchIndexDefinition.objects.filter(
            search_index_id=profile.search_index_id,
        ).get_or_none()
        if search_index is None:
            raise ValueError(f"search index not found: {profile.search_index_id}")
        return CrawlProfileWithIndex(profile=profile, search_index=search_index)

    @classmethod
    async def create(cls, body: CrawlProfileCreateRequest) -> CrawlProfileWithIndex:
        now = datetime.now(UTC)
        _ = await cls.objects.create(
            instance=cls(
                crawl_profile_id=body.crawl_profile_id,
                search_index_id=body.search_index_id,
                enabled=body.enabled,
                seed_source=body.seed_source,
                refresh_interval_seconds=body.refresh_interval_seconds,
                max_urls_per_domain_per_tick=body.max_urls_per_domain_per_tick,
                max_domains_per_tick=body.max_domains_per_tick,
                max_urls_per_batch=body.max_urls_per_batch,
                http_concurrency=body.http_concurrency,
                browser_fallback_enabled=body.browser_fallback_enabled,
                sitemap_stale_after_seconds=body.sitemap_stale_after_seconds,
                denylist_domains=list(body.denylist_domains),
                include_url_patterns=list(body.include_url_patterns),
                exclude_url_patterns=list(body.exclude_url_patterns),
                exclude_extensions=list(body.exclude_extensions),
                created_at=now,
                updated_at=now,
            )
        )
        return await cls.get_with_index(body.crawl_profile_id)

    @classmethod
    async def patch(
        cls,
        crawl_profile_id: str,
        body: CrawlProfilePatchRequest,
    ) -> CrawlProfileWithIndex:
        profile = await cls.objects.filter(crawl_profile_id=crawl_profile_id).get_or_none()
        if profile is None:
            raise ValueError(f"crawl profile not found: {crawl_profile_id}")
        if body.enabled is not None:
            profile.enabled = body.enabled
        if body.refresh_interval_seconds is not None:
            profile.refresh_interval_seconds = body.refresh_interval_seconds
        if body.max_urls_per_domain_per_tick is not None:
            profile.max_urls_per_domain_per_tick = body.max_urls_per_domain_per_tick
        if body.max_domains_per_tick is not None:
            profile.max_domains_per_tick = body.max_domains_per_tick
        if body.max_urls_per_batch is not None:
            profile.max_urls_per_batch = body.max_urls_per_batch
        if body.http_concurrency is not None:
            profile.http_concurrency = body.http_concurrency
        if body.browser_fallback_enabled is not None:
            profile.browser_fallback_enabled = body.browser_fallback_enabled
        if body.sitemap_stale_after_seconds is not None:
            profile.sitemap_stale_after_seconds = body.sitemap_stale_after_seconds
        if body.denylist_domains is not None:
            profile.denylist_domains = list(body.denylist_domains)
        if body.include_url_patterns is not None:
            profile.include_url_patterns = list(body.include_url_patterns)
        if body.exclude_url_patterns is not None:
            profile.exclude_url_patterns = list(body.exclude_url_patterns)
        if body.exclude_extensions is not None:
            profile.exclude_extensions = list(body.exclude_extensions)
        if body.llm_enrichment_enabled is not None:
            profile.llm_enrichment_enabled = body.llm_enrichment_enabled
            profile.enrichment_model = body.enrichment_model
        profile.updated_at = datetime.now(UTC)
        _ = await profile.save()
        return await cls.get_with_index(crawl_profile_id)

    @classmethod
    async def list_page(cls, *, limit: int, offset: int) -> OffsetPage[CrawlProfileWithIndex]:
        total = await cls.objects.count()
        rows = await (
            cls.objects.order_by("crawl_profile_id").limit(limit).offset(offset).all()
        )
        items = [await cls.get_with_index(row.crawl_profile_id) for row in rows]
        return OffsetPage[CrawlProfileWithIndex](items=items, total=total, limit=limit, offset=offset)

    @classmethod
    async def set_llm_enrichment(
        cls,
        crawl_profile_id: str,
        *,
        llm_enrichment_enabled: bool,
        enrichment_model: str | None,
    ) -> None:
        profile = await cls.objects.filter(crawl_profile_id=crawl_profile_id).get_or_none()
        if profile is None:
            raise ValueError(f"crawl profile not found: {crawl_profile_id}")
        profile.llm_enrichment_enabled = llm_enrichment_enabled
        profile.enrichment_model = enrichment_model
        profile.updated_at = datetime.now(UTC)
        _ = await profile.save()




class CrawlProfileWithIndex(StrictBaseModel):
    profile: CrawlProfile
    search_index: SearchIndexDefinition


class CrawlProfileCreateRequest(StrictBaseModel):
    crawl_profile_id: str = Field(..., min_length=1, max_length=64)
    search_index_id: str = Field(..., min_length=1, max_length=64)
    seed_source: CrawlSeedSource = "manual"
    enabled: bool = True
    refresh_interval_seconds: int = Field(default=21600, ge=60)
    max_urls_per_domain_per_tick: int = Field(default=10, ge=1)
    max_domains_per_tick: int = Field(default=10, ge=1)
    max_urls_per_batch: int = Field(default=10, ge=1)
    http_concurrency: int = Field(default=2, ge=1)
    browser_fallback_enabled: bool = True
    sitemap_stale_after_seconds: int = Field(default=86400, ge=3600)
    denylist_domains: list[str] = Field(default_factory=list)
    include_url_patterns: list[str] = Field(default_factory=list)
    exclude_url_patterns: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CRAWL_EXCLUDE_URL_PATTERNS)
    )
    exclude_extensions: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CRAWL_EXCLUDE_EXTENSIONS)
    )


class CrawlProfilePatchRequest(StrictBaseModel):
    enabled: bool | None = None
    refresh_interval_seconds: int | None = Field(default=None, ge=60)
    max_urls_per_domain_per_tick: int | None = Field(default=None, ge=1)
    max_domains_per_tick: int | None = Field(default=None, ge=1)
    max_urls_per_batch: int | None = Field(default=None, ge=1)
    http_concurrency: int | None = Field(default=None, ge=1)
    browser_fallback_enabled: bool | None = None
    sitemap_stale_after_seconds: int | None = Field(default=None, ge=3600)
    denylist_domains: list[str] | None = None
    include_url_patterns: list[str] | None = None
    exclude_url_patterns: list[str] | None = None
    exclude_extensions: list[str] | None = None
    llm_enrichment_enabled: bool | None = None
    enrichment_model: str | None = None


class CrawlDomain(PlatformModel):
    """Домен обхода. Таблица ``crawl_domains``."""

    __database_alias__: ClassVar[str | None] = "search"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "crawl_domains"
        unique_together: list[tuple[str, str]] = [("crawl_profile_id", "domain")]
        indexes: list[Index] = [
            Index(["crawl_profile_id", "status", "next_crawl_after"]),
        ]

    @field_validator(
        "next_crawl_after",
        "created_at",
        "updated_at",
        "last_discovered_at",
        "last_crawled_at",
        mode="after",
    )
    @classmethod
    def _bind_utc(cls, value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)

    crawl_domain_id: str = DbField(db_pk=True, max_length=36)
    crawl_profile_id: str = DbField(max_length=64)
    domain: str = DbField(max_length=255)
    category: str = DbField(max_length=32)
    status: CrawlDomainStatus = DbField(db_type="TEXT")
    next_crawl_after: datetime = DbField()
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    domain_rank: int | None = DbField(default=None)
    refresh_interval_seconds: int | None = DbField(default=None)
    include_url_patterns: list[str] = DbField(default_factory=list, db_type="JSONB")
    exclude_url_patterns: list[str] = DbField(default_factory=list, db_type="JSONB")
    last_discovered_at: datetime | None = DbField(default=None)
    last_crawled_at: datetime | None = DbField(default=None)
    last_error: str | None = DbField(default=None, db_type="TEXT")

    @classmethod
    async def upsert_seed_batch(
        cls,
        crawl_profile_id: str,
        seeds: list[CrawlDomainSeed],
        *,
        next_crawl_after: datetime,
    ) -> int:
        if len(seeds) == 0:
            return 0
        now = datetime.now(UTC)
        inserted = 0
        async with atomic(using="search"):
            for seed in seeds:
                domain = _normalize_domain(seed.domain)
                existing = await cls.objects.filter(
                    crawl_profile_id=crawl_profile_id,
                    domain=domain,
                ).get_or_none()
                if existing is not None:
                    continue
                _ = await cls.objects.create(
                    instance=cls(
                        crawl_domain_id=str(uuid.uuid4()),
                        crawl_profile_id=crawl_profile_id,
                        domain=domain,
                        domain_rank=seed.domain_rank,
                        category=seed.category,
                        status="active",
                        next_crawl_after=next_crawl_after,
                        created_at=now,
                        updated_at=now,
                    )
                )
                inserted += 1
        return inserted

    @classmethod
    async def create(
        cls,
        crawl_profile_id: str,
        body: CrawlDomainCreateRequest,
        *,
        next_crawl_after: datetime,
    ) -> Self:
        domain = _normalize_domain(body.domain)
        now = datetime.now(UTC)
        existing = await cls.objects.filter(
            crawl_profile_id=crawl_profile_id,
            domain=domain,
        ).get_or_none()
        if existing is not None:
            raise ValueError(f"crawl domain already exists: {domain}")
        return await cls.objects.create(
            instance=cls(
                crawl_domain_id=str(uuid.uuid4()),
                crawl_profile_id=crawl_profile_id,
                domain=domain,
                domain_rank=None,
                category=body.category,
                status="active",
                refresh_interval_seconds=body.refresh_interval_seconds,
                next_crawl_after=next_crawl_after,
                created_at=now,
                updated_at=now,
            )
        )

    @classmethod
    async def patch(cls, crawl_domain_id: str, body: CrawlDomainPatchRequest) -> Self:
        row = await cls.objects.filter(crawl_domain_id=crawl_domain_id).get_or_none()
        if row is None:
            raise ValueError(f"crawl domain not found: {crawl_domain_id}")
        if body.status is not None:
            row.status = body.status
        if body.refresh_interval_seconds is not None:
            row.refresh_interval_seconds = body.refresh_interval_seconds
        if body.include_url_patterns is not None:
            row.include_url_patterns = list(body.include_url_patterns)
        if body.exclude_url_patterns is not None:
            row.exclude_url_patterns = list(body.exclude_url_patterns)
        row.updated_at = datetime.now(UTC)
        _ = await row.save()
        return row

    @classmethod
    async def count_for_profile(cls, crawl_profile_id: str) -> int:
        return await cls.objects.filter(crawl_profile_id=crawl_profile_id).count()

    @classmethod
    async def list_due(
        cls,
        crawl_profile_id: str,
        *,
        now: datetime,
        limit: int,
    ) -> list[Self]:
        return await (
            cls.objects.filter(
                crawl_profile_id=crawl_profile_id,
                status="active",
                next_crawl_after__lte=now,
            )
            .order_by("next_crawl_after")
            .limit(limit)
            .all()
        )

    @classmethod
    async def list_with_pending_urls(
        cls,
        crawl_profile_id: str,
        *,
        limit: int,
    ) -> list[CrawlDomain]:
        rows = await execute_raw(
            "SELECT row_to_json(crawl_domains) AS domain FROM crawl_domains "
            + "JOIN (SELECT crawl_domain_id, count(*) AS pending_count FROM crawl_urls "
            + "WHERE crawl_status = 'pending' GROUP BY crawl_domain_id) pending "
            + "ON crawl_domains.crawl_domain_id = pending.crawl_domain_id "
            + "WHERE crawl_profile_id = $1 AND status = 'active' "
            + "ORDER BY pending.pending_count DESC, domain LIMIT $2",
            [crawl_profile_id, limit],
            using="search",
        )
        return [_domain_from_json(require_json_object(row, "crawl_domain")["domain"]) for row in rows]

    @classmethod
    async def mark_discovered(cls, crawl_domain_id: str, discovered_at: datetime) -> None:
        _ = await cls.objects.filter(crawl_domain_id=crawl_domain_id).update(
            using="search",
            last_discovered_at=discovered_at,
            updated_at=datetime.now(UTC),
            last_error=None,
        )

    @classmethod
    async def mark_crawled(cls, crawl_domain_id: str, crawled_at: datetime) -> None:
        _ = await cls.objects.filter(crawl_domain_id=crawl_domain_id).update(
            using="search",
            last_crawled_at=crawled_at,
            updated_at=datetime.now(UTC),
            last_error=None,
        )

    @classmethod
    async def schedule_next(
        cls,
        crawl_domain_id: str,
        next_crawl_after: datetime,
        *,
        last_error: str | None = None,
        status: CrawlDomainStatus | None = None,
    ) -> None:
        now = datetime.now(UTC)
        query = cls.objects.filter(crawl_domain_id=crawl_domain_id)
        if last_error is not None and status is not None:
            _ = await query.update(
                using="search",
                next_crawl_after=next_crawl_after,
                updated_at=now,
                last_error=last_error,
                status=status,
            )
            return
        if last_error is not None:
            _ = await query.update(
                using="search",
                next_crawl_after=next_crawl_after,
                updated_at=now,
                last_error=last_error,
            )
            return
        if status is not None:
            _ = await query.update(
                using="search",
                next_crawl_after=next_crawl_after,
                updated_at=now,
                status=status,
            )
            return
        _ = await query.update(
            using="search",
            next_crawl_after=next_crawl_after,
            updated_at=now,
        )

    @classmethod
    async def list_page(
        cls,
        *,
        crawl_profile_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlDomain]:
        rows = cls.objects.filter(crawl_profile_id=crawl_profile_id)
        if status is not None:
            rows = rows.filter(status=status)
        total = await rows.count()
        items = await rows.order_by("domain").limit(limit).offset(offset).all()
        return OffsetPage[CrawlDomain](items=list(items), total=total, limit=limit, offset=offset)

    @classmethod
    async def count_by_status(cls, crawl_profile_id: str) -> list[CrawlStatusCount]:
        return await CrawlDomain.grouped_counts(
            "SELECT status, count(*)::int AS total FROM crawl_domains "
            + "WHERE crawl_profile_id = $1 GROUP BY status",
            [crawl_profile_id],
        )

    @classmethod
    async def count_due(cls, crawl_profile_id: str, *, now: datetime) -> int:
        return await cls.objects.filter(
            crawl_profile_id=crawl_profile_id,
            status="active",
            next_crawl_after__lte=now,
        ).count()

    @classmethod
    async def scalar_count(cls, sql: str, params: list[str | int | datetime]) -> int:
        rows = await execute_raw(sql, params, using="search")
        total = require_json_object(rows[0], "crawl_count")["total"]
        if isinstance(total, bool) or not isinstance(total, int):
            raise TypeError("crawl count must be int")
        return total

    @classmethod
    async def grouped_counts(
        cls, sql: str, params: list[str | int | datetime]
    ) -> list[CrawlStatusCount]:
        rows = await execute_raw(sql, params, using="search")
        counts: list[CrawlStatusCount] = []
        for row in rows:
            parsed = require_json_object(row, "crawl_count")
            status = parsed["status"]
            total = parsed["total"]
            if not isinstance(status, str) or status.strip() == "":
                raise TypeError("crawl status must be str")
            if isinstance(total, bool) or not isinstance(total, int):
                raise TypeError("crawl count must be int")
            counts.append(CrawlStatusCount(status=status.strip(), count=total))
        return counts


class CrawlDomainCreateRequest(StrictBaseModel):
    domain: str = Field(..., min_length=1, max_length=255)
    category: str = Field(default="manual", min_length=1, max_length=32)
    refresh_interval_seconds: int | None = Field(default=None, ge=60)
    seed_urls: list[str] = Field(default_factory=list, max_length=500)


class CrawlDomainPatchRequest(StrictBaseModel):
    status: CrawlDomainStatus | None = None
    refresh_interval_seconds: int | None = Field(default=None, ge=60)
    include_url_patterns: list[str] | None = None
    exclude_url_patterns: list[str] | None = None


class CrawlUrlAddRequest(StrictBaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=500)


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




class CrawlJob(PlatformModel):
    """Запуск обхода. Таблица ``crawl_jobs``."""

    __database_alias__: ClassVar[str | None] = "search"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "crawl_jobs"
        indexes: list[Index] = [
            Index(["crawl_profile_id", "status"]),
            Index(["crawl_profile_id", "started_at"]),
        ]

    crawl_job_id: str = DbField(db_pk=True, max_length=36)
    crawl_profile_id: str = DbField(max_length=64)
    trigger: CrawlJobTrigger = DbField(db_type="TEXT")
    status: CrawlJobStatus = DbField(db_type="TEXT")
    started_at: datetime = DbField()
    schedule_task_id: str | None = DbField(default=None, max_length=255)
    domains_scheduled: int = DbField(default=0)
    urls_discovered: int = DbField(default=0)
    urls_fetched: int = DbField(default=0)
    urls_indexed: int = DbField(default=0)
    urls_skipped: int = DbField(default=0)
    urls_enriched: int = DbField(default=0)
    urls_enrichment_failed: int = DbField(default=0)
    errors: int = DbField(default=0)
    finished_at: datetime | None = DbField(default=None)

    @classmethod
    async def start(
        cls,
        crawl_profile_id: str,
        trigger: CrawlJobTrigger,
        schedule_task_id: str | None,
    ) -> Self:
        now = datetime.now(UTC)
        return await cls.objects.create(
            instance=cls(
                crawl_job_id=str(uuid.uuid4()),
                crawl_profile_id=crawl_profile_id,
                trigger=trigger,
                schedule_task_id=schedule_task_id,
                status="running",
                started_at=now,
            )
        )

    @classmethod
    async def increment(
        cls,
        crawl_job_id: str,
        *,
        urls_discovered: int = 0,
        urls_fetched: int = 0,
        urls_indexed: int = 0,
        urls_skipped: int = 0,
        urls_enriched: int = 0,
        urls_enrichment_failed: int = 0,
        errors: int = 0,
        domains_scheduled: int = 0,
    ) -> None:
        updated = await cls.objects.filter(crawl_job_id=crawl_job_id).update(
            using="search",
            urls_discovered=F("urls_discovered") + urls_discovered,
            urls_fetched=F("urls_fetched") + urls_fetched,
            urls_indexed=F("urls_indexed") + urls_indexed,
            urls_skipped=F("urls_skipped") + urls_skipped,
            urls_enriched=F("urls_enriched") + urls_enriched,
            urls_enrichment_failed=F("urls_enrichment_failed") + urls_enrichment_failed,
            errors=F("errors") + errors,
            domains_scheduled=F("domains_scheduled") + domains_scheduled,
        )
        if updated != 1:
            raise ValueError(f"crawl job not found: {crawl_job_id}")

    @classmethod
    async def finish(cls, crawl_job_id: str, *, status: CrawlJobStatus) -> Self:
        row = await cls.get(crawl_job_id)
        if row is None:
            raise ValueError(f"crawl job not found: {crawl_job_id}")
        row.status = status
        row.finished_at = datetime.now(UTC)
        _ = await row.save()
        return row

    @classmethod
    async def active_for_profile(cls, crawl_profile_id: str) -> Self | None:
        return await (
            cls.objects.filter(crawl_profile_id=crawl_profile_id, status="running")
            .order_by("-started_at")
            .first()
        )

    @classmethod
    async def latest_for_profile(cls, crawl_profile_id: str) -> Self | None:
        return await (
            cls.objects.filter(crawl_profile_id=crawl_profile_id)
            .order_by("-started_at")
            .first()
        )

    @classmethod
    async def finish_stale_running_jobs(cls, *, stale_before: datetime) -> int:
        return await cls.objects.filter(
            status="running",
            started_at__lt=stale_before,
        ).update(using="search", status="failed", finished_at=datetime.now(UTC))

    @classmethod
    async def list_page(
        cls,
        *,
        crawl_profile_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlJob]:
        rows = cls.objects.filter(crawl_profile_id=crawl_profile_id)
        if status is not None:
            rows = rows.filter(status=status)
        total = await rows.count()
        items = await rows.order_by("-started_at").limit(limit).offset(offset).all()
        return OffsetPage[CrawlJob](items=list(items), total=total, limit=limit, offset=offset)


class CrawlJobCreateRequest(StrictBaseModel):
    crawl_profile_id: str = Field(..., min_length=1, max_length=64)
    trigger: CrawlJobTrigger = "manual"


class CrawlJobQueuedResponse(StrictBaseModel):
    crawl_profile_id: str
    status: str


class CrawlDomainRunResponse(StrictBaseModel):
    crawl_domain_id: str
    crawl_job_id: str
    crawl_profile_id: str
    action: Literal["discover", "fetch"]
    status: str


class SeedImportRequest(StrictBaseModel):
    crawl_profile_id: str
    seed_source: CrawlSeedSource = "tranco"
    tranco_limit: int = Field(default=2000, ge=1, le=5000)
    mode: Literal["append"] = "append"


class SeedImportResult(StrictBaseModel):
    imported: int
    skipped: int


CrawlBootstrapAction = Literal["queued_seed", "skipped_seed", "bootstrap_disabled"]


class CrawlBootstrapResult(StrictBaseModel):
    crawl_profile_id: str
    action: CrawlBootstrapAction
    domain_count: int


class UpsertStats(StrictBaseModel):
    inserted: int
    updated: int


class CrawlOrchestratorTickResult(TypedDict):
    crawl_job_id: str
    crawl_profile_id: str
    domains_scheduled: int
    status: str


class CrawlStatusCount(StrictBaseModel):
    status: str
    count: int


class CrawlProfileSummary(StrictBaseModel):
    profile: CrawlProfileWithIndex
    domain_counts: list[CrawlStatusCount]
    url_counts: list[CrawlStatusCount]
    domains_total: int
    domains_due: int
    latest_job: CrawlJob | None = None
    running_job: CrawlJob | None = None
    content_type_counts: list[CrawlStatusCount] = Field(default_factory=list)
    primary_topic_counts: list[CrawlStatusCount] = Field(default_factory=list)
    urls_enriched_total: int = 0
    urls_enrichment_pending: int = 0


class CrawlUrlEnrichmentSnapshot(StrictBaseModel):
    page_title: str = Field(..., min_length=1)
    page_summary: str | None = None
    filter_metadata: CrawlPageFilterMetadata


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


def _domain_from_json(raw: JsonValue) -> CrawlDomain:
    if isinstance(raw, str):
        payload = parse_json_object(raw, "crawl_domain")
    else:
        payload = require_json_object(raw, "crawl_domain")
    return CrawlDomain.model_validate(payload)


def _domain_from_url(raw: JsonValue) -> CrawlUrl:
    if isinstance(raw, str):
        payload = parse_json_object(raw, "crawl_url")
    else:
        payload = require_json_object(raw, "crawl_url")
    return CrawlUrl.model_validate(payload)


