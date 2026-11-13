"""Crawl structured logging contract tests."""

from __future__ import annotations

import httpx2
import pytest
from structlog.typing import EventDict

import apps.search.crawl.logging_events as crawl_logging_events
from apps.search.crawl.errors import (
    CrawlErrorKind,
    CrawlExtractTooShortError,
    crawl_error_kind,
)
from apps.search.crawl.logging_events import log_crawl_url_outcome
from core.clients.service_client import ServiceClientError
from core.config.models import LoggingConfig
from core.logging import enter_request_scope, exit_request_scope, get_logger
from core.logging.attributes import EVENT_CRAWL_URL_OUTCOME
from core.logging.setup import reset_logging_for_tests, setup_logging


@pytest.fixture
def crawl_log_scope():
    reset_logging_for_tests()
    setup_logging("search_worker", LoggingConfig(level="INFO"))
    token = enter_request_scope(
        request_id="test-request-id",
        trace_id="crawl:test:job",
        service_name="search_worker",
    )
    yield
    exit_request_scope(token)
    reset_logging_for_tests()


def _log_event_name(entry: EventDict) -> str | None:
    event = entry.get("event")
    if isinstance(event, str):
        return event
    message = entry.get("message")
    if isinstance(message, str):
        return message
    return None


def test_log_crawl_url_outcome_emits_event(crawl_log_scope: None) -> None:
    _ = crawl_log_scope
    from structlog.testing import capture_logs

    with capture_logs() as captured_entries:
        # capture_logs переконфигурирует processors; перепривязываем module logger.
        crawl_logging_events.logger = get_logger("platform.crawl")
        log_crawl_url_outcome(
            crawl_profile_id="runet_platform",
            crawl_job_id="job-1",
            crawl_domain_id="domain-1",
            crawl_url_id="url-1",
            search_index_id="runet",
            domain="example.com",
            canonical_url="https://example.com/page",
            crawl_outcome="indexed",
            fetch_transport="http",
            extract_chars=1200,
            content_hash_changed=True,
            document_id="runet:abc",
        )
    assert any(_log_event_name(entry) == EVENT_CRAWL_URL_OUTCOME for entry in captured_entries)
    indexed_entry = next(
        entry for entry in captured_entries if _log_event_name(entry) == EVENT_CRAWL_URL_OUTCOME
    )
    assert indexed_entry.get("crawl_profile_id") == "runet_platform"
    assert indexed_entry.get("crawl_outcome") == "indexed"


def _outcome_entry(entries: list[EventDict]) -> EventDict:
    return next(
        entry for entry in entries if _log_event_name(entry) == EVENT_CRAWL_URL_OUTCOME
    )


def _log_failed_url(*, error_kind: CrawlErrorKind) -> list[EventDict]:
    from structlog.testing import capture_logs

    with capture_logs() as captured_entries:
        crawl_logging_events.logger = get_logger("platform.crawl")
        log_crawl_url_outcome(
            crawl_profile_id="runet_platform",
            crawl_job_id="job-1",
            crawl_domain_id="domain-1",
            crawl_url_id="url-1",
            search_index_id="runet",
            domain="example.com",
            canonical_url="https://example.com/page",
            crawl_outcome="failed",
            error_kind=error_kind,
            exception_type="ConnectError",
            exception_message="connection refused",
        )
    return captured_entries


def test_crawl_url_outcome_domain_failure_is_warning(crawl_log_scope: None) -> None:
    """Исход сайта (connect/timeout/4xx) — WARNING, а не ошибка платформы."""
    _ = crawl_log_scope
    entry = _outcome_entry(_log_failed_url(error_kind="domain"))
    assert entry.get("log_level") == "warning"
    assert entry.get("crawl_error_kind") == "domain"


def test_crawl_url_outcome_platform_failure_is_error(crawl_log_scope: None) -> None:
    """Отказ платформы — ERROR."""
    _ = crawl_log_scope
    entry = _outcome_entry(_log_failed_url(error_kind="platform"))
    assert entry.get("log_level") == "error"


def test_crawl_error_kind_classification() -> None:
    """Классификатор: целевой сайт → domain, внутренний сбой → platform."""
    request = httpx2.Request("GET", "https://example.com")
    response = httpx2.Response(403, request=request)
    assert (
        crawl_error_kind(
            httpx2.HTTPStatusError("403", request=request, response=response)
        )
        == "domain"
    )
    assert crawl_error_kind(httpx2.ConnectError("refused")) == "domain"
    assert crawl_error_kind(httpx2.ReadTimeout("slow")) == "domain"
    assert crawl_error_kind(CrawlExtractTooShortError("https://x")) == "domain"
    # Browser-service ответил upstream-контрактом — исход сайта.
    assert (
        crawl_error_kind(ServiceClientError("HTTP 502", status_code=502)) == "domain"
    )
    assert (
        crawl_error_kind(ServiceClientError("HTTP 429", status_code=429)) == "domain"
    )
    # 500 от browser-service и любые внутренние ошибки — отказ платформы.
    assert (
        crawl_error_kind(ServiceClientError("HTTP 500", status_code=500)) == "platform"
    )
    assert crawl_error_kind(RuntimeError("bug")) == "platform"
