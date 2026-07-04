"""Crawl structured logging contract tests."""

from __future__ import annotations

import pytest

import core.crawl.logging_events as crawl_logging_events
from core.config.models import LoggingConfig
from core.crawl.logging_events import log_crawl_url_outcome
from core.logging import enter_request_scope, exit_request_scope, get_logger
from core.logging.attributes import EVENT_CRAWL_URL_OUTCOME
from core.logging.setup import reset_logging_for_tests, setup_logging
from core.types import JsonObject


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


def _log_event_name(entry: JsonObject) -> str | None:
    event = entry.get("event")
    if isinstance(event, str):
        return event
    message = entry.get("message")
    if isinstance(message, str):
        return message
    return None


def test_log_crawl_url_outcome_emits_event(crawl_log_scope: None) -> None:
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
