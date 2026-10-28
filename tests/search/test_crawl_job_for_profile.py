"""Чтение одного запуска профиля: активный и последний."""

from datetime import UTC, datetime

import pytest

from core.crawl.models import CrawlJob


@pytest.mark.asyncio
async def test_active_and_latest_for_profile(unique_id: str) -> None:
    profile_id = f"cr-{unique_id}"[:64]
    other_id = f"ot-{unique_id}"[:64]
    assert await CrawlJob.active_for_profile(profile_id) is None
    assert await CrawlJob.latest_for_profile(profile_id) is None

    older = await CrawlJob.start(profile_id, "manual", None)
    older.started_at = datetime(2026, 1, 1, tzinfo=UTC)
    _ = await older.save()
    _ = await CrawlJob.finish(older.crawl_job_id, status="completed")

    newer = await CrawlJob.start(profile_id, "manual", None)
    newer.started_at = datetime(2026, 6, 1, tzinfo=UTC)
    _ = await newer.save()

    active = await CrawlJob.active_for_profile(profile_id)
    latest = await CrawlJob.latest_for_profile(profile_id)
    assert active is not None
    assert latest is not None
    assert active.crawl_job_id == newer.crawl_job_id
    assert latest.crawl_job_id == newer.crawl_job_id

    _ = await CrawlJob.finish(newer.crawl_job_id, status="completed")
    assert await CrawlJob.active_for_profile(profile_id) is None
    finished_latest = await CrawlJob.latest_for_profile(profile_id)
    assert finished_latest is not None
    assert finished_latest.crawl_job_id == newer.crawl_job_id

    other = await CrawlJob.start(other_id, "manual", None)
    other.started_at = datetime(2026, 12, 1, tzinfo=UTC)
    _ = await other.save()
    still = await CrawlJob.latest_for_profile(profile_id)
    assert still is not None
    assert still.crawl_job_id == newer.crawl_job_id
    other_active = await CrawlJob.active_for_profile(other_id)
    assert other_active is not None
    assert other_active.crawl_job_id == other.crawl_job_id
