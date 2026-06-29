"""Structured crawl pipeline log events for Loki/Grafana."""

from __future__ import annotations

from typing import Literal

from core.logging import get_logger
from core.logging.attributes import (
    EVENT_CRAWL_BOOTSTRAP,
    EVENT_CRAWL_DISCOVER_COMPLETED,
    EVENT_CRAWL_DISCOVER_FAILED,
    EVENT_CRAWL_DOMAIN_SCHEDULED,
    EVENT_CRAWL_ENRICH_COMPLETED,
    EVENT_CRAWL_ENRICH_FAILED,
    EVENT_CRAWL_FETCH_COMPLETED,
    EVENT_CRAWL_FETCH_FAILED,
    EVENT_CRAWL_INGEST_COMPLETED,
    EVENT_CRAWL_INGEST_FAILED,
    EVENT_CRAWL_RECLAIM_COMPLETED,
    EVENT_CRAWL_REINGEST_COMPLETED,
    EVENT_CRAWL_SEED_COMPLETED,
    EVENT_CRAWL_TICK_COMPLETED,
    EVENT_CRAWL_TICK_FAILED,
    EVENT_CRAWL_TICK_STARTED,
    EVENT_CRAWL_URL_OUTCOME,
    LOG_CRAWL_BOOTSTRAP_ACTION,
    LOG_CRAWL_BROWSER_FALLBACK,
    LOG_CRAWL_CANONICAL_URL,
    LOG_CRAWL_CONTENT_HASH_CHANGED,
    LOG_CRAWL_DOCUMENT_ID,
    LOG_CRAWL_DOMAIN,
    LOG_CRAWL_DOMAIN_COUNT,
    LOG_CRAWL_DOMAIN_ID,
    LOG_CRAWL_DOMAINS_SCHEDULED,
    LOG_CRAWL_ENRICHMENT_CHUNK_COUNT,
    LOG_CRAWL_ENRICHMENT_DURATION_MS,
    LOG_CRAWL_ENRICHMENT_MODEL,
    LOG_CRAWL_ENRICHMENT_PROMPT_VERSION,
    LOG_CRAWL_ENRICHMENT_PROVIDER,
    LOG_CRAWL_EXTRACT_CHARS,
    LOG_CRAWL_FETCH_ATTEMPTS,
    LOG_CRAWL_FETCH_DURATION_MS,
    LOG_CRAWL_FETCH_TRANSPORT,
    LOG_CRAWL_INGEST_DURATION_MS,
    LOG_CRAWL_JOB_ID,
    LOG_CRAWL_OUTCOME,
    LOG_CRAWL_PARALLEL_FETCH_ENQUEUED,
    LOG_CRAWL_PENDING_URLS,
    LOG_CRAWL_PROFILE_ID,
    LOG_CRAWL_RAG_NAMESPACE_ID,
    LOG_CRAWL_RECLAIMED_FETCHING,
    LOG_CRAWL_REQUEUED_FAILED,
    LOG_CRAWL_SEED_IMPORTED,
    LOG_CRAWL_SEED_SKIPPED,
    LOG_CRAWL_SITEMAP_ERROR_KIND,
    LOG_CRAWL_SKIP_REASON,
    LOG_CRAWL_STALE_JOBS_FINISHED,
    LOG_CRAWL_TRIGGER,
    LOG_CRAWL_URL_BUDGET,
    LOG_CRAWL_URL_ID,
    LOG_CRAWL_URLS_DISCOVERED,
    LOG_CRAWL_URLS_INSERTED,
    LOG_CRAWL_URLS_UPDATED,
    LOG_EXCEPTION_MESSAGE,
    LOG_EXCEPTION_TYPE,
    LOG_HTTP_STATUS_CODE,
    LOG_SEARCH_INDEX_ID,
)

logger = get_logger("platform.crawl")

CrawlOutcome = Literal["indexed", "skipped", "failed", "enriched", "enrichment_failed"]
CrawlSkipReason = Literal["extract_too_short", "content_unchanged", "filter_rejected"]
CrawlTrigger = Literal["scheduler", "manual", "api"]


def _truncate_url(url: str, max_len: int = 256) -> str:
    if len(url) <= max_len:
        return url
    return url[:max_len]


def log_crawl_tick_started(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    search_index_id: str,
    crawl_trigger: CrawlTrigger,
) -> None:
    logger.info(
        EVENT_CRAWL_TICK_STARTED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_SEARCH_INDEX_ID: search_index_id,
            LOG_CRAWL_TRIGGER: crawl_trigger,
        },
    )


