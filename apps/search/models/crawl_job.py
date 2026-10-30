"""Таблица краула."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import ClassVar, Self

from oxyde import F, Index
from oxyde import Field as DbField
from pydantic import Field

from core.crawl.models.contracts import (
    CrawlJobStatus,
    CrawlJobTrigger,
    CrawlStatusCount,
)
from core.crawl.models.crawl_profile import CrawlProfileWithIndex
from core.errors.boundary import PlatformNotFoundError
from core.models import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.pagination import OffsetPage


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
            raise PlatformNotFoundError(f"crawl job not found: {crawl_job_id}")

    @classmethod
    async def finish(cls, crawl_job_id: str, *, status: CrawlJobStatus) -> Self:
        row = await cls.get(crawl_job_id)
        if row is None:
            raise PlatformNotFoundError(f"crawl job not found: {crawl_job_id}")
        row.status = status
        row.finished_at = datetime.now(UTC)
        _ = await row.save()
        return row

    @classmethod
    async def active_for_profile_by_started_at_desc(cls, crawl_profile_id: str) -> Self | None:
        """Последний running job профиля, ORDER BY started_at DESC. Несколько с одним started_at — какой именно, не задано. Нет строки — None."""
        return await (
            cls.objects.filter(crawl_profile_id=crawl_profile_id, status="running")
            .order_by("-started_at")
            .first()
        )

    @classmethod
    async def latest_for_profile_by_started_at_desc(cls, crawl_profile_id: str) -> Self | None:
        """Последний job профиля, ORDER BY started_at DESC. Несколько с одним started_at — какой именно, не задано. Нет строки — None."""
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
    async def page_by_started_at_desc(
        cls,
        *,
        crawl_profile_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlJob]:
        """Страница запусков профиля, ORDER BY started_at DESC. status равный None не фильтрует. total — COUNT этого фильтра."""
        rows = cls.objects.filter(crawl_profile_id=crawl_profile_id)
        if status is not None:
            rows = rows.filter(status=status)
        total = await rows.count()
        items = await rows.order_by("-started_at").limit(limit).offset(offset).all()
        return OffsetPage[CrawlJob](items=list(items), total=total, limit=limit, offset=offset)

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
