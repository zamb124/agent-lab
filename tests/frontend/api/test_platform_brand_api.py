"""HTTP-тесты GET /frontend/api/platform/brand (multi-brand bootstrap)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_platform_brand_humanitec(frontend_client) -> None:
    response = await frontend_client.get(
        "/frontend/api/platform/brand",
        headers={"Host": "humanitec.ru"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["base_domain"] == "humanitec.ru"
    assert payload["platform_name"] == "Humanitec"
    assert payload["support_email"] == "helpme@humanitec.ru"
    assert payload["apex_origin"] == "https://humanitec.ru/"
    assert "humanitec.ru" in payload["supported_domains"]
    assert "linnex.io" in payload["supported_domains"]


@pytest.mark.asyncio
async def test_platform_brand_linnex(frontend_client) -> None:
    response = await frontend_client.get(
        "/frontend/api/platform/brand",
        headers={"Host": "linnex.io"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["base_domain"] == "linnex.io"
    assert payload["platform_name"] == "Linnex"
    assert payload["support_email"] == "support@linnex.io"
    assert payload["apex_origin"] == "https://linnex.io/"


@pytest.mark.asyncio
async def test_platform_brand_unknown_host_rejected(frontend_client) -> None:
    response = await frontend_client.get(
        "/frontend/api/platform/brand",
        headers={"Host": "evil.example.com"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_startup_card_linnex_branding(frontend_client) -> None:
    response = await frontend_client.get(
        "/frontend/api/public/startup-card",
        headers={"Host": "linnex.io"},
    )
    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "Linnex"
    assert card["website_url"] == "https://linnex.io"


@pytest.mark.asyncio
async def test_public_legal_linnex(frontend_client) -> None:
    response = await frontend_client.get(
        "/frontend/api/public/legal",
        headers={"Host": "linnex.io"},
    )
    assert response.status_code == 200
    legal = response.json()
    assert legal["company_name_ru"] == "Linnex"
    assert legal["contact_email"] == "legal@linnex.io"


@pytest.mark.asyncio
async def test_public_site_bundle_linnex(frontend_client) -> None:
    response = await frontend_client.get(
        "/frontend/api/public/site-bundle",
        headers={"Host": "linnex.io"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["legal"]["company_name_ru"] == "Linnex"
    assert payload["marketing"]["telegram_community_url"] is None


@pytest.mark.parametrize("host,short_name", [
    ("humanitec.ru", "Humanitec"),
    ("linnex.io", "Linnex"),
])
@pytest.mark.asyncio
async def test_pwa_manifest_host_aware(
    frontend_client,
    host: str,
    short_name: str,
) -> None:
    response = await frontend_client.get(
        "/manifest.json",
        headers={"Host": host},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["short_name"] == short_name
    assert short_name in payload["name"]
