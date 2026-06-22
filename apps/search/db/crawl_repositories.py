"""Crawl state repositories."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, select, update
from sqlalchemy.sql.elements import ColumnElement

from apps.search.db.base import SearchDatabase
from apps.search.db.models import (
    CrawlDomainRow,
    CrawlJobRow,
    CrawlProfileRow,
    CrawlUrlRow,
    SearchIndexRow,
)
from apps.search.db.search_index_repository import search_index_row_to_definition
from core.crawl.models import (
    CrawlDomain,
    CrawlDomainCreateRequest,
    CrawlDomainPatchRequest,
    CrawlDomainSeed,
    CrawlDomainStatus,
    CrawlJob,
    CrawlJobStatus,
    CrawlJobTrigger,
    CrawlProfile,
    CrawlProfileCreateRequest,
    CrawlProfilePatchRequest,
    CrawlProfileWithIndex,
    CrawlStatusCount,
    CrawlStructuralSignals,
    CrawlUrl,
    CrawlUrlEnrichmentSnapshot,
    CrawlUrlListItem,
    CrawlUrlStatus,
    SitemapEntry,
    UpsertStats,
)
from core.db.utils import get_rowcount
from core.pagination import OffsetPage


def _enrichment_snapshot_text(*json_path: str) -> ColumnElement[str]:
    node: object = CrawlUrlRow.enrichment_snapshot
    for key in json_path:
        node = node[key]
    return cast(ColumnElement[str], getattr(node, "astext"))


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


def _parse_crawl_domain_status(value: str) -> CrawlDomainStatus:
    match value:
        case "active" | "paused" | "blocked" | "error":
            return value
        case _:
            raise ValueError(f"invalid crawl domain status: {value}")


def _parse_crawl_url_status(value: str) -> CrawlUrlStatus:
    match value:
        case "pending" | "fetching" | "indexed" | "failed" | "skipped":
            return value
        case _:
            raise ValueError(f"invalid crawl url status: {value}")


def _parse_crawl_job_trigger(value: str) -> CrawlJobTrigger:
    match value:
        case "scheduler" | "manual" | "api":
            return value
        case _:
            raise ValueError(f"invalid crawl job trigger: {value}")


def _parse_crawl_job_status(value: str) -> CrawlJobStatus:
    match value:
        case "running" | "completed" | "failed":
            return value
        case _:
            raise ValueError(f"invalid crawl job status: {value}")


def _profile_row_to_model(row: CrawlProfileRow) -> CrawlProfile:
    return CrawlProfile(
        crawl_profile_id=row.crawl_profile_id,
        search_index_id=row.search_index_id,
        enabled=row.enabled,
        seed_source=row.seed_source,
        refresh_interval_seconds=row.refresh_interval_seconds,
        max_urls_per_domain_per_tick=row.max_urls_per_domain_per_tick,
        max_domains_per_tick=row.max_domains_per_tick,
        max_urls_per_batch=row.max_urls_per_batch,
        http_concurrency=row.http_concurrency,
        browser_fallback_enabled=row.browser_fallback_enabled,
        sitemap_stale_after_seconds=row.sitemap_stale_after_seconds,
        denylist_domains=list(row.denylist_domains),
        include_url_patterns=list(row.include_url_patterns),
        exclude_url_patterns=list(row.exclude_url_patterns),
        exclude_extensions=list(row.exclude_extensions),
        llm_enrichment_enabled=row.llm_enrichment_enabled,
        enrichment_model=row.enrichment_model,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _domain_row_to_model(row: CrawlDomainRow) -> CrawlDomain:
    return CrawlDomain(
        crawl_domain_id=row.crawl_domain_id,
        crawl_profile_id=row.crawl_profile_id,
        domain=row.domain,
        domain_rank=row.domain_rank,
        category=row.category,
        status=_parse_crawl_domain_status(row.status),
        refresh_interval_seconds=row.refresh_interval_seconds,
        include_url_patterns=list(row.include_url_patterns),
        exclude_url_patterns=list(row.exclude_url_patterns),
        last_discovered_at=row.last_discovered_at,
        last_crawled_at=row.last_crawled_at,
        next_crawl_after=row.next_crawl_after,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _structural_signals_from_row(row: CrawlUrlRow) -> CrawlStructuralSignals:
    raw_signals = row.extract_structural_signals
    if raw_signals is None:
        return CrawlStructuralSignals()
    return CrawlStructuralSignals.model_validate(raw_signals)


def _url_row_to_model(row: CrawlUrlRow) -> CrawlUrl:
    fetch_transport: str | None = row.fetch_transport
    parsed_fetch_transport = None
    if fetch_transport == "http" or fetch_transport == "browser":
        parsed_fetch_transport = fetch_transport
    return CrawlUrl(
        crawl_url_id=row.crawl_url_id,
        crawl_domain_id=row.crawl_domain_id,
        url=row.url,
        canonical_url=row.canonical_url,
        sitemap_lastmod=row.sitemap_lastmod,
        content_hash=row.content_hash,
        extract_content_hash=row.extract_content_hash,
        enriched_content_hash=row.enriched_content_hash,
        enrichment_model=row.enrichment_model,
        enrichment_prompt_version=row.enrichment_prompt_version,
        crawl_status=_parse_crawl_url_status(row.crawl_status),
        fetch_transport=parsed_fetch_transport,
        document_id=row.document_id,
        fetch_attempts=row.fetch_attempts,
        next_retry_after=row.next_retry_after,
        last_error=row.last_error,
        last_crawled_at=row.last_crawled_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _enrichment_snapshot_from_row(row: CrawlUrlRow) -> CrawlUrlEnrichmentSnapshot | None:
    raw_snapshot = row.enrichment_snapshot
    if raw_snapshot is None:
        return None
    return CrawlUrlEnrichmentSnapshot.model_validate(raw_snapshot)


def _crawl_url_list_item_from_row(url_row: CrawlUrlRow, domain: str) -> CrawlUrlListItem:
    url_model = _url_row_to_model(url_row)
    return CrawlUrlListItem(
        crawl_url_id=url_model.crawl_url_id,
        crawl_domain_id=url_model.crawl_domain_id,
        url=url_model.url,
        canonical_url=url_model.canonical_url,
        sitemap_lastmod=url_model.sitemap_lastmod,
        content_hash=url_model.content_hash,
        extract_content_hash=url_model.extract_content_hash,
        enriched_content_hash=url_model.enriched_content_hash,
        enrichment_model=url_model.enrichment_model,
        enrichment_prompt_version=url_model.enrichment_prompt_version,
        crawl_status=url_model.crawl_status,
        fetch_transport=url_model.fetch_transport,
        document_id=url_model.document_id,
        fetch_attempts=url_model.fetch_attempts,
        next_retry_after=url_model.next_retry_after,
        last_error=url_model.last_error,
        last_crawled_at=url_model.last_crawled_at,
        created_at=url_model.created_at,
        updated_at=url_model.updated_at,
        domain=domain,
        structural_signals=_structural_signals_from_row(url_row),
        enrichment_snapshot=_enrichment_snapshot_from_row(url_row),
    )


def _job_row_to_model(row: CrawlJobRow) -> CrawlJob:
    return CrawlJob(
        crawl_job_id=row.crawl_job_id,
        crawl_profile_id=row.crawl_profile_id,
        trigger=_parse_crawl_job_trigger(row.trigger),
        schedule_task_id=row.schedule_task_id,
        status=_parse_crawl_job_status(row.status),
        domains_scheduled=row.domains_scheduled,
        urls_discovered=row.urls_discovered,
        urls_fetched=row.urls_fetched,
        urls_indexed=row.urls_indexed,
        urls_skipped=row.urls_skipped,
        urls_enriched=row.urls_enriched,
        urls_enrichment_failed=row.urls_enrichment_failed,
        errors=row.errors,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


class CrawlProfileRepository:
    def __init__(self, db: SearchDatabase) -> None:
        self._db: SearchDatabase = db

    async def get_with_index(self, crawl_profile_id: str) -> CrawlProfileWithIndex:
        async with self._db.session() as session:
            stmt = (
                select(CrawlProfileRow, SearchIndexRow)
                .join(SearchIndexRow, CrawlProfileRow.search_index_id == SearchIndexRow.search_index_id)
                .where(CrawlProfileRow.crawl_profile_id == crawl_profile_id)
            )
            row = (await session.execute(stmt)).one_or_none()
        if row is None:
            raise ValueError(f"crawl profile not found: {crawl_profile_id}")
        profile_row = cast(CrawlProfileRow, row[0])
        index_row = cast(SearchIndexRow, row[1])
        return CrawlProfileWithIndex(
            profile=_profile_row_to_model(profile_row),
            search_index=search_index_row_to_definition(index_row),
        )

    async def create(self, body: CrawlProfileCreateRequest) -> CrawlProfileWithIndex:
        now = datetime.now(UTC)
        row = CrawlProfileRow(
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
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
        return await self.get_with_index(body.crawl_profile_id)

    async def patch(
        self,
        crawl_profile_id: str,
        body: CrawlProfilePatchRequest,
    ) -> CrawlProfileWithIndex:
        values: dict[str, object] = {}
        if body.enabled is not None:
            values["enabled"] = body.enabled
        if body.refresh_interval_seconds is not None:
            values["refresh_interval_seconds"] = body.refresh_interval_seconds
        if body.max_urls_per_domain_per_tick is not None:
            values["max_urls_per_domain_per_tick"] = body.max_urls_per_domain_per_tick
        if body.max_domains_per_tick is not None:
            values["max_domains_per_tick"] = body.max_domains_per_tick
        if body.max_urls_per_batch is not None:
            values["max_urls_per_batch"] = body.max_urls_per_batch
        if body.http_concurrency is not None:
            values["http_concurrency"] = body.http_concurrency
        if body.browser_fallback_enabled is not None:
            values["browser_fallback_enabled"] = body.browser_fallback_enabled
        if body.sitemap_stale_after_seconds is not None:
            values["sitemap_stale_after_seconds"] = body.sitemap_stale_after_seconds
        if body.denylist_domains is not None:
            values["denylist_domains"] = list(body.denylist_domains)
        if body.include_url_patterns is not None:
            values["include_url_patterns"] = list(body.include_url_patterns)
        if body.exclude_url_patterns is not None:
            values["exclude_url_patterns"] = list(body.exclude_url_patterns)
        if body.exclude_extensions is not None:
            values["exclude_extensions"] = list(body.exclude_extensions)
        if body.llm_enrichment_enabled is not None:
            values["llm_enrichment_enabled"] = body.llm_enrichment_enabled
            values["enrichment_model"] = body.enrichment_model
        if not values:
            return await self.get_with_index(crawl_profile_id)
        values["updated_at"] = datetime.now(UTC)
        async with self._db.session() as session:
            stmt = (
                update(CrawlProfileRow)
                .where(CrawlProfileRow.crawl_profile_id == crawl_profile_id)
                .values(**values)
            )
            result = await session.execute(stmt)
            if get_rowcount(result) == 0:
                raise ValueError(f"crawl profile not found: {crawl_profile_id}")
            await session.commit()
        return await self.get_with_index(crawl_profile_id)

    async def list_page(self, *, limit: int, offset: int) -> OffsetPage[CrawlProfileWithIndex]:
        async with self._db.session() as session:
            count_stmt = select(func.count()).select_from(CrawlProfileRow)
            total = int((await session.execute(count_stmt)).scalar_one())
            stmt = select(CrawlProfileRow.crawl_profile_id).order_by(CrawlProfileRow.crawl_profile_id)
            stmt = stmt.limit(limit).offset(offset)
            ids = list((await session.execute(stmt)).scalars().all())
        items = [await self.get_with_index(crawl_profile_id) for crawl_profile_id in ids]
        return OffsetPage[CrawlProfileWithIndex](items=items, total=total, limit=limit, offset=offset)

    async def set_llm_enrichment(
        self,
        crawl_profile_id: str,
        *,
        llm_enrichment_enabled: bool,
        enrichment_model: str | None,
    ) -> None:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            stmt = (
                update(CrawlProfileRow)
                .where(CrawlProfileRow.crawl_profile_id == crawl_profile_id)
                .values(
                    llm_enrichment_enabled=llm_enrichment_enabled,
                    enrichment_model=enrichment_model,
                    updated_at=now,
                )
            )
            result = await session.execute(stmt)
            if get_rowcount(result) == 0:
                raise ValueError(f"crawl profile not found: {crawl_profile_id}")
            await session.commit()


class CrawlDomainRepository:
    def __init__(self, db: SearchDatabase) -> None:
        self._db: SearchDatabase = db

    async def upsert_seed_batch(
        self,
        crawl_profile_id: str,
        seeds: list[CrawlDomainSeed],
        *,
        next_crawl_after: datetime,
    ) -> int:
        if not seeds:
            return 0
        now = datetime.now(UTC)
        inserted = 0
        async with self._db.session() as session:
            for seed in seeds:
                domain = _normalize_domain(seed.domain)
                stmt = select(CrawlDomainRow).where(
                    CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                    CrawlDomainRow.domain == domain,
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing is not None:
                    continue
                session.add(
                    CrawlDomainRow(
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
            await session.commit()
        return inserted

    async def create(
        self,
        crawl_profile_id: str,
        body: CrawlDomainCreateRequest,
        *,
        next_crawl_after: datetime,
    ) -> CrawlDomain:
        domain = _normalize_domain(body.domain)
        now = datetime.now(UTC)
        async with self._db.session() as session:
            existing_stmt = select(CrawlDomainRow).where(
                CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                CrawlDomainRow.domain == domain,
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing is not None:
                raise ValueError(f"crawl domain already exists: {domain}")
            row = CrawlDomainRow(
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
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return _domain_row_to_model(row)

    async def patch(self, crawl_domain_id: str, body: CrawlDomainPatchRequest) -> CrawlDomain:
        values: dict[str, object] = {}
        if body.status is not None:
            values["status"] = body.status
        if body.refresh_interval_seconds is not None:
            values["refresh_interval_seconds"] = body.refresh_interval_seconds
        if body.include_url_patterns is not None:
            values["include_url_patterns"] = list(body.include_url_patterns)
        if body.exclude_url_patterns is not None:
            values["exclude_url_patterns"] = list(body.exclude_url_patterns)
        if values:
            values["updated_at"] = datetime.now(UTC)
            async with self._db.session() as session:
                stmt = (
                    update(CrawlDomainRow)
                    .where(CrawlDomainRow.crawl_domain_id == crawl_domain_id)
                    .values(**values)
                )
                result = await session.execute(stmt)
                if get_rowcount(result) == 0:
                    raise ValueError(f"crawl domain not found: {crawl_domain_id}")
                await session.commit()
        return await self.get(crawl_domain_id)

    async def delete(self, crawl_domain_id: str) -> None:
        async with self._db.session() as session:
            stmt = select(CrawlDomainRow).where(CrawlDomainRow.crawl_domain_id == crawl_domain_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ValueError(f"crawl domain not found: {crawl_domain_id}")
            await session.delete(row)
            await session.commit()

    async def count_for_profile(self, crawl_profile_id: str) -> int:
        async with self._db.session() as session:
            stmt = select(func.count()).where(CrawlDomainRow.crawl_profile_id == crawl_profile_id)
            return int((await session.execute(stmt)).scalar_one())

    async def list_due(
        self,
        crawl_profile_id: str,
        *,
        now: datetime,
        limit: int,
    ) -> list[CrawlDomain]:
        async with self._db.session() as session:
            stmt = (
                select(CrawlDomainRow)
                .where(
                    CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                    CrawlDomainRow.status == "active",
                    CrawlDomainRow.next_crawl_after <= now,
                )
                .order_by(CrawlDomainRow.next_crawl_after)
                .limit(limit)
            )
            rows = list((await session.execute(stmt)).scalars().all())
        return [_domain_row_to_model(row) for row in rows]

    async def list_with_pending_urls(
        self,
        crawl_profile_id: str,
        *,
        limit: int,
    ) -> list[CrawlDomain]:
        pending_by_domain = (
            select(
                CrawlUrlRow.crawl_domain_id,
                func.count(CrawlUrlRow.crawl_url_id).label("pending_count"),
            )
            .where(CrawlUrlRow.crawl_status == "pending")
            .group_by(CrawlUrlRow.crawl_domain_id)
            .subquery()
        )
        async with self._db.session() as session:
            stmt = (
                select(CrawlDomainRow)
                .join(
                    pending_by_domain,
                    CrawlDomainRow.crawl_domain_id == pending_by_domain.c.crawl_domain_id,
                )
                .where(
                    CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                    CrawlDomainRow.status == "active",
                )
                .order_by(pending_by_domain.c.pending_count.desc(), CrawlDomainRow.domain)
                .limit(limit)
            )
            rows = list((await session.execute(stmt)).scalars().all())
        return [_domain_row_to_model(row) for row in rows]

    async def mark_discovered(self, crawl_domain_id: str, discovered_at: datetime) -> None:
        async with self._db.session() as session:
            stmt = (
                update(CrawlDomainRow)
                .where(CrawlDomainRow.crawl_domain_id == crawl_domain_id)
                .values(last_discovered_at=discovered_at, updated_at=datetime.now(UTC), last_error=None)
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def mark_crawled(self, crawl_domain_id: str, crawled_at: datetime) -> None:
        async with self._db.session() as session:
            stmt = (
                update(CrawlDomainRow)
                .where(CrawlDomainRow.crawl_domain_id == crawl_domain_id)
                .values(last_crawled_at=crawled_at, updated_at=datetime.now(UTC), last_error=None)
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def schedule_next(
        self,
        crawl_domain_id: str,
        next_crawl_after: datetime,
        *,
        last_error: str | None = None,
        status: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "next_crawl_after": next_crawl_after,
            "updated_at": datetime.now(UTC),
        }
        if last_error is not None:
            values["last_error"] = last_error
        if status is not None:
            values["status"] = status
        async with self._db.session() as session:
            stmt = update(CrawlDomainRow).where(CrawlDomainRow.crawl_domain_id == crawl_domain_id).values(**values)
            _ = await session.execute(stmt)
            await session.commit()

    async def get(self, crawl_domain_id: str) -> CrawlDomain:
        async with self._db.session() as session:
            stmt = select(CrawlDomainRow).where(CrawlDomainRow.crawl_domain_id == crawl_domain_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise ValueError(f"crawl domain not found: {crawl_domain_id}")
        return _domain_row_to_model(row)

    async def list_page(
        self,
        *,
        crawl_profile_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlDomain]:
        async with self._db.session() as session:
            base = select(CrawlDomainRow).where(CrawlDomainRow.crawl_profile_id == crawl_profile_id)
            if status is not None:
                base = base.where(CrawlDomainRow.status == status)
            count_stmt = select(func.count()).select_from(base.subquery())
            total = int((await session.execute(count_stmt)).scalar_one())
            stmt = base.order_by(CrawlDomainRow.domain).limit(limit).offset(offset)
            rows = list((await session.execute(stmt)).scalars().all())
        return OffsetPage[CrawlDomain](
            items=[_domain_row_to_model(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def count_by_status(self, crawl_profile_id: str) -> list[CrawlStatusCount]:
        async with self._db.session() as session:
            stmt = (
                select(CrawlDomainRow.status, func.count())
                .where(CrawlDomainRow.crawl_profile_id == crawl_profile_id)
                .group_by(CrawlDomainRow.status)
            )
            rows: Sequence[tuple[str, int]] = (await session.execute(stmt)).tuples().all()
        status_counts: list[CrawlStatusCount] = []
        for status_cell, count_cell in rows:
            status_counts.append(CrawlStatusCount(status=status_cell, count=count_cell))
        return status_counts

    async def count_due(self, crawl_profile_id: str, *, now: datetime) -> int:
        async with self._db.session() as session:
            stmt = select(func.count()).where(
                CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                CrawlDomainRow.status == "active",
                CrawlDomainRow.next_crawl_after <= now,
            )
            return int((await session.execute(stmt)).scalar_one())


class CrawlUrlRepository:
    def __init__(self, db: SearchDatabase) -> None:
        self._db: SearchDatabase = db

    async def get(self, crawl_url_id: str) -> CrawlUrl:
        async with self._db.session() as session:
            stmt = select(CrawlUrlRow).where(CrawlUrlRow.crawl_url_id == crawl_url_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise ValueError(f"crawl url not found: {crawl_url_id}")
        return _url_row_to_model(row)

    async def upsert_from_sitemap(
        self,
        crawl_domain_id: str,
        entries: list[SitemapEntry],
    ) -> UpsertStats:
        inserted = 0
        updated = 0
        now = datetime.now(UTC)
        async with self._db.session() as session:
            for entry in entries:
                canonical = canonicalize_url(entry.url)
                stmt = select(CrawlUrlRow).where(
                    CrawlUrlRow.crawl_domain_id == crawl_domain_id,
                    CrawlUrlRow.canonical_url == canonical,
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing is None:
                    session.add(
                        CrawlUrlRow(
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
                existing.sitemap_lastmod = entry.lastmod
                existing.updated_at = now
                updated += 1
            await session.commit()
        return UpsertStats(inserted=inserted, updated=updated)

    async def count_pending(self, crawl_domain_id: str) -> int:
        async with self._db.session() as session:
            stmt = select(func.count()).where(
                CrawlUrlRow.crawl_domain_id == crawl_domain_id,
                CrawlUrlRow.crawl_status == "pending",
            )
            return int((await session.execute(stmt)).scalar_one())

    async def count_pending_for_profile(self, crawl_profile_id: str) -> int:
        async with self._db.session() as session:
            stmt = (
                select(func.count())
                .select_from(CrawlUrlRow)
                .join(
                    CrawlDomainRow,
                    CrawlUrlRow.crawl_domain_id == CrawlDomainRow.crawl_domain_id,
                )
                .where(
                    CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                    CrawlUrlRow.crawl_status == "pending",
                )
            )
            return int((await session.execute(stmt)).scalar_one())

    async def claim_pending_batch(self, crawl_domain_id: str, limit: int) -> list[CrawlUrl]:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            select_stmt = (
                select(CrawlUrlRow.crawl_url_id)
                .where(
                    CrawlUrlRow.crawl_domain_id == crawl_domain_id,
                    CrawlUrlRow.crawl_status == "pending",
                )
                .order_by(CrawlUrlRow.created_at)
                .limit(limit)
            )
            ids = list((await session.execute(select_stmt)).scalars().all())
            if not ids:
                return []
            update_stmt = (
                update(CrawlUrlRow)
                .where(CrawlUrlRow.crawl_url_id.in_(ids))
                .values(crawl_status="fetching", updated_at=now)
            )
            _ = await session.execute(update_stmt)
            await session.commit()
            rows_stmt = select(CrawlUrlRow).where(CrawlUrlRow.crawl_url_id.in_(ids))
            rows = list((await session.execute(rows_stmt)).scalars().all())
        return [_url_row_to_model(row) for row in rows]

    async def mark_indexed(
        self,
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
        async with self._db.session() as session:
            stmt = (
                update(CrawlUrlRow)
                .where(CrawlUrlRow.crawl_url_id == crawl_url_id)
                .values(
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
                    fetch_transport=fetch_transport,
                    fetch_attempts=0,
                    next_retry_after=None,
                    last_crawled_at=now,
                    updated_at=now,
                    last_error=None,
                )
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def mark_enriched(
        self,
        crawl_url_id: str,
        *,
        enriched_content_hash: str,
        enrichment_model: str,
        enrichment_prompt_version: str,
        enrichment_snapshot: CrawlUrlEnrichmentSnapshot,
    ) -> None:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            stmt = (
                update(CrawlUrlRow)
                .where(CrawlUrlRow.crawl_url_id == crawl_url_id)
                .values(
                    enriched_content_hash=enriched_content_hash,
                    enrichment_model=enrichment_model,
                    enrichment_prompt_version=enrichment_prompt_version,
                    enrichment_snapshot=enrichment_snapshot.model_dump(mode="json"),
                    updated_at=now,
                    last_error=None,
                )
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def mark_enrichment_failed(self, crawl_url_id: str, error: str) -> None:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            stmt = (
                update(CrawlUrlRow)
                .where(CrawlUrlRow.crawl_url_id == crawl_url_id)
                .values(last_error=error, updated_at=now)
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def get_layer1_snapshot(
        self,
        crawl_url_id: str,
    ) -> tuple[str, str, str, str, str, CrawlStructuralSignals]:
        async with self._db.session() as session:
            stmt = select(CrawlUrlRow).where(CrawlUrlRow.crawl_url_id == crawl_url_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise ValueError(f"crawl url not found: {crawl_url_id}")
        if row.extract_markdown is None or not row.extract_markdown.strip():
            raise ValueError(f"extract_markdown is missing for crawl_url_id={crawl_url_id}")
        if row.extract_title is None or not row.extract_title.strip():
            raise ValueError(f"extract_title is missing for crawl_url_id={crawl_url_id}")
        if row.extract_content_hash is None or not row.extract_content_hash.strip():
            raise ValueError(f"extract_content_hash is missing for crawl_url_id={crawl_url_id}")
        return (
            row.url,
            row.canonical_url,
            row.extract_markdown,
            row.extract_title,
            row.extract_content_hash,
            _structural_signals_from_row(row),
        )

    async def mark_failed(
        self,
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
        now = datetime.now(UTC)
        async with self._db.session() as session:
            row_stmt = select(CrawlUrlRow).where(CrawlUrlRow.crawl_url_id == crawl_url_id)
            row = (await session.execute(row_stmt)).scalar_one_or_none()
            if row is None:
                raise ValueError(f"crawl url not found: {crawl_url_id}")
            attempts = row.fetch_attempts + 1
            next_retry_after: datetime | None = None
            if attempts < max_attempts:
                # Экспоненциальный backoff с потолком в 24 часа.
                backoff_seconds: int = min(retry_base_seconds * (1 << (attempts - 1)), 86400)
                next_retry_after = now + timedelta(seconds=backoff_seconds)
            row.crawl_status = "failed"
            row.last_error = error
            row.fetch_attempts = attempts
            row.next_retry_after = next_retry_after
            row.updated_at = now
            await session.commit()

    async def mark_skipped(
        self,
        crawl_url_id: str,
        extract_content_hash: str | None,
        *,
        enriched_content_hash: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        values: dict[str, object] = {
            "crawl_status": "skipped",
            "updated_at": now,
            "last_crawled_at": now,
            "fetch_attempts": 0,
            "next_retry_after": None,
        }
        if extract_content_hash is not None:
            values["content_hash"] = extract_content_hash
            values["extract_content_hash"] = extract_content_hash
        if enriched_content_hash is not None:
            values["enriched_content_hash"] = enriched_content_hash
        async with self._db.session() as session:
            stmt = update(CrawlUrlRow).where(CrawlUrlRow.crawl_url_id == crawl_url_id).values(**values)
            _ = await session.execute(stmt)
            await session.commit()

    async def reclaim_stale_fetching(self, *, stale_before: datetime) -> int:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            count_stmt = select(func.count()).where(
                CrawlUrlRow.crawl_status == "fetching",
                CrawlUrlRow.updated_at < stale_before,
            )
            stale_count = int((await session.execute(count_stmt)).scalar_one())
            if stale_count == 0:
                return 0
            stmt = (
                update(CrawlUrlRow)
                .where(
                    CrawlUrlRow.crawl_status == "fetching",
                    CrawlUrlRow.updated_at < stale_before,
                )
                .values(crawl_status="pending", updated_at=now)
            )
            _ = await session.execute(stmt)
            await session.commit()
        return stale_count

    async def requeue_failed_urls(self) -> int:
        # Возвращаем в очередь только те failed URL, у которых истёк backoff и не
        # исчерпан лимит попыток (next_retry_after IS NULL означает исчерпание).
        now = datetime.now(UTC)
        async with self._db.session() as session:
            ready_filter = (
                CrawlUrlRow.crawl_status == "failed",
                CrawlUrlRow.next_retry_after.is_not(None),
                CrawlUrlRow.next_retry_after <= now,
            )
            count_stmt = select(func.count()).where(*ready_filter)
            ready_count = int((await session.execute(count_stmt)).scalar_one())
            if ready_count == 0:
                return 0
            stmt = (
                update(CrawlUrlRow)
                .where(*ready_filter)
                .values(crawl_status="pending", last_error=None, next_retry_after=None, updated_at=now)
            )
            _ = await session.execute(stmt)
            await session.commit()
        return ready_count

    async def add_manual_urls(self, crawl_domain_id: str, urls: list[str]) -> UpsertStats:
        inserted = 0
        updated = 0
        now = datetime.now(UTC)
        async with self._db.session() as session:
            for raw_url in urls:
                canonical = canonicalize_url(raw_url)
                stmt = select(CrawlUrlRow).where(
                    CrawlUrlRow.crawl_domain_id == crawl_domain_id,
                    CrawlUrlRow.canonical_url == canonical,
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing is None:
                    session.add(
                        CrawlUrlRow(
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
                updated += 1
            await session.commit()
        return UpsertStats(inserted=inserted, updated=updated)

    async def requeue_url(self, crawl_url_id: str) -> CrawlUrl:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            stmt = select(CrawlUrlRow).where(CrawlUrlRow.crawl_url_id == crawl_url_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ValueError(f"crawl url not found: {crawl_url_id}")
            row.crawl_status = "pending"
            row.fetch_attempts = 0
            row.next_retry_after = None
            row.last_error = None
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
        return _url_row_to_model(row)

    async def requeue_indexed_for_content_recheck(self, crawl_url_id: str) -> None:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            stmt = (
                update(CrawlUrlRow)
                .where(
                    CrawlUrlRow.crawl_url_id == crawl_url_id,
                    CrawlUrlRow.crawl_status == "indexed",
                )
                .values(crawl_status="pending", updated_at=now)
            )
            _ = await session.execute(stmt)
            await session.commit()

    async def list_indexed_missing_enrichment(
        self,
        crawl_profile_id: str,
        *,
        limit: int,
    ) -> list[str]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        async with self._db.session() as session:
            domain_ids_stmt = select(CrawlDomainRow.crawl_domain_id).where(
                CrawlDomainRow.crawl_profile_id == crawl_profile_id
            )
            domain_ids = list((await session.execute(domain_ids_stmt)).scalars().all())
            if not domain_ids:
                return []
            stmt = (
                select(CrawlUrlRow.crawl_url_id)
                .where(
                    CrawlUrlRow.crawl_domain_id.in_(domain_ids),
                    CrawlUrlRow.crawl_status == "indexed",
                    CrawlUrlRow.enriched_content_hash.is_(None),
                    CrawlUrlRow.document_id.is_not(None),
                    CrawlUrlRow.extract_markdown.is_not(None),
                )
                .order_by(CrawlUrlRow.last_error.is_not(None).desc(), CrawlUrlRow.updated_at)
                .limit(limit)
            )
            return list((await session.execute(stmt)).scalars().all())

    async def requeue_indexed_missing_enrichment(self, crawl_profile_id: str) -> int:
        crawl_url_ids = await self.list_indexed_missing_enrichment(
            crawl_profile_id,
            limit=10_000,
        )
        return len(crawl_url_ids)

    async def count_by_status_for_profile(self, crawl_profile_id: str) -> list[CrawlStatusCount]:
        async with self._db.session() as session:
            stmt = (
                select(CrawlUrlRow.crawl_status, func.count())
                .join(CrawlDomainRow, CrawlUrlRow.crawl_domain_id == CrawlDomainRow.crawl_domain_id)
                .where(CrawlDomainRow.crawl_profile_id == crawl_profile_id)
                .group_by(CrawlUrlRow.crawl_status)
            )
            rows: Sequence[tuple[str, int]] = (await session.execute(stmt)).tuples().all()
        status_counts: list[CrawlStatusCount] = []
        for status_cell, count_cell in rows:
            status_counts.append(CrawlStatusCount(status=status_cell, count=count_cell))
        return status_counts

    async def list_page_for_profile(
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
        async with self._db.session() as session:
            base = (
                select(CrawlUrlRow, CrawlDomainRow.domain)
                .join(CrawlDomainRow, CrawlUrlRow.crawl_domain_id == CrawlDomainRow.crawl_domain_id)
                .where(CrawlDomainRow.crawl_profile_id == crawl_profile_id)
            )
            if crawl_status is not None:
                base = base.where(CrawlUrlRow.crawl_status == crawl_status)
            if domain is not None:
                base = base.where(CrawlDomainRow.domain == domain)
            if content_type is not None:
                base = base.where(
                    _enrichment_snapshot_text("filter_metadata", "content_type") == content_type
                )
            if primary_topic is not None:
                base = base.where(
                    _enrichment_snapshot_text("filter_metadata", "primary_topic") == primary_topic
                )
            if enriched_only is True:
                base = base.where(CrawlUrlRow.enriched_content_hash.isnot(None))
            if enriched_only is False:
                base = base.where(CrawlUrlRow.enriched_content_hash.is_(None))
            count_stmt = select(func.count()).select_from(base.subquery())
            total = int((await session.execute(count_stmt)).scalar_one())
            stmt = base.order_by(CrawlUrlRow.updated_at.desc()).limit(limit).offset(offset)
            rows: Sequence[tuple[CrawlUrlRow, str]] = (await session.execute(stmt)).tuples().all()
        items: list[CrawlUrlListItem] = []
        for url_row, domain_cell in rows:
            items.append(_crawl_url_list_item_from_row(url_row, domain_cell))
        return OffsetPage[CrawlUrlListItem](
            items=items,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def count_enriched_for_profile(self, crawl_profile_id: str) -> int:
        async with self._db.session() as session:
            stmt = (
                select(func.count())
                .select_from(CrawlUrlRow)
                .join(CrawlDomainRow, CrawlUrlRow.crawl_domain_id == CrawlDomainRow.crawl_domain_id)
                .where(
                    CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                    CrawlUrlRow.enriched_content_hash.isnot(None),
                )
            )
            return int((await session.execute(stmt)).scalar_one())

    async def count_enrichment_pending_for_profile(
        self,
        crawl_profile_id: str,
        *,
        llm_enrichment_enabled: bool,
    ) -> int:
        if not llm_enrichment_enabled:
            return 0
        async with self._db.session() as session:
            stmt = (
                select(func.count())
                .select_from(CrawlUrlRow)
                .join(CrawlDomainRow, CrawlUrlRow.crawl_domain_id == CrawlDomainRow.crawl_domain_id)
                .where(
                    CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                    CrawlUrlRow.crawl_status == "indexed",
                    CrawlUrlRow.enriched_content_hash.is_(None),
                )
            )
            return int((await session.execute(stmt)).scalar_one())

    async def count_by_enrichment_content_type(self, crawl_profile_id: str) -> list[CrawlStatusCount]:
        async with self._db.session() as session:
            content_type_expr = _enrichment_snapshot_text("filter_metadata", "content_type")
            stmt = (
                select(content_type_expr, func.count())
                .select_from(CrawlUrlRow)
                .join(CrawlDomainRow, CrawlUrlRow.crawl_domain_id == CrawlDomainRow.crawl_domain_id)
                .where(
                    CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                    CrawlUrlRow.enrichment_snapshot.isnot(None),
                    content_type_expr.isnot(None),
                )
                .group_by(content_type_expr)
                .order_by(func.count().desc())
                .limit(12)
            )
            rows: Sequence[tuple[str, int]] = (await session.execute(stmt)).tuples().all()
        counts: list[CrawlStatusCount] = []
        for content_type, count_cell in rows:
            normalized = content_type.strip()
            if not normalized:
                continue
            counts.append(CrawlStatusCount(status=normalized, count=count_cell))
        return counts

    async def count_by_enrichment_primary_topic(self, crawl_profile_id: str) -> list[CrawlStatusCount]:
        async with self._db.session() as session:
            primary_topic_expr = _enrichment_snapshot_text("filter_metadata", "primary_topic")
            stmt = (
                select(primary_topic_expr, func.count())
                .select_from(CrawlUrlRow)
                .join(CrawlDomainRow, CrawlUrlRow.crawl_domain_id == CrawlDomainRow.crawl_domain_id)
                .where(
                    CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                    CrawlUrlRow.enrichment_snapshot.isnot(None),
                    primary_topic_expr.isnot(None),
                )
                .group_by(primary_topic_expr)
                .order_by(func.count().desc())
                .limit(12)
            )
            rows: Sequence[tuple[str, int]] = (await session.execute(stmt)).tuples().all()
        counts: list[CrawlStatusCount] = []
        for primary_topic, count_cell in rows:
            normalized = primary_topic.strip()
            if not normalized:
                continue
            counts.append(CrawlStatusCount(status=normalized, count=count_cell))
        return counts

    async def get_for_profile(
        self,
        crawl_url_id: str,
        crawl_profile_id: str,
    ) -> tuple[CrawlUrlListItem, str | None, str | None]:
        async with self._db.session() as session:
            stmt = (
                select(CrawlUrlRow, CrawlDomainRow.domain)
                .join(CrawlDomainRow, CrawlUrlRow.crawl_domain_id == CrawlDomainRow.crawl_domain_id)
                .where(
                    CrawlUrlRow.crawl_url_id == crawl_url_id,
                    CrawlDomainRow.crawl_profile_id == crawl_profile_id,
                )
            )
            row = (await session.execute(stmt)).tuples().one_or_none()
        if row is None:
            raise ValueError(f"crawl url not found: crawl_url_id={crawl_url_id}")
        url_row, domain_cell = row
        list_item = _crawl_url_list_item_from_row(url_row, domain_cell)
        return list_item, url_row.extract_title, url_row.extract_markdown


class CrawlJobRepository:
    def __init__(self, db: SearchDatabase) -> None:
        self._db: SearchDatabase = db

    async def start(
        self,
        crawl_profile_id: str,
        trigger: CrawlJobTrigger,
        schedule_task_id: str | None,
    ) -> CrawlJob:
        now = datetime.now(UTC)
        row = CrawlJobRow(
            crawl_job_id=str(uuid.uuid4()),
            crawl_profile_id=crawl_profile_id,
            trigger=trigger,
            schedule_task_id=schedule_task_id,
            status="running",
            started_at=now,
        )
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return _job_row_to_model(row)

    async def get(self, crawl_job_id: str) -> CrawlJob:
        async with self._db.session() as session:
            stmt = select(CrawlJobRow).where(CrawlJobRow.crawl_job_id == crawl_job_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise ValueError(f"crawl job not found: {crawl_job_id}")
        return _job_row_to_model(row)

    async def increment(
        self,
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
        async with self._db.session() as session:
            stmt = select(CrawlJobRow).where(CrawlJobRow.crawl_job_id == crawl_job_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ValueError(f"crawl job not found: {crawl_job_id}")
            row.urls_discovered += urls_discovered
            row.urls_fetched += urls_fetched
            row.urls_indexed += urls_indexed
            row.urls_skipped += urls_skipped
            row.urls_enriched += urls_enriched
            row.urls_enrichment_failed += urls_enrichment_failed
            row.errors += errors
            row.domains_scheduled += domains_scheduled
            await session.commit()

    async def finish(self, crawl_job_id: str, *, status: str) -> CrawlJob:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            stmt = select(CrawlJobRow).where(CrawlJobRow.crawl_job_id == crawl_job_id)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise ValueError(f"crawl job not found: {crawl_job_id}")
            row.status = status
            row.finished_at = now
            await session.commit()
            await session.refresh(row)
        return _job_row_to_model(row)

    async def get_running(self, crawl_profile_id: str) -> CrawlJob | None:
        async with self._db.session() as session:
            stmt = (
                select(CrawlJobRow)
                .where(
                    CrawlJobRow.crawl_profile_id == crawl_profile_id,
                    CrawlJobRow.status == "running",
                )
                .order_by(CrawlJobRow.started_at.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return _job_row_to_model(row)

    async def get_latest(self, crawl_profile_id: str) -> CrawlJob | None:
        async with self._db.session() as session:
            stmt = (
                select(CrawlJobRow)
                .where(CrawlJobRow.crawl_profile_id == crawl_profile_id)
                .order_by(CrawlJobRow.started_at.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return _job_row_to_model(row)

    async def finish_stale_running_jobs(self, *, stale_before: datetime) -> int:
        now = datetime.now(UTC)
        async with self._db.session() as session:
            stmt = select(CrawlJobRow).where(
                CrawlJobRow.status == "running",
                CrawlJobRow.started_at < stale_before,
            )
            rows = list((await session.execute(stmt)).scalars().all())
            for row in rows:
                row.status = "failed"
                row.finished_at = now
            await session.commit()
        return len(rows)

    async def list_page(
        self,
        *,
        crawl_profile_id: str,
        status: str | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[CrawlJob]:
        async with self._db.session() as session:
            base = select(CrawlJobRow).where(CrawlJobRow.crawl_profile_id == crawl_profile_id)
            if status is not None:
                base = base.where(CrawlJobRow.status == status)
            count_stmt = select(func.count()).select_from(base.subquery())
            total = int((await session.execute(count_stmt)).scalar_one())
            stmt = base.order_by(CrawlJobRow.started_at.desc()).limit(limit).offset(offset)
            rows = list((await session.execute(stmt)).scalars().all())
        return OffsetPage[CrawlJob](
            items=[_job_row_to_model(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )
