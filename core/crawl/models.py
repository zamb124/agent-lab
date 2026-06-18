"""Crawl and index pipeline DTOs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, TypedDict

from pydantic import Field, field_validator

from core.models import StrictBaseModel
from core.rag.models import RAGMetadata
from core.search.index_models import SearchIndexDefinition

CrawlJobTrigger = Literal["scheduler", "manual", "api"]
CrawlJobStatus = Literal["running", "completed", "failed"]
CrawlDomainStatus = Literal["active", "paused", "blocked", "error"]
CrawlUrlStatus = Literal["pending", "fetching", "indexed", "failed", "skipped"]
CrawlSeedSource = Literal["tranco", "manual", "cloudflare_radar"]
CrawlFetchTransport = Literal["http", "browser"]

CrawlContentTypeHint = Literal[
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

CrawlPageContentType = Literal[
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

CrawlPageFreshnessRelevance = Literal["evergreen", "time_sensitive", "archival"]

CrawlDatePrecision = Literal["day", "month", "year"]


class SitemapEntry(StrictBaseModel):
    url: str
    lastmod: datetime | None = None


class CrawlStructuralSignals(StrictBaseModel):
    title: str | None = None
    date_published: date | None = None
    date_modified: date | None = None
    author: str | None = None
    publisher: str | None = None
    language: str | None = None
    content_type_hint: CrawlContentTypeHint | None = None
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
    content_type: CrawlPageContentType
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


class CrawlProfile(StrictBaseModel):
    crawl_profile_id: str
    search_index_id: str
    enabled: bool
    seed_source: str
    refresh_interval_seconds: int
    max_urls_per_domain_per_tick: int
    max_domains_per_tick: int
    max_urls_per_batch: int
    http_concurrency: int
    browser_fallback_enabled: bool
    sitemap_stale_after_seconds: int
    denylist_domains: list[str] = Field(default_factory=list)
    llm_enrichment_enabled: bool = False
    enrichment_model: str | None = None
    created_at: datetime
    updated_at: datetime


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


class CrawlDomain(StrictBaseModel):
    crawl_domain_id: str
    crawl_profile_id: str
    domain: str
    domain_rank: int | None = None
    category: str
    crawl_policy: str
    status: CrawlDomainStatus
    last_discovered_at: datetime | None = None
    last_crawled_at: datetime | None = None
    next_crawl_after: datetime
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class CrawlUrl(StrictBaseModel):
    crawl_url_id: str
    crawl_domain_id: str
    url: str
    canonical_url: str
    sitemap_lastmod: datetime | None = None
    content_hash: str | None = None
    extract_content_hash: str | None = None
    enriched_content_hash: str | None = None
    enrichment_model: str | None = None
    enrichment_prompt_version: str | None = None
    crawl_status: CrawlUrlStatus
    fetch_transport: CrawlFetchTransport | None = None
    document_id: str | None = None
    last_error: str | None = None
    last_crawled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CrawlJob(StrictBaseModel):
    crawl_job_id: str
    crawl_profile_id: str
    trigger: CrawlJobTrigger
    schedule_task_id: str | None = None
    status: CrawlJobStatus
    domains_scheduled: int = 0
    urls_discovered: int = 0
    urls_fetched: int = 0
    urls_indexed: int = 0
    urls_skipped: int = 0
    urls_enriched: int = 0
    urls_enrichment_failed: int = 0
    errors: int = 0
    started_at: datetime
    finished_at: datetime | None = None


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
