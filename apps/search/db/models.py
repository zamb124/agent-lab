"""SQLAlchemy models for platform_search."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SearchIndexRow(Base):
    __tablename__: str = "search_indexes"

    search_index_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rag_namespace_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rag_collection_id: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    search_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieval_semantic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieval_lexical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieval_rerank: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retrieval_rrf_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieval_per_channel_top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snippet_max_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    indexing_profile_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CrawlProfileRow(Base):
    __tablename__: str = "crawl_profiles"

    crawl_profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    search_index_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("search_indexes.search_index_id", ondelete="RESTRICT"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    seed_source: Mapped[str] = mapped_column(String(32), nullable=False)
    refresh_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=21600)
    max_urls_per_domain_per_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    max_domains_per_tick: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_urls_per_batch: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    http_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    browser_fallback_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sitemap_stale_after_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=86400)
    denylist_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    llm_enrichment_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enrichment_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CrawlDomainRow(Base):
    __tablename__: str = "crawl_domains"
    __table_args__: tuple[UniqueConstraint, ...] = (
        UniqueConstraint("crawl_profile_id", "domain", name="uq_crawl_domains_profile_domain"),
    )

    crawl_domain_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    crawl_profile_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("crawl_profiles.crawl_profile_id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    domain_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    crawl_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="sitemap_only")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    last_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_crawl_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CrawlUrlRow(Base):
    __tablename__: str = "crawl_urls"
    __table_args__: tuple[UniqueConstraint, ...] = (
        UniqueConstraint("crawl_domain_id", "canonical_url", name="uq_crawl_urls_domain_canonical"),
    )

    crawl_url_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    crawl_domain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("crawl_domains.crawl_domain_id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    sitemap_lastmod: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extract_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enriched_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enrichment_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enrichment_prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    crawl_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    fetch_transport: Mapped[str | None] = mapped_column(String(16), nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extract_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    extract_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CrawlJobRow(Base):
    __tablename__: str = "crawl_jobs"

    crawl_job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    crawl_profile_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("crawl_profiles.crawl_profile_id", ondelete="CASCADE"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    schedule_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    domains_scheduled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urls_discovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urls_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urls_indexed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urls_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urls_enriched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urls_enrichment_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
