"""Crawl orchestrator and seed import."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx

from apps.search.config import SearchCrawlConfig
from apps.search.services.crawl.fetch_service import CrawlFetchService
from apps.search.services.crawl.ingest_service import CrawlIngestService
from apps.search.services.crawl.page_enrichment_service import CrawlPageEnrichmentService
from apps.search.services.crawl.politeness_service import CrawlPolitenessService
from apps.search.services.crawl.seed_loader import import_tranco_domains
from apps.search.services.crawl.sitemap_parser import discover_sitemap_urls
from apps.search_worker.tasks.task_names import (
    CRAWL_DISCOVER_DOMAIN,
    CRAWL_ENRICH_URL,
    CRAWL_FETCH_URL,
    CRAWL_ORCHESTRATOR_TICK,
)
from core.clients.rag_client import RagClient
from core.crawl.enrichment_skip import (
    compute_enriched_content_hash,
    should_skip_crawl_url_after_fetch,
)
from core.crawl.errors import CrawlExtractTooShortError
from core.crawl.logging_events import (
    log_crawl_discover_completed,
    log_crawl_discover_failed,
    log_crawl_domain_scheduled,
    log_crawl_enrich_completed,
    log_crawl_enrich_failed,
    log_crawl_seed_completed,
    log_crawl_tick_completed,
    log_crawl_tick_failed,
    log_crawl_tick_started,
    log_crawl_url_outcome,
)
from core.crawl.models import (
    CrawlDomain,
    CrawlDomainRunResponse,
    CrawlFetchResult,
    CrawlIngestPayload,
    CrawlJob,
    CrawlJobTrigger,
    CrawlOrchestratorTickResult,
    CrawlProfile,
    CrawlProfileWithIndex,
    CrawlUrl,
    SeedImportRequest,
    SeedImportResult,
)
from core.crawl.report_projection import enrichment_snapshot_from_enriched_page
from core.crawl.url_filter import build_url_filter
from core.search.index_models import SearchIndexDefinition
from core.tasks import enqueue


def _gone_http_status(exc: BaseException) -> int | None:
    """HTTP-статус окончательно недоступной страницы (404/410) или None."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (404, 410):
        return exc.response.status_code
    return None


