"""Таблица краула."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, atomic, execute_raw
from pydantic import field_validator

from core.crawl.models.contracts import (
    CrawlDomainCreateRequest,
    CrawlDomainPatchRequest,
    CrawlDomainSeed,
    CrawlDomainStatus,
    CrawlStatusCount,
    normalize_domain,
)
from core.errors.boundary import PlatformNotFoundError
from core.models.platform_model import PlatformModel
from core.pagination import OffsetPage
from core.types import JsonValue, parse_json_object, require_json_object


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
                domain = normalize_domain(seed.domain)
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
        domain = normalize_domain(body.domain)
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
            raise PlatformNotFoundError(f"crawl domain not found: {crawl_domain_id}")
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
            + "ORDER BY pending.pending_count DESC, crawl_domains.domain LIMIT $2",
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
    async def page_by_domain(
        cls,
        *,
        crawl_profile_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlDomain]:
        """Страница доменов профиля, ORDER BY domain. status равный None не фильтрует. total — COUNT этого фильтра."""
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

def _domain_from_json(raw: JsonValue) -> CrawlDomain:
    if isinstance(raw, str):
        payload = parse_json_object(raw, "crawl_domain")
    else:
        payload = require_json_object(raw, "crawl_domain")
    return CrawlDomain.model_validate(payload)
