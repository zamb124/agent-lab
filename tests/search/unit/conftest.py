"""Unit-тесты search без PostgreSQL / session-инфры."""

from __future__ import annotations

import pytest

from core.search.index_models import SearchIndexCrawlTaxonomy

_TEST_CRAWL_TAXONOMY = SearchIndexCrawlTaxonomy(
    primary_topics=["tech", "other", "documentation"],
    topic_tags=["tech", "software", "other", "documentation", "faq"],
    category_paths=[["tech"], ["other"]],
)


@pytest.fixture(scope="session", autouse=True)
def setup_database_before_tests():
    yield


@pytest.fixture(scope="session", autouse=True)
def platform_notification_manager_redis(setup_database_before_tests):
    _ = setup_database_before_tests
    yield


@pytest.fixture(autouse=True)
def crawl_taxonomy_for_search_unit_tests(monkeypatch):
    def _resolve(search_index_id: str) -> SearchIndexCrawlTaxonomy:
        _ = search_index_id
        return _TEST_CRAWL_TAXONOMY

    monkeypatch.setattr(
        "apps.search.services.crawl.page_enrichment_service.resolve_crawl_taxonomy",
        _resolve,
    )