def log_crawl_tick_completed(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    search_index_id: str,
    crawl_trigger: CrawlTrigger,
    domains_scheduled: int,
    pending_urls: int,
) -> None:
    logger.info(
        EVENT_CRAWL_TICK_COMPLETED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_SEARCH_INDEX_ID: search_index_id,
            LOG_CRAWL_TRIGGER: crawl_trigger,
            LOG_CRAWL_DOMAINS_SCHEDULED: domains_scheduled,
            LOG_CRAWL_PENDING_URLS: pending_urls,
        },
    )


def log_crawl_tick_failed(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    search_index_id: str,
    crawl_trigger: CrawlTrigger,
    exception_type: str,
    exception_message: str,
) -> None:
    logger.error(
        EVENT_CRAWL_TICK_FAILED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_SEARCH_INDEX_ID: search_index_id,
            LOG_CRAWL_TRIGGER: crawl_trigger,
            LOG_EXCEPTION_TYPE: exception_type,
            LOG_EXCEPTION_MESSAGE: exception_message,
        },
    )


def log_crawl_discover_completed(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    crawl_domain_id: str,
    search_index_id: str,
    domain: str,
    urls_discovered: int,
    urls_inserted: int,
    urls_updated: int,
) -> None:
    logger.info(
        EVENT_CRAWL_DISCOVER_COMPLETED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_CRAWL_DOMAIN_ID: crawl_domain_id,
            LOG_SEARCH_INDEX_ID: search_index_id,
            LOG_CRAWL_DOMAIN: domain,
            LOG_CRAWL_URLS_DISCOVERED: urls_discovered,
            LOG_CRAWL_URLS_INSERTED: urls_inserted,
            LOG_CRAWL_URLS_UPDATED: urls_updated,
        },
    )


def log_crawl_discover_failed(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    crawl_domain_id: str,
    search_index_id: str,
    domain: str,
    sitemap_error_kind: str,
    exception_message: str,
) -> None:
    logger.error(
        EVENT_CRAWL_DISCOVER_FAILED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_CRAWL_DOMAIN_ID: crawl_domain_id,
            LOG_SEARCH_INDEX_ID: search_index_id,
            LOG_CRAWL_DOMAIN: domain,
            LOG_CRAWL_SITEMAP_ERROR_KIND: sitemap_error_kind,
            LOG_EXCEPTION_MESSAGE: exception_message,
        },
    )


def log_crawl_fetch_completed(
    *,
    canonical_url: str,
    fetch_transport: str,
    fetch_duration_ms: int,
    extract_chars: int,
    browser_fallback: bool,
    http_status_code: int | None = None,
) -> None:
    fields: dict[str, object] = {
        LOG_CRAWL_CANONICAL_URL: _truncate_url(canonical_url),
        LOG_CRAWL_FETCH_TRANSPORT: fetch_transport,
        LOG_CRAWL_FETCH_DURATION_MS: fetch_duration_ms,
        LOG_CRAWL_EXTRACT_CHARS: extract_chars,
        LOG_CRAWL_BROWSER_FALLBACK: browser_fallback,
    }
    if http_status_code is not None:
        fields[LOG_HTTP_STATUS_CODE] = http_status_code
    logger.info(EVENT_CRAWL_FETCH_COMPLETED, **fields)


def log_crawl_fetch_failed(
    *,
    canonical_url: str,
    fetch_duration_ms: int,
    browser_fallback: bool,
    exception_type: str,
    exception_message: str,
    http_status_code: int | None = None,
) -> None:
    fields: dict[str, object] = {
        LOG_CRAWL_CANONICAL_URL: _truncate_url(canonical_url),
        LOG_CRAWL_FETCH_DURATION_MS: fetch_duration_ms,
        LOG_CRAWL_BROWSER_FALLBACK: browser_fallback,
        LOG_EXCEPTION_TYPE: exception_type,
        LOG_EXCEPTION_MESSAGE: exception_message,
    }
    if http_status_code is not None:
        fields[LOG_HTTP_STATUS_CODE] = http_status_code
    logger.error(EVENT_CRAWL_FETCH_FAILED, **fields)


