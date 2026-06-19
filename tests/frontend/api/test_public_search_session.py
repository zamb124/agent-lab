"""Квота публичного поиска для анонимов и bypass для залогиненных."""

from __future__ import annotations

import hashlib

import pytest
import pytest_asyncio
from httpx import AsyncClient

from apps.frontend.api.public_session_security import (
    PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT,
    PUBLIC_SEARCH_QUOTA_EXHAUSTED_DETAIL,
    PUBLIC_SEARCH_QUOTA_REDIS_PREFIX,
)
from core.search import PUBLIC_SEARCH_SESSION_ISSUER
from core.utils.tokens import TokenType, get_token_service

_TEST_CLIENT_HOST = "127.0.0.1"


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


def _public_search_quota_redis_key(client_host: str = _TEST_CLIENT_HOST) -> str:
    scope_key = hashlib.sha256("public_search".encode("utf-8")).hexdigest()[:32]
    client_key = hashlib.sha256(client_host.encode("utf-8")).hexdigest()[:32]
    return f"{PUBLIC_SEARCH_QUOTA_REDIS_PREFIX}:{scope_key}:{client_key}"


@pytest_asyncio.fixture
async def clean_public_search_quota(frontend_container):
    quota_key = _public_search_quota_redis_key()
    await frontend_container.redis_client.delete(quota_key)
    yield quota_key
    await frontend_container.redis_client.delete(quota_key)


@pytest.mark.asyncio
async def test_anonymous_search_quota_allows_twenty_then_rejects(
    frontend_client: AsyncClient,
    clean_public_search_quota,
):
    _ = clean_public_search_quota
    headers = _public_search_session_headers()
    for index in range(PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT):
        response = await frontend_client.post(
            "/frontend/api/public/search/session",
            headers=headers,
            json=_public_search_session_body(),
        )
        assert response.status_code == 200, f"request {index + 1}: {response.text}"

    exhausted = await frontend_client.post(
        "/frontend/api/public/search/session",
        headers=headers,
        json=_public_search_session_body(),
    )
    assert exhausted.status_code == 429
    assert exhausted.json()["detail"] == PUBLIC_SEARCH_QUOTA_EXHAUSTED_DETAIL


@pytest.mark.asyncio
async def test_auxiliary_session_does_not_consume_search_quota(
    frontend_client: AsyncClient,
    clean_public_search_quota,
):
    _ = clean_public_search_quota
    headers = _public_search_session_headers()
    for _ in range(PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT):
        response = await frontend_client.post(
            "/frontend/api/public/search/session",
            headers=headers,
            json=_public_search_session_body(),
        )
        assert response.status_code == 200, response.text

    auxiliary = await frontend_client.post(
        "/frontend/api/public/search/session",
        headers=headers,
        json=_public_search_session_body(consume_search_quota=False),
    )
    assert auxiliary.status_code == 200, auxiliary.text

    exhausted = await frontend_client.post(
        "/frontend/api/public/search/session",
        headers=headers,
        json=_public_search_session_body(),
    )
    assert exhausted.status_code == 429
    assert exhausted.json()["detail"] == PUBLIC_SEARCH_QUOTA_EXHAUSTED_DETAIL


@pytest.mark.asyncio
async def test_platform_session_user_bypasses_search_quota(
    frontend_client_with_auth: AsyncClient,
    clean_public_search_quota,
):
    _ = clean_public_search_quota
    headers = _public_search_session_headers()
    for index in range(PUBLIC_SEARCH_ANONYMOUS_DAILY_LIMIT + 5):
        response = await frontend_client_with_auth.post(
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
