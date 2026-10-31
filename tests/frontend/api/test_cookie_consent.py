"""Публичный журнал согласия на cookie."""

from __future__ import annotations

import re

import pytest
from httpx2 import AsyncClient

from apps.frontend.cookie_consent import COOKIE_CONSENT_TEXT_VERSION
from core.middleware.auth.route_config import RouteMatcher


def _body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision": "necessary_only",
        "analytics_allowed": False,
        "consent_text_version": COOKIE_CONSENT_TEXT_VERSION,
        "locale": "ru",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_record_cookie_consent_necessary_only(frontend_client: AsyncClient) -> None:
    response = await frontend_client.post(
        "/frontend/api/public/cookie-consent",
        json=_body(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "necessary_only"
    assert payload["analytics_allowed"] is False
    assert payload["consent_text_version"] == COOKIE_CONSENT_TEXT_VERSION
    assert payload["locale"] == "ru"
    assert isinstance(payload["cookie_consent_id"], str)
    assert payload["cookie_consent_id"]
    assert payload["brand_host"] == "linnex.io"
    assert payload["apex_domain"] == "linnex.io"
    assert isinstance(payload["request_id"], str)
    assert payload["request_id"]
    assert re.fullmatch(r"[0-9a-f]{64}", payload["ip_hash"])
    assert payload["ip_hash"] != "127.0.0.1"
    assert payload["supersedes_cookie_consent_id"] is None


@pytest.mark.asyncio
async def test_record_cookie_consent_unprefixed_mirror(frontend_client: AsyncClient) -> None:
    response = await frontend_client.post(
        "/api/public/cookie-consent",
        json=_body(locale="en"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["locale"] == "en"
    assert payload["decision"] == "necessary_only"


@pytest.mark.asyncio
async def test_record_cookie_consent_custom_and_supersedes(frontend_client: AsyncClient) -> None:
    first = await frontend_client.post(
        "/frontend/api/public/cookie-consent",
        json=_body(),
    )
    assert first.status_code == 200
    first_id = first.json()["cookie_consent_id"]

    second = await frontend_client.post(
        "/frontend/api/public/cookie-consent",
        json=_body(
            decision="custom",
            analytics_allowed=False,
            supersedes_cookie_consent_id=first_id,
        ),
    )
    assert second.status_code == 200
    payload = second.json()
    assert payload["decision"] == "custom"
    assert payload["supersedes_cookie_consent_id"] == first_id
    assert payload["cookie_consent_id"] != first_id


@pytest.mark.asyncio
async def test_record_cookie_consent_stale_version_conflict(frontend_client: AsyncClient) -> None:
    response = await frontend_client.post(
        "/frontend/api/public/cookie-consent",
        json=_body(consent_text_version="1999-01-01.0"),
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_record_cookie_consent_accept_all_requires_configured_analytics(
    frontend_client: AsyncClient,
) -> None:
    bundle = await frontend_client.get("/frontend/api/public/site-bundle")
    assert bundle.status_code == 200
    configured = bundle.json()["analytics_configured"]
    response = await frontend_client.post(
        "/frontend/api/public/cookie-consent",
        json=_body(decision="accept_all", analytics_allowed=True),
    )
    if configured:
        assert response.status_code == 200
        assert response.json()["decision"] == "accept_all"
        assert response.json()["analytics_allowed"] is True
        return
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_record_cookie_consent_necessary_only_rejects_analytics(
    frontend_client: AsyncClient,
) -> None:
    response = await frontend_client.post(
        "/frontend/api/public/cookie-consent",
        json=_body(analytics_allowed=True),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_record_cookie_consent_invalid_locale(frontend_client: AsyncClient) -> None:
    response = await frontend_client.post(
        "/frontend/api/public/cookie-consent",
        json=_body(locale="de"),
    )
    assert response.status_code == 422


def test_route_matcher_marks_cookie_consent_api_anonymous() -> None:
    matcher = RouteMatcher()
    for path in (
        "/cookies",
        "/consent/cookies",
        "/api/public/cookie-consent",
        "/frontend/api/public/cookie-consent",
    ):
        rule = matcher.match(path)
        assert rule is not None, f"No route rule for {path}"
        assert rule.context_type == "anonymous"
        assert rule.auth_required is False