def log_crawl_url_outcome(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    crawl_domain_id: str,
    crawl_url_id: str,
    search_index_id: str,
    domain: str,
    canonical_url: str,
    crawl_outcome: CrawlOutcome,
    crawl_skip_reason: CrawlSkipReason | None = None,
    fetch_transport: str | None = None,
    extract_chars: int | None = None,
    content_hash_changed: bool | None = None,
    fetch_attempts: int | None = None,
    document_id: str | None = None,
    exception_type: str | None = None,
    exception_message: str | None = None,
) -> None:
    fields: dict[str, object] = {
        LOG_CRAWL_PROFILE_ID: crawl_profile_id,
        LOG_CRAWL_JOB_ID: crawl_job_id,
        LOG_CRAWL_DOMAIN_ID: crawl_domain_id,
        LOG_CRAWL_URL_ID: crawl_url_id,
        LOG_SEARCH_INDEX_ID: search_index_id,
        LOG_CRAWL_DOMAIN: domain,
        LOG_CRAWL_CANONICAL_URL: _truncate_url(canonical_url),
        LOG_CRAWL_OUTCOME: crawl_outcome,
    }
    if crawl_skip_reason is not None:
        fields[LOG_CRAWL_SKIP_REASON] = crawl_skip_reason
    if fetch_transport is not None:
        fields[LOG_CRAWL_FETCH_TRANSPORT] = fetch_transport
    if extract_chars is not None:
        fields[LOG_CRAWL_EXTRACT_CHARS] = extract_chars
    if content_hash_changed is not None:
        fields[LOG_CRAWL_CONTENT_HASH_CHANGED] = content_hash_changed
    if fetch_attempts is not None:
        fields[LOG_CRAWL_FETCH_ATTEMPTS] = fetch_attempts
    if document_id is not None:
        fields[LOG_CRAWL_DOCUMENT_ID] = document_id
    if exception_type is not None:
        fields[LOG_EXCEPTION_TYPE] = exception_type
    if exception_message is not None:
        fields[LOG_EXCEPTION_MESSAGE] = exception_message
    if crawl_outcome in ("failed", "enrichment_failed"):
        logger.error(EVENT_CRAWL_URL_OUTCOME, **fields)
    else:
        logger.info(EVENT_CRAWL_URL_OUTCOME, **fields)


def log_crawl_domain_scheduled(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    crawl_domain_id: str,
    parallel_fetch_enqueued: int,
    url_budget: int,
) -> None:
    logger.info(
        EVENT_CRAWL_DOMAIN_SCHEDULED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_CRAWL_DOMAIN_ID: crawl_domain_id,
            LOG_CRAWL_PARALLEL_FETCH_ENQUEUED: parallel_fetch_enqueued,
            LOG_CRAWL_URL_BUDGET: url_budget,
        },
    )


def log_crawl_ingest_completed(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    search_index_id: str,
    crawl_domain_id: str,
    domain: str,
    document_id: str,
    rag_namespace_id: str,
    ingest_duration_ms: int,
    canonical_url: str,
) -> None:
    logger.info(
        EVENT_CRAWL_INGEST_COMPLETED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_SEARCH_INDEX_ID: search_index_id,
            LOG_CRAWL_DOMAIN_ID: crawl_domain_id,
            LOG_CRAWL_DOMAIN: domain,
            LOG_CRAWL_DOCUMENT_ID: document_id,
            LOG_CRAWL_RAG_NAMESPACE_ID: rag_namespace_id,
            LOG_CRAWL_INGEST_DURATION_MS: ingest_duration_ms,
            LOG_CRAWL_CANONICAL_URL: _truncate_url(canonical_url),
        },
    )


def log_crawl_ingest_failed(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    search_index_id: str,
    crawl_domain_id: str,
    domain: str,
    canonical_url: str,
    ingest_duration_ms: int,
    exception_type: str,
    exception_message: str,
) -> None:
    logger.error(
        EVENT_CRAWL_INGEST_FAILED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_SEARCH_INDEX_ID: search_index_id,
            LOG_CRAWL_DOMAIN_ID: crawl_domain_id,
            LOG_CRAWL_DOMAIN: domain,
            LOG_CRAWL_CANONICAL_URL: _truncate_url(canonical_url),
            LOG_CRAWL_INGEST_DURATION_MS: ingest_duration_ms,
            LOG_EXCEPTION_TYPE: exception_type,
            LOG_EXCEPTION_MESSAGE: exception_message,
        },
    )


