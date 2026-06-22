"""Unit tests for CrawlUrlFilter and profile/domain merge."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.crawl.models import CrawlDomain, CrawlProfile
from core.crawl.url_filter import CrawlUrlFilter, build_url_filter

pytestmark = pytest.mark.unit


def _profile(**overrides: object) -> CrawlProfile:
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "crawl_profile_id": "cr_test",
        "search_index_id": "runet",
        "enabled": True,
        "seed_source": "manual",
        "refresh_interval_seconds": 21600,
        "max_urls_per_domain_per_tick": 10,
        "max_domains_per_tick": 10,
        "max_urls_per_batch": 10,
        "http_concurrency": 2,
        "browser_fallback_enabled": True,
        "sitemap_stale_after_seconds": 86400,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return CrawlProfile.model_validate(base)


def _domain(**overrides: object) -> CrawlDomain:
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "crawl_domain_id": "dom-1",
        "crawl_profile_id": "cr_test",
        "domain": "example.com",
        "category": "manual",
        "status": "active",
        "next_crawl_after": now,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return CrawlDomain.model_validate(base)


def test_filter_blocks_excluded_extension() -> None:
    url_filter = CrawlUrlFilter(
        include_patterns=[],
        exclude_patterns=[],
        exclude_extensions=["pdf"],
    )
    assert url_filter.allows("https://example.com/page") is True
    assert url_filter.allows("https://example.com/file.pdf") is False


def test_filter_blocks_excluded_path_pattern() -> None:
    url_filter = CrawlUrlFilter(
        include_patterns=[],
        exclude_patterns=[r"/login(/|$)"],
        exclude_extensions=[],
    )
    assert url_filter.allows("https://example.com/login") is False
    assert url_filter.allows("https://example.com/articles/login-guide") is True


def test_filter_include_restricts_to_matching_paths() -> None:
    url_filter = CrawlUrlFilter(
        include_patterns=[r"^/docs/"],
        exclude_patterns=[],
        exclude_extensions=[],
    )
    assert url_filter.allows("https://example.com/docs/intro") is True
    assert url_filter.allows("https://example.com/blog/post") is False


def test_invalid_pattern_raises() -> None:
    with pytest.raises(ValueError):
        CrawlUrlFilter(include_patterns=["("], exclude_patterns=[], exclude_extensions=[])


def test_build_url_filter_merges_domain_over_profile() -> None:
    profile = _profile(
        include_url_patterns=[],
        exclude_url_patterns=[r"/profile-deny(/|$)"],
        exclude_extensions=["pdf"],
    )
    domain = _domain(
        include_url_patterns=[r"^/only-this/"],
        exclude_url_patterns=[r"/domain-deny(/|$)"],
    )
    url_filter = build_url_filter(profile, domain)

    # include из домена перекрывает (профильный include пуст) — пропускаем только /only-this/
    assert url_filter.allows("https://example.com/only-this/page") is True
    assert url_filter.allows("https://example.com/other") is False
    # exclude профиля и домена объединяются
    assert url_filter.allows("https://example.com/only-this/domain-deny") is False
    # расширения берутся из профиля
    assert url_filter.allows("https://example.com/only-this/file.pdf") is False
