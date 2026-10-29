"""Таблица краула."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index

from core.crawl.models.contracts import (
    CrawlProfileCreateRequest,
    CrawlProfilePatchRequest,
)
from core.errors.boundary import PlatformNotFoundError
from core.models import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.pagination import OffsetPage
from core.search.index_models import SearchIndexDefinition


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
    async def require_with_index(cls, crawl_profile_id: str) -> CrawlProfileWithIndex:
        profile = await cls.objects.filter(crawl_profile_id=crawl_profile_id).get_or_none()
        if profile is None:
            raise PlatformNotFoundError(f"crawl profile not found: {crawl_profile_id}")
        search_index = await SearchIndexDefinition.objects.filter(
            search_index_id=profile.search_index_id,
        ).get_or_none()
        if search_index is None:
            raise PlatformNotFoundError(f"search index not found: {profile.search_index_id}")
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
        return await cls.require_with_index(body.crawl_profile_id)

    @classmethod
    async def patch_with_index(
        cls,
        crawl_profile_id: str,
        body: CrawlProfilePatchRequest,
    ) -> CrawlProfileWithIndex:
        """Частичная запись полей patch. Поле None не пишется, кроме enrichment_model: он пишется, когда llm_enrichment_enabled is not None. Нет профиля — PlatformNotFoundError. Возврат — require_with_index."""
        profile = await cls.objects.filter(crawl_profile_id=crawl_profile_id).get_or_none()
        if profile is None:
            raise PlatformNotFoundError(f"crawl profile not found: {crawl_profile_id}")
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
        return await cls.require_with_index(crawl_profile_id)

    @classmethod
    async def with_index_page_by_crawl_profile_id_asc(
        cls, *, limit: int, offset: int
    ) -> OffsetPage[CrawlProfileWithIndex]:
        """Страница всех профилей с индексом, ORDER BY crawl_profile_id ASC. total — COUNT всех профилей."""
        total = await cls.objects.count()
        rows = await (
            cls.objects.order_by("crawl_profile_id").limit(limit).offset(offset).all()
        )
        items = [await cls.require_with_index(row.crawl_profile_id) for row in rows]
        return OffsetPage[CrawlProfileWithIndex](items=items, total=total, limit=limit, offset=offset)

    @classmethod
    async def update_llm_enrichment_enabled_and_model(
        cls,
        crawl_profile_id: str,
        *,
        llm_enrichment_enabled: bool,
        enrichment_model: str | None,
    ) -> None:
        """Пишет llm_enrichment_enabled, enrichment_model и updated_at. None в enrichment_model записывается. Нет профиля — PlatformNotFoundError."""
        profile = await cls.objects.filter(crawl_profile_id=crawl_profile_id).get_or_none()
        if profile is None:
            raise PlatformNotFoundError(f"crawl profile not found: {crawl_profile_id}")
        profile.llm_enrichment_enabled = llm_enrichment_enabled
        profile.enrichment_model = enrichment_model
        profile.updated_at = datetime.now(UTC)
        _ = await profile.save()

class CrawlProfileWithIndex(StrictBaseModel):
    profile: CrawlProfile
    search_index: SearchIndexDefinition