def log_crawl_reingest_completed(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    search_index_id: str,
    crawl_domain_id: str,
    domain: str,
    document_id: str,
    rag_namespace_id: str,
    ingest_duration_ms: int,
    canonical_url: str,
) -> None:
    logger.info(
        EVENT_CRAWL_REINGEST_COMPLETED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_SEARCH_INDEX_ID: search_index_id,
            LOG_CRAWL_DOMAIN_ID: crawl_domain_id,
            LOG_CRAWL_DOMAIN: domain,
            LOG_CRAWL_DOCUMENT_ID: document_id,
            LOG_CRAWL_RAG_NAMESPACE_ID: rag_namespace_id,
            LOG_CRAWL_INGEST_DURATION_MS: ingest_duration_ms,
            LOG_CRAWL_CANONICAL_URL: _truncate_url(canonical_url),
        },
    )


def log_crawl_enrich_completed(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    crawl_url_id: str,
    crawl_domain_id: str,
    search_index_id: str,
    domain: str,
    canonical_url: str,
    enrichment_provider: str,
    enrichment_model: str,
    enrichment_chunk_count: int,
    enrichment_prompt_version: str,
    enrichment_duration_ms: int,
) -> None:
    logger.info(
        EVENT_CRAWL_ENRICH_COMPLETED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_CRAWL_URL_ID: crawl_url_id,
            LOG_CRAWL_DOMAIN_ID: crawl_domain_id,
            LOG_SEARCH_INDEX_ID: search_index_id,
            LOG_CRAWL_DOMAIN: domain,
            LOG_CRAWL_CANONICAL_URL: _truncate_url(canonical_url),
            LOG_CRAWL_ENRICHMENT_PROVIDER: enrichment_provider,
            LOG_CRAWL_ENRICHMENT_MODEL: enrichment_model,
            LOG_CRAWL_ENRICHMENT_CHUNK_COUNT: enrichment_chunk_count,
            LOG_CRAWL_ENRICHMENT_PROMPT_VERSION: enrichment_prompt_version,
            LOG_CRAWL_ENRICHMENT_DURATION_MS: enrichment_duration_ms,
        },
    )


def log_crawl_enrich_failed(
    *,
    crawl_profile_id: str,
    crawl_job_id: str,
    crawl_url_id: str,
    crawl_domain_id: str,
    search_index_id: str,
    domain: str,
    canonical_url: str,
    exception_type: str,
    exception_message: str,
) -> None:
    logger.error(
        EVENT_CRAWL_ENRICH_FAILED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_JOB_ID: crawl_job_id,
            LOG_CRAWL_URL_ID: crawl_url_id,
            LOG_CRAWL_DOMAIN_ID: crawl_domain_id,
            LOG_SEARCH_INDEX_ID: search_index_id,
            LOG_CRAWL_DOMAIN: domain,
            LOG_CRAWL_CANONICAL_URL: _truncate_url(canonical_url),
            LOG_EXCEPTION_TYPE: exception_type,
            LOG_EXCEPTION_MESSAGE: exception_message,
        },
    )


def log_crawl_seed_completed(
    *,
    crawl_profile_id: str,
    seed_imported: int,
    seed_skipped: int,
) -> None:
    logger.info(
        EVENT_CRAWL_SEED_COMPLETED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_SEED_IMPORTED: seed_imported,
            LOG_CRAWL_SEED_SKIPPED: seed_skipped,
        },
    )


def log_crawl_reclaim_completed(
    *,
    crawl_profile_id: str,
    stale_jobs_finished: int,
    reclaimed_fetching: int,
    requeued_failed: int,
    pending_urls: int,
) -> None:
    logger.info(
        EVENT_CRAWL_RECLAIM_COMPLETED,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_STALE_JOBS_FINISHED: stale_jobs_finished,
            LOG_CRAWL_RECLAIMED_FETCHING: reclaimed_fetching,
            LOG_CRAWL_REQUEUED_FAILED: requeued_failed,
            LOG_CRAWL_PENDING_URLS: pending_urls,
        },
    )


def log_crawl_bootstrap(
    *,
    crawl_profile_id: str,
    action: str,
    domain_count: int,
) -> None:
    logger.info(
        EVENT_CRAWL_BOOTSTRAP,
        **{
            LOG_CRAWL_PROFILE_ID: crawl_profile_id,
            LOG_CRAWL_BOOTSTRAP_ACTION: action,
            LOG_CRAWL_DOMAIN_COUNT: domain_count,
        },
    )