class CrawlOrchestratorService:
    def __init__(
        self,
        *,
        fetch_service: CrawlFetchService,
        page_enrichment_service: CrawlPageEnrichmentService,
        politeness_service: CrawlPolitenessService,
        rag_client: RagClient,
        crawl_config: SearchCrawlConfig,
    ) -> None:
        self._fetch_service: CrawlFetchService = fetch_service
        self._page_enrichment_service: CrawlPageEnrichmentService = page_enrichment_service
        self._politeness_service: CrawlPolitenessService = politeness_service
        self._ingest_service: CrawlIngestService = CrawlIngestService(rag_client)
        self._rag_client: RagClient = rag_client
        self._crawl_config: SearchCrawlConfig = crawl_config
        self._ensured_rag_namespace_ids: set[str] = set()

    async def ensure_rag_namespace(self, search_index: SearchIndexDefinition) -> None:
        rag_namespace_id = search_index.rag_namespace_id
        if rag_namespace_id in self._ensured_rag_namespace_ids:
            return
        _ = await self._rag_client.create_namespace(
            rag_namespace_id,
            description=search_index.description or search_index.display_name,
        )
        self._ensured_rag_namespace_ids.add(rag_namespace_id)

    async def run_tick(
        self,
        *,
        crawl_profile_id: str,
        trigger: CrawlJobTrigger,
        schedule_task_id: str | None,
    ) -> CrawlOrchestratorTickResult:
        profile_bundle = await CrawlProfile.get_with_index(crawl_profile_id)
        if not profile_bundle.profile.enabled:
            raise ValueError(f"crawl profile disabled: {crawl_profile_id}")
        job = await CrawlJob.start(crawl_profile_id, trigger, schedule_task_id)
        search_index_id = profile_bundle.search_index.search_index_id
        log_crawl_tick_started(
            crawl_profile_id=crawl_profile_id,
            crawl_job_id=job.crawl_job_id,
            search_index_id=search_index_id,
            crawl_trigger=trigger,
        )
        try:
            await self.ensure_rag_namespace(profile_bundle.search_index)
            now = datetime.now(UTC)
            max_domains = profile_bundle.profile.max_domains_per_tick
            scheduled_domain_ids: set[str] = set()
            domains: list[CrawlDomain] = []

            backlog_domains = await CrawlDomain.list_with_pending_urls(
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
                due_domains = await CrawlDomain.list_due(
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

            await CrawlJob.increment(
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
            _ = await CrawlJob.finish(job.crawl_job_id, status="completed")
            pending_urls = await CrawlUrl.count_pending_for_profile(crawl_profile_id)
            log_crawl_tick_completed(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=job.crawl_job_id,
                search_index_id=search_index_id,
                crawl_trigger=trigger,
                domains_scheduled=len(domains),
                pending_urls=pending_urls,
            )
            return {
                "crawl_job_id": job.crawl_job_id,
                "crawl_profile_id": crawl_profile_id,
                "domains_scheduled": len(domains),
                "status": "completed",
            }
        except Exception as exc:
            _ = await CrawlJob.finish(job.crawl_job_id, status="failed")
            log_crawl_tick_failed(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=job.crawl_job_id,
                search_index_id=search_index_id,
                crawl_trigger=trigger,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            raise

    async def discover_domain(
        self,
        crawl_domain_id: str,
        crawl_job_id: str,
        crawl_profile_id: str,
    ) -> None:
        profile_bundle = await CrawlProfile.get_with_index(crawl_profile_id)
        domain = await CrawlDomain.get(crawl_domain_id)
        if domain is None:
            raise ValueError(f"crawl domain not found: {crawl_domain_id}")
        search_index_id = profile_bundle.search_index.search_index_id
        url_filter = build_url_filter(profile_bundle.profile, domain)
        try:
            entries = await discover_sitemap_urls(
                domain.domain,
                timeout_seconds=self._crawl_config.http_timeout_seconds,
                max_urls=self._crawl_config.sitemap_max_urls_per_domain,
                max_sitemap_bytes=self._crawl_config.sitemap_max_bytes,
                url_filter=url_filter,
            )
            stats = await CrawlUrl.upsert_from_sitemap(crawl_domain_id, entries)
            await CrawlDomain.mark_discovered(crawl_domain_id, datetime.now(UTC))
            urls_discovered = stats.inserted + stats.updated
            await CrawlJob.increment(
                crawl_job_id,
                urls_discovered=urls_discovered,
            )
            log_crawl_discover_completed(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=crawl_job_id,
                crawl_domain_id=crawl_domain_id,
                search_index_id=search_index_id,
                domain=domain.domain,
                urls_discovered=urls_discovered,
                urls_inserted=stats.inserted,
                urls_updated=stats.updated,
            )
            await self._enqueue_domain_fetch(
                crawl_domain_id=crawl_domain_id,
                crawl_job_id=crawl_job_id,
                crawl_profile_id=crawl_profile_id,
                url_budget=profile_bundle.profile.max_urls_per_domain_per_tick,
            )
        except Exception as exc:
            await CrawlDomain.schedule_next(
                crawl_domain_id,
                datetime.now(UTC)
                + timedelta(seconds=self._effective_refresh_interval(domain, profile_bundle)),
                last_error=str(exc),
                status="error",
            )
            log_crawl_discover_failed(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=crawl_job_id,
                crawl_domain_id=crawl_domain_id,
                search_index_id=search_index_id,
                domain=domain.domain,
                sitemap_error_kind=type(exc).__name__,
                exception_message=str(exc),
            )
            raise

    async def fetch_one_url(
        self,
        crawl_domain_id: str,
        crawl_job_id: str,
        crawl_profile_id: str,
        url_budget: int,
    ) -> None:
        if url_budget < 1:
            raise ValueError("url_budget must be >= 1")
        profile_bundle = await CrawlProfile.get_with_index(crawl_profile_id)
        domain = await CrawlDomain.get(crawl_domain_id)
        if domain is None:
            raise ValueError(f"crawl domain not found: {crawl_domain_id}")
        urls = await CrawlUrl.claim_pending_batch(crawl_domain_id, 1)
        if not urls:
            return
        crawl_url = urls[0]
        profile = profile_bundle.profile
        prompt_version = self._crawl_config.enrichment.prompt_version
        stored_extract_hash = crawl_url.extract_content_hash
        if stored_extract_hash is None:
            stored_extract_hash = crawl_url.content_hash
        await CrawlJob.increment(crawl_job_id, urls_fetched=1)
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
                await CrawlUrl.mark_skipped(
                    crawl_url.crawl_url_id,
                    stored_extract_hash,
                    enriched_content_hash=crawl_url.enriched_content_hash,
                )
                await CrawlJob.increment(crawl_job_id, urls_skipped=1)
                log_crawl_url_outcome(
                    crawl_profile_id=crawl_profile_id,
                    crawl_job_id=crawl_job_id,
                    crawl_domain_id=crawl_domain_id,
                    crawl_url_id=crawl_url.crawl_url_id,
                    search_index_id=profile_bundle.search_index.search_index_id,
                    domain=domain.domain,
                    canonical_url=crawl_url.canonical_url,
                    crawl_outcome="skipped",
                    crawl_skip_reason="content_unchanged",
                    content_hash_changed=False,
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
        else:
            await self._fetch_and_index_url(
                crawl_url=crawl_url,
                crawl_job_id=crawl_job_id,
                crawl_profile_id=crawl_profile_id,
                profile_bundle=profile_bundle,
                domain=domain,
                stored_extract_hash=stored_extract_hash,
            )

        pending = await CrawlUrl.count_pending(crawl_domain_id)
        if pending == 0:
            await CrawlDomain.mark_crawled(crawl_domain_id, datetime.now(UTC))
            profile_pending = await CrawlUrl.count_pending_for_profile(crawl_profile_id)
            if profile_pending > 0:
                _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, crawl_profile_id)
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
        search_index_id = profile_bundle.search_index.search_index_id
        if not await self._politeness_service.is_url_allowed(crawl_url.url):
            await CrawlUrl.mark_skipped(crawl_url.crawl_url_id, None)
            await CrawlJob.increment(crawl_job_id, urls_skipped=1)
            log_crawl_url_outcome(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=crawl_job_id,
                crawl_domain_id=domain.crawl_domain_id,
                crawl_url_id=crawl_url.crawl_url_id,
                search_index_id=search_index_id,
                domain=domain.domain,
                canonical_url=crawl_url.canonical_url,
                crawl_outcome="skipped",
                crawl_skip_reason="robots_disallowed",
            )
            return
        _ = await self._politeness_service.wait_for_fetch_slot(crawl_url.url)
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
                await CrawlUrl.mark_skipped(
                    crawl_url.crawl_url_id,
                    fetched.content_hash,
                    enriched_content_hash=crawl_url.enriched_content_hash,
                )
                await CrawlJob.increment(crawl_job_id, urls_skipped=1)
                log_crawl_url_outcome(
                    crawl_profile_id=crawl_profile_id,
                    crawl_job_id=crawl_job_id,
                    crawl_domain_id=domain.crawl_domain_id,
                    crawl_url_id=crawl_url.crawl_url_id,
                    search_index_id=search_index_id,
                    domain=domain.domain,
                    canonical_url=fetched.canonical_url,
                    crawl_outcome="skipped",
                    crawl_skip_reason="content_unchanged",
                    fetch_transport=fetched.fetch_transport,
                    extract_chars=len(fetched.markdown.strip()),
                    content_hash_changed=False,
                )
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
            await CrawlUrl.mark_indexed(
                crawl_url.crawl_url_id,
                document_id,
                fetched.content_hash,
                fetched.fetch_transport,
                extract_markdown=fetched.markdown,
                extract_title=fetched.title,
                extract_structural_signals=fetched.structural_signals,
            )
            await CrawlJob.increment(crawl_job_id, urls_indexed=1)
            log_crawl_url_outcome(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=crawl_job_id,
                crawl_domain_id=domain.crawl_domain_id,
                crawl_url_id=crawl_url.crawl_url_id,
                search_index_id=search_index_id,
                domain=domain.domain,
                canonical_url=fetched.canonical_url,
                crawl_outcome="indexed",
                fetch_transport=fetched.fetch_transport,
                extract_chars=len(fetched.markdown.strip()),
                content_hash_changed=True,
                document_id=document_id,
            )
            if profile.llm_enrichment_enabled:
                _ = await enqueue(
                    CRAWL_ENRICH_URL,
                    crawl_url.crawl_url_id,
                    crawl_job_id,
                    crawl_profile_id,
                )
        except CrawlExtractTooShortError:
            await CrawlUrl.mark_skipped(
                crawl_url.crawl_url_id,
                None,
            )
            await CrawlJob.increment(crawl_job_id, urls_skipped=1)
            log_crawl_url_outcome(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=crawl_job_id,
                crawl_domain_id=domain.crawl_domain_id,
                crawl_url_id=crawl_url.crawl_url_id,
                search_index_id=search_index_id,
                domain=domain.domain,
                canonical_url=crawl_url.canonical_url,
                crawl_outcome="skipped",
                crawl_skip_reason="extract_too_short",
            )
        except Exception as exc:
            gone_status = _gone_http_status(exc)
            if gone_status is not None:
                # Гигиена индекса: мёртвая страница удаляется из RAG и выводится
                # из очереди до появления нового sitemap_lastmod.
                if crawl_url.document_id is not None:
                    _ = await self._rag_client.delete_namespace_document(
                        profile_bundle.search_index.rag_namespace_id,
                        crawl_url.document_id,
                    )
                await CrawlUrl.mark_gone(
                    crawl_url.crawl_url_id,
                    error=f"http_{gone_status}",
                )
                await CrawlJob.increment(crawl_job_id, urls_skipped=1)
                log_crawl_url_outcome(
                    crawl_profile_id=crawl_profile_id,
                    crawl_job_id=crawl_job_id,
                    crawl_domain_id=domain.crawl_domain_id,
                    crawl_url_id=crawl_url.crawl_url_id,
                    search_index_id=search_index_id,
                    domain=domain.domain,
                    canonical_url=crawl_url.canonical_url,
                    crawl_outcome="gone",
                    document_id=crawl_url.document_id,
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                )
                return
            await CrawlUrl.mark_failed(
                crawl_url.crawl_url_id,
                str(exc),
                retry_base_seconds=self._crawl_config.fetch_retry_base_seconds,
                max_attempts=self._crawl_config.max_fetch_attempts,
            )
            await CrawlJob.increment(crawl_job_id, errors=1)
            updated_url = await CrawlUrl.get(crawl_url.crawl_url_id)
            if updated_url is None:
                raise ValueError(f"crawl url not found: {crawl_url.crawl_url_id}")
            log_crawl_url_outcome(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=crawl_job_id,
                crawl_domain_id=domain.crawl_domain_id,
                crawl_url_id=crawl_url.crawl_url_id,
                search_index_id=search_index_id,
                domain=domain.domain,
                canonical_url=crawl_url.canonical_url,
                crawl_outcome="failed",
                fetch_attempts=updated_url.fetch_attempts,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )

    async def enrich_one_url(
        self,
        crawl_url_id: str,
        crawl_job_id: str,
        crawl_profile_id: str,
    ) -> None:
        profile_bundle = await CrawlProfile.get_with_index(crawl_profile_id)
        profile = profile_bundle.profile
        if not profile.llm_enrichment_enabled:
            raise ValueError(f"llm enrichment disabled for crawl profile: {crawl_profile_id}")
        crawl_url = await CrawlUrl.get(crawl_url_id)
        if crawl_url is None:
            raise ValueError(f"crawl url not found: {crawl_url_id}")
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
        domain = await CrawlDomain.get(crawl_url.crawl_domain_id)
        if domain is None:
            raise ValueError(f"crawl domain not found: {crawl_url.crawl_domain_id}")
        (
            url,
            canonical_url,
            extract_markdown,
            extract_title,
            extract_content_hash,
            structural_signals,
        ) = await CrawlUrl.get_layer1_snapshot(crawl_url_id)
        fetched = CrawlFetchResult(
            url=url,
            canonical_url=canonical_url,
            markdown=extract_markdown,
            title=extract_title,
            content_hash=extract_content_hash,
            fetch_transport=crawl_url.fetch_transport or "http",
            structural_signals=structural_signals,
        )
        try:
            enrich_started_at = time.monotonic()
            enriched_page = await self._page_enrichment_service.enrich_markdown(
                markdown=extract_markdown,
                url=url,
                profile=profile,
                search_index_id=profile_bundle.search_index.search_index_id,
                domain=domain,
                crawl_domain_id=crawl_url.crawl_domain_id,
                structural_signals=structural_signals,
                sitemap_lastmod=crawl_url.sitemap_lastmod,
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
            await CrawlUrl.mark_enriched(
                crawl_url_id,
                enriched_content_hash=enriched_content_hash,
                enrichment_model=enriched_page.enrichment_model,
                enrichment_prompt_version=enriched_page.enrichment_prompt_version,
                enrichment_snapshot=enrichment_snapshot_from_enriched_page(enriched_page),
            )
            await CrawlJob.increment(crawl_job_id, urls_enriched=1)
            enrichment_duration_ms = int((time.monotonic() - enrich_started_at) * 1000)
            enrichment_provider = self._crawl_config.enrichment.provider.strip()
            log_crawl_enrich_completed(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=crawl_job_id,
                crawl_url_id=crawl_url_id,
                crawl_domain_id=crawl_url.crawl_domain_id,
                search_index_id=profile_bundle.search_index.search_index_id,
                domain=domain.domain,
                canonical_url=canonical_url,
                enrichment_provider=enrichment_provider,
                enrichment_model=enriched_page.enrichment_model,
                enrichment_chunk_count=len(enriched_page.chunks),
                enrichment_prompt_version=enriched_page.enrichment_prompt_version,
                enrichment_duration_ms=enrichment_duration_ms,
            )
            log_crawl_url_outcome(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=crawl_job_id,
                crawl_domain_id=crawl_url.crawl_domain_id,
                crawl_url_id=crawl_url_id,
                search_index_id=profile_bundle.search_index.search_index_id,
                domain=domain.domain,
                canonical_url=canonical_url,
                crawl_outcome="enriched",
                document_id=crawl_url.document_id,
            )
        except Exception as exc:
            await CrawlUrl.mark_enrichment_failed(crawl_url_id, str(exc))
            await CrawlJob.increment(
                crawl_job_id,
                errors=1,
                urls_enrichment_failed=1,
            )
            log_crawl_enrich_failed(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=crawl_job_id,
                crawl_url_id=crawl_url_id,
                crawl_domain_id=crawl_url.crawl_domain_id,
                search_index_id=profile_bundle.search_index.search_index_id,
                domain=domain.domain,
                canonical_url=canonical_url,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            log_crawl_url_outcome(
                crawl_profile_id=crawl_profile_id,
                crawl_job_id=crawl_job_id,
                crawl_domain_id=crawl_url.crawl_domain_id,
                crawl_url_id=crawl_url_id,
                search_index_id=profile_bundle.search_index.search_index_id,
                domain=domain.domain,
                canonical_url=canonical_url,
                crawl_outcome="enrichment_failed",
                document_id=crawl_url.document_id,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            raise

    async def enqueue_enrichment_backfill(
        self,
        crawl_profile_id: str,
        crawl_job_id: str,
        *,
        limit: int = 100,
    ) -> int:
        profile_bundle = await CrawlProfile.get_with_index(crawl_profile_id)
        if not profile_bundle.profile.llm_enrichment_enabled:
            raise ValueError(f"llm enrichment disabled for crawl profile: {crawl_profile_id}")
        crawl_url_ids = await CrawlUrl.list_indexed_missing_enrichment(
            crawl_profile_id,
            limit=limit,
        )
        for crawl_url_id in crawl_url_ids:
            _ = await enqueue(
                CRAWL_ENRICH_URL,
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
        profile_bundle = await CrawlProfile.get_with_index(crawl_profile_id)
        profile = profile_bundle.profile
        pending = await CrawlUrl.count_pending(crawl_domain_id)
        if pending == 0:
            return
        batch = min(url_budget, profile.max_urls_per_batch, pending)
        parallel = min(batch, profile.http_concurrency)
        for _ in range(parallel):
            _ = await enqueue(
                CRAWL_FETCH_URL,
                crawl_domain_id,
                crawl_job_id,
                crawl_profile_id,
                1,
            )
        log_crawl_domain_scheduled(
            crawl_profile_id=crawl_profile_id,
            crawl_job_id=crawl_job_id,
            crawl_domain_id=crawl_domain_id,
            parallel_fetch_enqueued=parallel,
            url_budget=url_budget,
        )

    def _effective_refresh_interval(
        self,
        domain: CrawlDomain,
        profile_bundle: CrawlProfileWithIndex,
    ) -> int:
        if domain.refresh_interval_seconds is not None:
            return domain.refresh_interval_seconds
        return profile_bundle.profile.refresh_interval_seconds

    async def _adaptive_refresh_interval(
        self,
        domain: CrawlDomain,
        profile_bundle: CrawlProfileWithIndex,
        *,
        now: datetime,
    ) -> int:
        """
        Интервал re-crawl домена по наблюдаемой частоте изменений.

        Доля изменившихся страниц (indexed vs skipped/content_unchanged) за
        lookback-окно масштабирует базовый интервал: часто меняющиеся домены
        (новостники) обходятся до 4x чаще, статичные — до 4x реже.
        Явный per-domain override отключает адаптацию.
        """
        if domain.refresh_interval_seconds is not None:
            return domain.refresh_interval_seconds
        base = profile_bundle.profile.refresh_interval_seconds
        if not self._crawl_config.adaptive_refresh_enabled:
            return base
        lookback_seconds = base * self._crawl_config.adaptive_refresh_lookback_factor
        changed, unchanged = await CrawlUrl.domain_change_stats(
            domain.crawl_domain_id,
            since=now - timedelta(seconds=lookback_seconds),
        )
        sampled = changed + unchanged
        if sampled < self._crawl_config.adaptive_refresh_min_samples:
            return base
        change_ratio = changed / sampled
        # ratio=1 -> base/4, ratio=0.5 -> base, ratio=0 -> base*4.
        adaptive = base * math.pow(4.0, 1.0 - 2.0 * change_ratio)
        return int(
            min(
                max(adaptive, self._crawl_config.adaptive_refresh_min_seconds),
                self._crawl_config.adaptive_refresh_max_seconds,
            )
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
        refresh_interval = await self._adaptive_refresh_interval(domain, profile_bundle, now=now)
        if domain.domain in profile.denylist_domains:
            await CrawlDomain.schedule_next(
                domain.crawl_domain_id,
                now + timedelta(seconds=refresh_interval),
            )
            return False

        pending = await CrawlUrl.count_pending(domain.crawl_domain_id)
        if pending > 0:
            await self._enqueue_domain_fetch(
                crawl_domain_id=domain.crawl_domain_id,
                crawl_job_id=crawl_job_id,
                crawl_profile_id=crawl_profile_id,
                url_budget=profile.max_urls_per_domain_per_tick,
            )
            await CrawlDomain.schedule_next(
                domain.crawl_domain_id,
                now + timedelta(seconds=self._crawl_config.backlog_reschedule_seconds),
            )
            return True

        if self._needs_discovery(domain, profile.sitemap_stale_after_seconds, now):
            _ = await enqueue(
                CRAWL_DISCOVER_DOMAIN,
                domain.crawl_domain_id,
                crawl_job_id,
                crawl_profile_id,
            )
            await CrawlDomain.schedule_next(
                domain.crawl_domain_id,
                now + timedelta(seconds=refresh_interval),
            )
            return True

        # Sitemap свежий и нет pending URL: переносим следующий обход без повторного discovery.
        await CrawlDomain.schedule_next(
            domain.crawl_domain_id,
            now + timedelta(seconds=refresh_interval),
        )
        return False

    async def import_seed(self, body: SeedImportRequest) -> SeedImportResult:
        if body.seed_source != "tranco":
            raise ValueError(f"unsupported seed_source: {body.seed_source}")
        result = await import_tranco_domains(
            body.crawl_profile_id,
            limit=body.tranco_limit,
            ru_com_whitelist=tuple(self._crawl_config.ru_com_whitelist),
            skip_categories=tuple(self._crawl_config.skip_categories),
        )
        log_crawl_seed_completed(
            crawl_profile_id=body.crawl_profile_id,
            seed_imported=result.imported,
            seed_skipped=result.skipped,
        )
        return result

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
        profile_bundle = await CrawlProfile.get_with_index(crawl_profile_id)
        if not profile_bundle.profile.enabled:
            raise ValueError(f"crawl profile disabled: {crawl_profile_id}")
        domain = await CrawlDomain.get(crawl_domain_id)
        if domain is None:
            raise ValueError(f"crawl domain not found: {crawl_domain_id}")
        if domain.crawl_profile_id != crawl_profile_id:
            raise ValueError("crawl_domain_id does not belong to crawl_profile_id")
        if domain.domain in profile_bundle.profile.denylist_domains:
            raise ValueError(f"domain is denylisted: {domain.domain}")

        now = datetime.now(UTC)
        await CrawlDomain.schedule_next(
            crawl_domain_id,
            now,
            last_error=None,
            status="active",
        )
        job = await CrawlJob.start(crawl_profile_id, "manual", None)
        await CrawlJob.increment(job.crawl_job_id, domains_scheduled=1)

        action: Literal["discover", "fetch"]
        if self._needs_discovery(domain, profile_bundle.profile.sitemap_stale_after_seconds, now):
            _ = await enqueue(
                CRAWL_DISCOVER_DOMAIN,
                crawl_domain_id,
                job.crawl_job_id,
                crawl_profile_id,
            )
            action = "discover"
        else:
            pending = await CrawlUrl.count_pending(crawl_domain_id)
            if pending > 0:
                await self._enqueue_domain_fetch(
                    crawl_domain_id=crawl_domain_id,
                    crawl_job_id=job.crawl_job_id,
                    crawl_profile_id=crawl_profile_id,
                    url_budget=profile_bundle.profile.max_urls_per_domain_per_tick,
                )
                action = "fetch"
            else:
                _ = await enqueue(
                    CRAWL_DISCOVER_DOMAIN,
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
