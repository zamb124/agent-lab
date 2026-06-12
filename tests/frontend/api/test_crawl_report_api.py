"""Frontend crawl report API integration tests (real Postgres, no mocks)."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from apps.frontend.config import reset_frontend_settings
from core.crawl.models import CrawlDomainSeed
from tests.search.integration.test_crawl_report_api import _create_profile

pytest_plugins = ["tests.search.conftest"]

pytestmark = pytest.mark.timeout(60, func_only=True)


@pytest_asyncio.fixture
async def frontend_client_system(frontend_app, auth_token_system):
    async with AsyncClient(
        transport=ASGITransport(app=frontend_app),
        base_url="http://testserver",
        cookies={"auth_token": auth_token_system},
        follow_redirects=True,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_crawl_report_summary_system(
    frontend_client_system,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)
    now = datetime.now(UTC)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain="frontend-report.example.com", category="news")],
        next_crawl_after=now,
    )

    response = await frontend_client_system.get(
        f"/frontend/api/crawl-report/profiles/{crawl_profile_id}/summary",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["domains_total"] == 1


@pytest.mark.asyncio
async def test_crawl_report_list_endpoints_system(
    frontend_client_system,
    search_container,
    search_system_context,
    unique_id,
):
    _ = search_system_context
    crawl_profile_id = await _create_profile(search_container, unique_id)

    domains = await frontend_client_system.get(
        "/frontend/api/crawl-report/domains",
        params={"crawl_profile_id": crawl_profile_id, "limit": 10, "offset": 0},
    )
    assert domains.status_code == 200
    assert domains.json()["total"] == 0

    urls = await frontend_client_system.get(
        "/frontend/api/crawl-report/urls",
        params={"crawl_profile_id": crawl_profile_id, "limit": 10, "offset": 0},
    )
    assert urls.status_code == 200

    jobs = await frontend_client_system.get(
        "/frontend/api/crawl-report/jobs",
        params={"crawl_profile_id": crawl_profile_id, "limit": 10, "offset": 0},
    )
    assert jobs.status_code == 200


@pytest.mark.asyncio
async def test_crawl_report_forbidden_for_non_system(frontend_client_with_auth):
    response = await frontend_client_with_auth.get(
        "/frontend/api/crawl-report/profiles",
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_crawl_report_unavailable_without_search_db(frontend_client_system):
    search_url = os.environ.get("DATABASE__SEARCH_URL")
    agent_config_path = os.environ.get("AGENT_CONFIG_PATH")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as config_file:
        json.dump({"database": {"search_url": None}}, config_file)
        override_config_path = config_file.name
    if search_url is not None:
        del os.environ["DATABASE__SEARCH_URL"]
    os.environ["AGENT_CONFIG_PATH"] = override_config_path
    reset_frontend_settings()
    try:
        response = await frontend_client_system.get("/frontend/api/crawl-report/profiles")
        assert response.status_code == 503
        assert "DATABASE__SEARCH_URL" in response.json()["detail"]
    finally:
        os.unlink(override_config_path)
        if search_url is not None:
            os.environ["DATABASE__SEARCH_URL"] = search_url
        if agent_config_path is not None:
            os.environ["AGENT_CONFIG_PATH"] = agent_config_path
        else:
            _ = os.environ.pop("AGENT_CONFIG_PATH", None)
        reset_frontend_settings()


@pytest.mark.asyncio
async def test_crawl_report_run_domain_system(
    frontend_client_system,
    search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    _ = search_system_context

    async def _noop_enqueue(task_name: str, *args: object, **kwargs: object) -> None:
        _ = task_name
        _ = args
        _ = kwargs

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _noop_enqueue,
    )

    crawl_profile_id = await _create_profile(search_container, unique_id)
    now = datetime.now(UTC)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain="frontend-run.example.com", category="news")],
        next_crawl_after=now,
    )
    domain = (
        await search_container.crawl_domain_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=None,
            limit=1,
            offset=0,
        )
    ).items[0]

    response = await frontend_client_system.post(
        f"/frontend/api/crawl-report/domains/{domain.crawl_domain_id}/run",
        params={"crawl_profile_id": crawl_profile_id},
        json={},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["crawl_domain_id"] == domain.crawl_domain_id
    assert payload["status"] == "queued"


@pytest.mark.asyncio
async def test_crawl_report_run_domain_system(
    frontend_client_system,
    search_container,
    search_system_context,
    unique_id,
    monkeypatch: pytest.MonkeyPatch,
):
    _ = search_system_context

    async def _noop_enqueue(task_name: str, *args: object, **kwargs: object) -> None:
        _ = task_name
        _ = args
        _ = kwargs

    monkeypatch.setattr(
        "apps.search.services.crawl.orchestrator_service._enqueue_task",
        _noop_enqueue,
    )

    crawl_profile_id = await _create_profile(search_container, unique_id)
    now = datetime.now(UTC)
    await search_container.crawl_domain_repository.upsert_seed_batch(
        crawl_profile_id,
        [CrawlDomainSeed(domain="frontend-run.example.com", category="news")],
        next_crawl_after=now,
    )
    domain = (
        await search_container.crawl_domain_repository.list_page(
            crawl_profile_id=crawl_profile_id,
            status=None,
            limit=1,
            offset=0,
        )
    ).items[0]

    response = await frontend_client_system.post(
        f"/frontend/api/crawl-report/domains/{domain.crawl_domain_id}/run",
        params={"crawl_profile_id": crawl_profile_id},
        json={},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["crawl_domain_id"] == domain.crawl_domain_id
    assert payload["status"] == "queued"
