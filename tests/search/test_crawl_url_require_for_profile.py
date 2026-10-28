"""Обязательное чтение URL внутри профиля обхода."""

import uuid
from datetime import UTC, datetime

import pytest

from core.crawl.models import CrawlDomain, CrawlUrl
from core.errors.boundary import PlatformNotFoundError


def _domain(
    *,
    crawl_domain_id: str,
    crawl_profile_id: str,
    domain: str,
    now: datetime,
) -> CrawlDomain:
    return CrawlDomain(
        crawl_domain_id=crawl_domain_id,
        crawl_profile_id=crawl_profile_id,
        domain=domain,
        category="docs",
        status="active",
        next_crawl_after=now,
        created_at=now,
        updated_at=now,
    )


def _url(
    *,
    crawl_url_id: str,
    crawl_domain_id: str,
    now: datetime,
) -> CrawlUrl:
    return CrawlUrl(
        crawl_url_id=crawl_url_id,
        crawl_domain_id=crawl_domain_id,
        url="https://example.test/page",
        canonical_url="https://example.test/page",
        crawl_status="indexed",
        extract_title="Page title",
        extract_markdown="Page body",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_require_for_profile_returns_projection_or_not_found(unique_id: str) -> None:
    missing_url_id = str(uuid.uuid4())
    with pytest.raises(PlatformNotFoundError, match="crawl url not found"):
        _ = await CrawlUrl.require_for_profile(missing_url_id, f"cr-{unique_id}"[:64])

    now = datetime(2026, 10, 26, tzinfo=UTC)
    profile_id = f"cr-{unique_id}"[:64]
    other_profile_id = f"ot-{unique_id}"[:64]
    domain_id = str(uuid.uuid4())
    other_domain_id = str(uuid.uuid4())
    url_id = str(uuid.uuid4())
    _ = await CrawlDomain.objects.create(
        instance=_domain(
            crawl_domain_id=domain_id,
            crawl_profile_id=profile_id,
            domain=f"{unique_id}.example.test",
            now=now,
        )
    )
    _ = await CrawlDomain.objects.create(
        instance=_domain(
            crawl_domain_id=other_domain_id,
            crawl_profile_id=other_profile_id,
            domain=f"other-{unique_id}.example.test",
            now=now,
        )
    )
    _ = await CrawlUrl.objects.create(
        instance=_url(crawl_url_id=url_id, crawl_domain_id=domain_id, now=now)
    )

    item, title, markdown = await CrawlUrl.require_for_profile(url_id, profile_id)
    assert item.crawl_url_id == url_id
    assert item.domain == f"{unique_id}.example.test"
    assert title == "Page title"
    assert markdown == "Page body"
    again_item, again_title, again_markdown = await CrawlUrl.require_for_profile(url_id, profile_id)
    assert again_item.crawl_url_id == item.crawl_url_id
    assert again_title == title
    assert again_markdown == markdown

    with pytest.raises(PlatformNotFoundError, match="crawl url not found"):
        _ = await CrawlUrl.require_for_profile(url_id, other_profile_id)


@pytest.mark.asyncio
async def test_require_layer1_snapshot_returns_extract_or_not_found(unique_id: str) -> None:
    missing_url_id = str(uuid.uuid4())
    with pytest.raises(PlatformNotFoundError, match="crawl url not found"):
        _ = await CrawlUrl.require_layer1_snapshot(missing_url_id)

    now = datetime(2026, 10, 26, tzinfo=UTC)
    domain_id = str(uuid.uuid4())
    bare_url_id = str(uuid.uuid4())
    ready_url_id = str(uuid.uuid4())
    _ = await CrawlDomain.objects.create(
        instance=_domain(
            crawl_domain_id=domain_id,
            crawl_profile_id=f"cr-{unique_id}"[:64],
            domain=f"layer-{unique_id}.example.test",
            now=now,
        )
    )
    _ = await CrawlUrl.objects.create(
        instance=_url(crawl_url_id=bare_url_id, crawl_domain_id=domain_id, now=now)
    )
    with pytest.raises(ValueError, match="extract_content_hash is missing"):
        _ = await CrawlUrl.require_layer1_snapshot(bare_url_id)

    ready = _url(crawl_url_id=ready_url_id, crawl_domain_id=domain_id, now=now)
    ready.extract_content_hash = "hash-1"
    ready.canonical_url = "https://example.test/ready"
    _ = await CrawlUrl.objects.create(instance=ready)
    url, canonical_url, markdown, title, content_hash, signals = await CrawlUrl.require_layer1_snapshot(
        ready_url_id
    )
    assert url == "https://example.test/page"
    assert canonical_url == "https://example.test/ready"
    assert markdown == "Page body"
    assert title == "Page title"
    assert content_hash == "hash-1"
    assert signals.title is None
