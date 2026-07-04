"""Crawl structured logging contract tests."""

from __future__ import annotations

import logging

import pytest

from core.crawl.logging_events import log_crawl_url_outcome
from core.logging import enter_request_scope, exit_request_scope
from core.logging.attributes import EVENT_CRAWL_URL_OUTCOME
from core.logging.setup import reset_logging_for_tests, setup_logging


@pytest.fixture
def crawl_log_scope():
    reset_logging_for_tests()
    setup_logging("search_worker")
    token = enter_request_scope(
        request_id="test-request-id",
        trace_id="crawl:test:job",
        service_name="search_worker",
    )
    yield
    exit_request_scope(token)
    reset_logging_for_tests()


def test_log_crawl_url_outcome_emits_event(crawl_log_scope: None) -> None:
    captured: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    root_logger = logging.getLogger()
    handler = _CaptureHandler()
    root_logger.addHandler(handler)
    try:
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
        combined = "\n".join(captured)
        assert EVENT_CRAWL_URL_OUTCOME in combined
        assert "runet_platform" in combined
        assert "crawl_outcome" in combined
    finally:
        root_logger.removeHandler(handler)
