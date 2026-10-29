"""Квота публичного поиска для анонимов и bypass для залогиненных."""

from __future__ import annotations

import hashlib

import pytest
import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient

from apps.frontend.api.public_session_security import (
    PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT,
    PUBLIC_SEARCH_QUOTA_EXHAUSTED_DETAIL,
    PUBLIC_SEARCH_RESEARCH_QUOTA_COST,
)
from core.search import PUBLIC_SEARCH_SESSION_ISSUER
from core.utils.tokens import TokenType, get_token_service

# Квота считается по client host (request.client.host). Для параллельной изоляции
# каждый тест получает уникальный client IP через ASGITransport(client=...):
# redis-ключ квоты становится тестовым, воркеры xdist не делят счётчик.


def _unique_client_ip(unique_id: str) -> str:
    digest = hashlib.sha256(unique_id.encode("utf-8")).digest()
    return f"10.{digest[0]}.{digest[1]}.{digest[2]}"


def _public_search_session_headers() -> dict[str, str]:
    return {
        "origin": "http://testserver",
        "referer": "http://testserver/search",
    }


def _public_search_session_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "mode": "quick",
        "origin": "http://testserver",
        "expires_in_seconds": 300,
        "consume_search_quota": True,
    }
    body.update(overrides)
    return body


@pytest_asyncio.fixture
async def public_search_client(frontend_app, unique_id):
    """Анонимный клиент с уникальным client IP — свой redis-ключ квоты."""
    transport = ASGITransport(app=frontend_app, client=(_unique_client_ip(unique_id), 12345))
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=True,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def public_search_client_with_auth(frontend_app, unique_id, auth_token):
    """Залогиненный клиент с уникальным client IP."""
    transport = ASGITransport(app=frontend_app, client=(_unique_client_ip(unique_id), 12345))
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"auth_token": auth_token},
        follow_redirects=True,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_anonymous_search_quota_allows_twenty_then_rejects(
    public_search_client: AsyncClient,
):
    headers = _public_search_session_headers()
    for index in range(PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT):
        response = await public_search_client.post(
            "/frontend/api/public/search/session",
            headers=headers,
            json=_public_search_session_body(),
        )
        assert response.status_code == 200, f"request {index + 1}: {response.text}"

    exhausted = await public_search_client.post(
        "/frontend/api/public/search/session",
        headers=headers,
        json=_public_search_session_body(),
    )
    assert exhausted.status_code == 429
    assert exhausted.json()["detail"] == PUBLIC_SEARCH_QUOTA_EXHAUSTED_DETAIL


@pytest.mark.asyncio
async def test_auxiliary_session_does_not_consume_search_quota(
    public_search_client: AsyncClient,
):
    headers = _public_search_session_headers()
    for _ in range(PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT):
        response = await public_search_client.post(
            "/frontend/api/public/search/session",
            headers=headers,
            json=_public_search_session_body(),
        )
        assert response.status_code == 200, response.text

    auxiliary = await public_search_client.post(
        "/frontend/api/public/search/session",
        headers=headers,
        json=_public_search_session_body(consume_search_quota=False),
    )
    assert auxiliary.status_code == 200, auxiliary.text

    exhausted = await public_search_client.post(
        "/frontend/api/public/search/session",
        headers=headers,
        json=_public_search_session_body(),
    )
    assert exhausted.status_code == 429
    assert exhausted.json()["detail"] == PUBLIC_SEARCH_QUOTA_EXHAUSTED_DETAIL


@pytest.mark.asyncio
async def test_platform_session_user_bypasses_search_quota(
    public_search_client_with_auth: AsyncClient,
):
    headers = _public_search_session_headers()
    for index in range(PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT + 5):
        response = await public_search_client_with_auth.post(
            "/frontend/api/public/search/session",
            headers=headers,
            json=_public_search_session_body(),
        )
        assert response.status_code == 200, f"request {index + 1}: {response.text}"
        token_data = get_token_service().validate_token(response.json()["token"])
        assert token_data is not None
        assert token_data.token_type == TokenType.EMBED_SESSION
        assert not token_data.user_id.startswith("search_guest_")
        assert token_data.metadata["issued_by"] == PUBLIC_SEARCH_SESSION_ISSUER


@pytest.mark.asyncio
async def test_serp_more_accepts_platform_session_user(
    public_search_client_with_auth: AsyncClient,
):
    response = await public_search_client_with_auth.post(
        "/frontend/api/public/search/serp/more",
        headers=_public_search_session_headers(),
        json={
            "serp_cache_key": "00000000000000000000000000000000",
            "offset": 10,
            "limit": 10,
        },
    )
    if response.status_code == 403:
        assert response.json()["detail"] != "Недопустимый тип сессии для SERP"


def _serp_click_body() -> dict[str, object]:
    return {
        "query": "тестовый запрос",
        "mode": "quick",
        "url": "https://example.ru/articles/tech",
        "position": 2,
        "provider": "index",
        "search_index_id": "",
        "serp_cache_key": "",
    }


@pytest.mark.asyncio
async def test_anonymous_research_session_costs_five_quota_units(
    public_search_client: AsyncClient,
):
    headers = _public_search_session_headers()
    max_research_runs = PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT // PUBLIC_SEARCH_RESEARCH_QUOTA_COST
    for index in range(max_research_runs):
        response = await public_search_client.post(
            "/frontend/api/public/search/session",
            headers=headers,
            json=_public_search_session_body(mode="research"),
        )
        assert response.status_code == 200, f"request {index + 1}: {response.text}"

    exhausted = await public_search_client.post(
        "/frontend/api/public/search/session",
        headers=headers,
        json=_public_search_session_body(mode="research"),
    )
    assert exhausted.status_code == 429
    assert exhausted.json()["detail"] == PUBLIC_SEARCH_QUOTA_EXHAUSTED_DETAIL


@pytest.mark.asyncio
async def test_anonymous_quick_session_still_costs_one_quota_unit(
    public_search_client: AsyncClient,
):
    headers = _public_search_session_headers()
    for index in range(PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT):
        response = await public_search_client.post(
            "/frontend/api/public/search/session",
            headers=headers,
            json=_public_search_session_body(mode="quick"),
        )
        assert response.status_code == 200, f"request {index + 1}: {response.text}"

    exhausted = await public_search_client.post(
        "/frontend/api/public/search/session",
        headers=headers,
        json=_public_search_session_body(mode="quick"),
    )
    assert exhausted.status_code == 429
    assert exhausted.json()["detail"] == PUBLIC_SEARCH_QUOTA_EXHAUSTED_DETAIL


@pytest.mark.asyncio
async def test_serp_click_rejects_anonymous_without_session(
    public_search_client: AsyncClient,
):
    response = await public_search_client.post(
        "/frontend/api/public/search/serp/click",
        headers=_public_search_session_headers(),
        json=_serp_click_body(),
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_serp_click_accepts_platform_session_user(
    public_search_client_with_auth: AsyncClient,
):
    response = await public_search_client_with_auth.post(
        "/frontend/api/public/search/serp/click",
        headers=_public_search_session_headers(),
        json=_serp_click_body(),
    )
    if response.status_code == 403:
        assert response.json()["detail"] != "Недопустимый тип сессии для SERP"
