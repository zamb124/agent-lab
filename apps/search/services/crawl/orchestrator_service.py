"""Crawl orchestrator and seed import."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from apps.search.config import SearchCrawlConfig
from apps.search.db.crawl_repositories import (
    CrawlDomainRepository,
    CrawlJobRepository,
    CrawlProfileRepository,
    CrawlUrlRepository,
)
from apps.search.services.crawl.fetch_service import CrawlFetchService
from apps.search.services.crawl.ingest_service import CrawlIngestService
from apps.search.services.crawl.page_enrichment_service import CrawlPageEnrichmentService
from apps.search.services.crawl.seed_loader import import_tranco_domains
from apps.search.services.crawl.sitemap_parser import SitemapDiscoveryError, discover_sitemap_urls
from apps.search_worker.broker import broker as search_worker_broker
from apps.search_worker.tasks.task_names import (
    CRAWL_DISCOVER_DOMAIN_TASK_NAME,
    CRAWL_ENRICH_URL_TASK_NAME,
    CRAWL_FETCH_URL_TASK_NAME,
    CRAWL_ORCHESTRATOR_TICK_TASK_NAME,
)
from core.clients.rag_client import RagClient
from core.context import Context, clear_context, set_context
from core.crawl.enrichment_skip import (
    compute_enriched_content_hash,
    should_skip_crawl_url_after_fetch,
)
from core.crawl.models import (
    CrawlDomain,
    CrawlDomainRunResponse,
    CrawlFetchResult,
    CrawlIngestPayload,
    CrawlJobTrigger,
    CrawlOrchestratorTickResult,
    CrawlProfileWithIndex,
    CrawlUrl,
    SeedImportRequest,
    SeedImportResult,
)
from core.search.index_models import SearchIndexDefinition


async def _enqueue_task(task_name: str, *args: object, **kwargs: object) -> None:
    task = search_worker_broker.find_task(task_name)
    if task is None:
        raise RuntimeError(f"task is not registered: {task_name}")
    _ = await task.kiq(*args, **kwargs)


class CrawlOrchestratorService:
    def __init__(
        self,
        *,
        crawl_profile_repository: CrawlProfileRepository,
        crawl_domain_repository: CrawlDomainRepository,
        crawl_url_repository: CrawlUrlRepository,
        crawl_job_repository: CrawlJobRepository,
        fetch_service: CrawlFetchService,
        page_enrichment_service: CrawlPageEnrichmentService,
        rag_client: RagClient,
        build_system_context: Callable[[str], Awaitable[Context]],
        crawl_config: SearchCrawlConfig,
    ) -> None:
        self._crawl_profile_repository: CrawlProfileRepository = crawl_profile_repository
        self._crawl_domain_repository: CrawlDomainRepository = crawl_domain_repository
        self._crawl_url_repository: CrawlUrlRepository = crawl_url_repository
        self._crawl_job_repository: CrawlJobRepository = crawl_job_repository
        self._fetch_service: CrawlFetchService = fetch_service
        self._page_enrichment_service: CrawlPageEnrichmentService = page_enrichment_service
        self._ingest_service: CrawlIngestService = CrawlIngestService(rag_client)
        self._rag_client: RagClient = rag_client
        self._build_system_context: Callable[[str], Awaitable[Context]] = build_system_context
        self._crawl_config: SearchCrawlConfig = crawl_config

    async def ensure_rag_namespace(self, search_index: SearchIndexDefinition) -> None:
        _ = await self._rag_client.create_namespace(
            search_index.rag_namespace_id,
            description=search_index.description or search_index.display_name,
        )

    async def run_tick(
        self,
        *,
        crawl_profile_id: str,
        trigger: CrawlJobTrigger,
        schedule_task_id: str | None,
    ) -> CrawlOrchestratorTickResult:
        profile_bundle = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        if not profile_bundle.profile.enabled:
            raise ValueError(f"crawl profile disabled: {crawl_profile_id}")
        job = await self._crawl_job_repository.start(crawl_profile_id, trigger, schedule_task_id)
        trace_id = f"crawl:tick:{job.crawl_job_id}"
        set_context(await self._build_system_context(trace_id))
        try:
            await self.ensure_rag_namespace(profile_bundle.search_index)
            now = datetime.now(UTC)
            max_domains = profile_bundle.profile.max_domains_per_tick
            scheduled_domain_ids: set[str] = set()
            domains: list[CrawlDomain] = []

            backlog_domains = await self._crawl_domain_repository.list_with_pending_urls(
                crawl_profile_id,
                limit=max_domains,
            )
            for domain in backlog_domains:
                if domain.crawl_domain_id in scheduled_domain_ids:
                    continue
                domains.append(domain)
                scheduled_domain_ids.add(domain.crawl_domain_id)

            remaining_slots = max_domains - len(domains)
            if remaining_slots > 0:
                due_domains = await self._crawl_domain_repository.list_due(
                    crawl_profile_id,
                    now=now,
                    limit=remaining_slots,
                )
                for domain in due_domains:
                    if domain.crawl_domain_id in scheduled_domain_ids:
                        continue
                    domains.append(domain)
                    scheduled_domain_ids.add(domain.crawl_domain_id)
                    if len(domains) >= max_domains:
                        break

            await self._crawl_job_repository.increment(
                job.crawl_job_id,
                domains_scheduled=len(domains),
            )
            for domain in domains:
                if domain.status != "active":
                    continue
                _ = await self._schedule_domain_for_tick(
                    domain=domain,
                    crawl_job_id=job.crawl_job_id,
                    crawl_profile_id=crawl_profile_id,
                    profile_bundle=profile_bundle,
                    now=now,
                )
            _ = await self._crawl_job_repository.finish(job.crawl_job_id, status="completed")
            pending_urls = await self._crawl_url_repository.count_pending_for_profile(crawl_profile_id)
            if pending_urls > 0:
                await _enqueue_task(CRAWL_ORCHESTRATOR_TICK_TASK_NAME, crawl_profile_id)
            return {
                "crawl_job_id": job.crawl_job_id,
                "crawl_profile_id": crawl_profile_id,
                "domains_scheduled": len(domains),
                "status": "completed",
            }
        except Exception:
            _ = await self._crawl_job_repository.finish(job.crawl_job_id, status="failed")
            raise
        finally:
            clear_context()

    async def discover_domain(
        self,
        crawl_domain_id: str,
        crawl_job_id: str,
        crawl_profile_id: str,
    ) -> None:
        profile_bundle = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        domain = await self._crawl_domain_repository.get(crawl_domain_id)
        try:
            entries = await discover_sitemap_urls(
                domain.domain,
                timeout_seconds=self._crawl_config.http_timeout_seconds,
                max_urls=self._crawl_config.sitemap_max_urls_per_domain,
                max_sitemap_bytes=self._crawl_config.sitemap_max_bytes,
            )
        except SitemapDiscoveryError as exc:
            await self._crawl_domain_repository.schedule_next(
                crawl_domain_id,
                datetime.now(UTC)
                + timedelta(seconds=profile_bundle.profile.refresh_interval_seconds),
                last_error=str(exc),
                status="error",
            )
            raise
        stats = await self._crawl_url_repository.upsert_from_sitemap(crawl_domain_id, entries)
        await self._crawl_domain_repository.mark_discovered(crawl_domain_id, datetime.now(UTC))
        await self._crawl_job_repository.increment(
            crawl_job_id,
            urls_discovered=stats.inserted + stats.updated,
        )
        await self._enqueue_domain_fetch(
            crawl_domain_id=crawl_domain_id,
            crawl_job_id=crawl_job_id,
            crawl_profile_id=crawl_profile_id,
            url_budget=profile_bundle.profile.max_urls_per_domain_per_tick,
        )

    async def fetch_one_url(
        self,
        crawl_domain_id: str,
        crawl_job_id: str,
        crawl_profile_id: str,
        url_budget: int,
    ) -> None:
        if url_budget < 1:
            raise ValueError("url_budget must be >= 1")
        profile_bundle = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        domain = await self._crawl_domain_repository.get(crawl_domain_id)
        urls = await self._crawl_url_repository.claim_pending_batch(crawl_domain_id, 1)
        if not urls:
            return
        crawl_url = urls[0]
        profile = profile_bundle.profile
        prompt_version = self._crawl_config.enrichment.prompt_version
        stored_extract_hash = crawl_url.extract_content_hash
        if stored_extract_hash is None:
            stored_extract_hash = crawl_url.content_hash
        await self._crawl_job_repository.increment(crawl_job_id, urls_fetched=1)
        if crawl_url.document_id is not None and crawl_url.crawl_status == "indexed":
            if stored_extract_hash is not None and should_skip_crawl_url_after_fetch(
                llm_enrichment_enabled=profile.llm_enrichment_enabled,
                extract_hash=stored_extract_hash,
                stored_extract_hash=stored_extract_hash,
                stored_enriched_hash=crawl_url.enriched_content_hash,
                stored_enrichment_prompt_version=crawl_url.enrichment_prompt_version,
                current_prompt_version=prompt_version,
                document_id=crawl_url.document_id,
            ):
                await self._crawl_url_repository.mark_skipped(
                    crawl_url.crawl_url_id,
                    stored_extract_hash,
                    enriched_content_hash=crawl_url.enriched_content_hash,
                )
                await self._crawl_job_repository.increment(crawl_job_id, urls_skipped=1)
            else:
                await self._fetch_and_index_url(
                    crawl_url=crawl_url,
                    crawl_job_id=crawl_job_id,
                    crawl_profile_id=crawl_profile_id,
                    profile_bundle=profile_bundle,
                    domain=domain,
                    stored_extract_hash=stored_extract_hash,
                )
        else:
            await self._fetch_and_index_url(
                crawl_url=crawl_url,
                crawl_job_id=crawl_job_id,
                crawl_profile_id=crawl_profile_id,
                profile_bundle=profile_bundle,
                domain=domain,
                stored_extract_hash=stored_extract_hash,
            )

        pending = await self._crawl_url_repository.count_pending(crawl_domain_id)
        if pending == 0:
            await self._crawl_domain_repository.mark_crawled(crawl_domain_id, datetime.now(UTC))
            profile_pending = await self._crawl_url_repository.count_pending_for_profile(crawl_profile_id)
            if profile_pending > 0:
                await _enqueue_task(CRAWL_ORCHESTRATOR_TICK_TASK_NAME, crawl_profile_id)
            return
        await self._enqueue_domain_fetch(
            crawl_domain_id=crawl_domain_id,
            crawl_job_id=crawl_job_id,
            crawl_profile_id=crawl_profile_id,
            url_budget=1,
        )

    async def _fetch_and_index_url(
        self,
        *,
        crawl_url: CrawlUrl,
        crawl_job_id: str,
        crawl_profile_id: str,
        profile_bundle: CrawlProfileWithIndex,
        domain: CrawlDomain,
        stored_extract_hash: str | None,
    ) -> None:
        profile = profile_bundle.profile
        prompt_version = self._crawl_config.enrichment.prompt_version
        try:
            fetched = await self._fetch_service.fetch_markdown(
                crawl_url.url,
                timeout_seconds=self._crawl_config.http_timeout_seconds,
                min_extract_chars=self._crawl_config.min_extract_chars,
                browser_fallback_enabled=profile.browser_fallback_enabled,
            )
            if should_skip_crawl_url_after_fetch(
                llm_enrichment_enabled=profile.llm_enrichment_enabled,
                extract_hash=fetched.content_hash,
                stored_extract_hash=stored_extract_hash,
                stored_enriched_hash=crawl_url.enriched_content_hash,
                stored_enrichment_prompt_version=crawl_url.enrichment_prompt_version,
                current_prompt_version=prompt_version,
                document_id=crawl_url.document_id,
            ):
                await self._crawl_url_repository.mark_skipped(
                    crawl_url.crawl_url_id,
                    fetched.content_hash,
                    enriched_content_hash=crawl_url.enriched_content_hash,
                )
                await self._crawl_job_repository.increment(crawl_job_id, urls_skipped=1)
                return
            enriched_page = None
            payload = CrawlIngestPayload(fetched=fetched, enriched_page=enriched_page)
            document_id = await self._ingest_service.ingest_page(
                search_index=profile_bundle.search_index,
                crawl_job_id=crawl_job_id,
                crawl_profile_id=crawl_profile_id,
                domain=domain,
                payload=payload,
                document_id=crawl_url.document_id,
            )
            await self._crawl_url_repository.mark_indexed(
                crawl_url.crawl_url_id,
                document_id,
                fetched.content_hash,
                fetched.fetch_transport,
                extract_markdown=fetched.markdown,
                extract_title=fetched.title,
            )
            await self._crawl_job_repository.increment(crawl_job_id, urls_indexed=1)
            if profile.llm_enrichment_enabled:
                await _enqueue_task(
                    CRAWL_ENRICH_URL_TASK_NAME,
                    crawl_url.crawl_url_id,
                    crawl_job_id,
                    crawl_profile_id,
                )
        except Exception as exc:
            await self._crawl_url_repository.mark_failed(crawl_url.crawl_url_id, str(exc))
            await self._crawl_job_repository.increment(crawl_job_id, errors=1)

    async def enrich_one_url(
        self,
        crawl_url_id: str,
        crawl_job_id: str,
        crawl_profile_id: str,
    ) -> None:
        profile_bundle = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        profile = profile_bundle.profile
        if not profile.llm_enrichment_enabled:
            raise ValueError(f"llm enrichment disabled for crawl profile: {crawl_profile_id}")
        crawl_url = await self._crawl_url_repository.get(crawl_url_id)
        if crawl_url.crawl_status != "indexed":
            raise ValueError(
                f"crawl enrich requires indexed status: crawl_url_id={crawl_url_id}, status={crawl_url.crawl_status}"
            )
        if crawl_url.document_id is None:
            raise ValueError(f"crawl enrich requires document_id: crawl_url_id={crawl_url_id}")
        prompt_version = self._crawl_config.enrichment.prompt_version
        stored_extract_hash = crawl_url.extract_content_hash
        if stored_extract_hash is None:
            stored_extract_hash = crawl_url.content_hash
        if stored_extract_hash is None:
            raise ValueError(f"crawl enrich requires extract_content_hash: crawl_url_id={crawl_url_id}")
        if should_skip_crawl_url_after_fetch(
            llm_enrichment_enabled=True,
            extract_hash=stored_extract_hash,
            stored_extract_hash=stored_extract_hash,
            stored_enriched_hash=crawl_url.enriched_content_hash,
            stored_enrichment_prompt_version=crawl_url.enrichment_prompt_version,
            current_prompt_version=prompt_version,
            document_id=crawl_url.document_id,
        ):
            return
        domain = await self._crawl_domain_repository.get(crawl_url.crawl_domain_id)
        url, canonical_url, extract_markdown, extract_title, extract_content_hash = (
            await self._crawl_url_repository.get_layer1_snapshot(crawl_url_id)
        )
        fetched = CrawlFetchResult(
            url=url,
            canonical_url=canonical_url,
            markdown=extract_markdown,
            title=extract_title,
            content_hash=extract_content_hash,
            fetch_transport=crawl_url.fetch_transport or "http",
        )
        try:
            enriched_page = await self._page_enrichment_service.enrich_markdown(
                markdown=extract_markdown,
                url=url,
                profile=profile,
                crawl_domain_id=crawl_url.crawl_domain_id,
            )
            enriched_content_hash = compute_enriched_content_hash(enriched_page)
            _ = await self._ingest_service.reingest_enriched_page(
                search_index=profile_bundle.search_index,
                crawl_job_id=crawl_job_id,
                crawl_profile_id=crawl_profile_id,
                domain=domain,
                document_id=crawl_url.document_id,
                fetched=fetched,
                enriched_page=enriched_page,
            )
            await self._crawl_url_repository.mark_enriched(
                crawl_url_id,
                enriched_content_hash=enriched_content_hash,
                enrichment_model=enriched_page.enrichment_model,
                enrichment_prompt_version=enriched_page.enrichment_prompt_version,
            )
            await self._crawl_job_repository.increment(crawl_job_id, urls_enriched=1)
        except Exception as exc:
            await self._crawl_url_repository.mark_enrichment_failed(crawl_url_id, str(exc))
            await self._crawl_job_repository.increment(
                crawl_job_id,
                errors=1,
                urls_enrichment_failed=1,
            )
            raise

    async def enqueue_enrichment_backfill(
        self,
        crawl_profile_id: str,
        crawl_job_id: str,
        *,
        limit: int = 100,
    ) -> int:
        profile_bundle = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        if not profile_bundle.profile.llm_enrichment_enabled:
            raise ValueError(f"llm enrichment disabled for crawl profile: {crawl_profile_id}")
        crawl_url_ids = await self._crawl_url_repository.list_indexed_missing_enrichment(
            crawl_profile_id,
            limit=limit,
        )
        for crawl_url_id in crawl_url_ids:
            await _enqueue_task(
                CRAWL_ENRICH_URL_TASK_NAME,
                crawl_url_id,
                crawl_job_id,
                crawl_profile_id,
            )
        return len(crawl_url_ids)

    async def _enqueue_domain_fetch(
        self,
        *,
        crawl_domain_id: str,
        crawl_job_id: str,
        crawl_profile_id: str,
        url_budget: int,
    ) -> None:
        if url_budget < 1:
            raise ValueError("url_budget must be >= 1")
        profile_bundle = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        profile = profile_bundle.profile
        pending = await self._crawl_url_repository.count_pending(crawl_domain_id)
        if pending == 0:
            return
        batch = min(url_budget, profile.max_urls_per_batch, pending)
        parallel = min(batch, profile.http_concurrency)
        for _ in range(parallel):
            await _enqueue_task(
                CRAWL_FETCH_URL_TASK_NAME,
                crawl_domain_id,
                crawl_job_id,
                crawl_profile_id,
                1,
            )

    async def _schedule_domain_for_tick(
        self,
        *,
        domain: CrawlDomain,
        crawl_job_id: str,
        crawl_profile_id: str,
        profile_bundle: CrawlProfileWithIndex,
        now: datetime,
    ) -> bool:
        profile = profile_bundle.profile
        if domain.domain in profile.denylist_domains:
            await self._crawl_domain_repository.schedule_next(
                domain.crawl_domain_id,
                now + timedelta(seconds=profile.refresh_interval_seconds),
            )
            return False

        pending = await self._crawl_url_repository.count_pending(domain.crawl_domain_id)
        if pending > 0:
            await self._enqueue_domain_fetch(
                crawl_domain_id=domain.crawl_domain_id,
                crawl_job_id=crawl_job_id,
                crawl_profile_id=crawl_profile_id,
                url_budget=profile.max_urls_per_domain_per_tick,
            )
            await self._crawl_domain_repository.schedule_next(
                domain.crawl_domain_id,
                now + timedelta(seconds=self._crawl_config.backlog_reschedule_seconds),
            )
            return True

        if self._needs_discovery(domain, profile.sitemap_stale_after_seconds, now):
            await _enqueue_task(
                CRAWL_DISCOVER_DOMAIN_TASK_NAME,
                domain.crawl_domain_id,
                crawl_job_id,
                crawl_profile_id,
            )
            await self._crawl_domain_repository.schedule_next(
                domain.crawl_domain_id,
                now + timedelta(seconds=profile.refresh_interval_seconds),
            )
            return True

        await _enqueue_task(
            CRAWL_DISCOVER_DOMAIN_TASK_NAME,
            domain.crawl_domain_id,
            crawl_job_id,
            crawl_profile_id,
        )
        await self._crawl_domain_repository.schedule_next(
            domain.crawl_domain_id,
            now + timedelta(seconds=profile.refresh_interval_seconds),
        )
        return True

    async def import_seed(self, body: SeedImportRequest) -> SeedImportResult:
        if body.seed_source != "tranco":
            raise ValueError(f"unsupported seed_source: {body.seed_source}")
        return await import_tranco_domains(
            body.crawl_profile_id,
            crawl_domain_repository=self._crawl_domain_repository,
            limit=body.tranco_limit,
            ru_com_whitelist=tuple(self._crawl_config.ru_com_whitelist),
            skip_categories=tuple(self._crawl_config.skip_categories),
        )

    def _needs_discovery(self, domain: CrawlDomain, stale_after_seconds: int, now: datetime) -> bool:
        if domain.last_discovered_at is None:
            return True
        age = (now - domain.last_discovered_at).total_seconds()
        return age > stale_after_seconds

    async def run_single_domain(
        self,
        crawl_domain_id: str,
        crawl_profile_id: str,
    ) -> CrawlDomainRunResponse:
        profile_bundle = await self._crawl_profile_repository.get_with_index(crawl_profile_id)
        if not profile_bundle.profile.enabled:
            raise ValueError(f"crawl profile disabled: {crawl_profile_id}")
        domain = await self._crawl_domain_repository.get(crawl_domain_id)
        if domain.crawl_profile_id != crawl_profile_id:
            raise ValueError("crawl_domain_id does not belong to crawl_profile_id")
        if domain.domain in profile_bundle.profile.denylist_domains:
            raise ValueError(f"domain is denylisted: {domain.domain}")

        now = datetime.now(UTC)
        await self._crawl_domain_repository.schedule_next(
            crawl_domain_id,
            now,
            last_error=None,
            status="active",
        )
        job = await self._crawl_job_repository.start(crawl_profile_id, "manual", None)
        await self._crawl_job_repository.increment(job.crawl_job_id, domains_scheduled=1)

        action: Literal["discover", "fetch"]
        if self._needs_discovery(domain, profile_bundle.profile.sitemap_stale_after_seconds, now):
            await _enqueue_task(
                CRAWL_DISCOVER_DOMAIN_TASK_NAME,
                crawl_domain_id,
                job.crawl_job_id,
                crawl_profile_id,
            )
            action = "discover"
        else:
            pending = await self._crawl_url_repository.count_pending(crawl_domain_id)
            if pending > 0:
                await self._enqueue_domain_fetch(
                    crawl_domain_id=crawl_domain_id,
                    crawl_job_id=job.crawl_job_id,
                    crawl_profile_id=crawl_profile_id,
                    url_budget=profile_bundle.profile.max_urls_per_domain_per_tick,
                )
                action = "fetch"
            else:
                await _enqueue_task(
                    CRAWL_DISCOVER_DOMAIN_TASK_NAME,
                    crawl_domain_id,
                    job.crawl_job_id,
                    crawl_profile_id,
                )
                action = "discover"

        return CrawlDomainRunResponse(
            crawl_domain_id=crawl_domain_id,
            crawl_job_id=job.crawl_job_id,
            crawl_profile_id=crawl_profile_id,
            action=action,
            status="queued",
        )
