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
async def test_platform_brand_lvh_me_dev_host(frontend_client) -> None:
    response = await frontend_client.get(
        "/frontend/api/platform/brand",
        headers={"Host": "system.lvh.me:9004"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["base_domain"] == "lvh.me"
    assert payload["platform_name"] == "Linnex"
    assert payload["agent_product_name"] == "LinnexAgent"
    assert payload["apex_origin"] == "http://system.lvh.me:9004/"


@pytest.mark.asyncio
async def test_platform_brand_localhost_dev_host(frontend_client) -> None:
    response = await frontend_client.get(
        "/frontend/api/platform/brand",
        headers={"Host": "localhost:9004"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["base_domain"] == "localhost"
    assert payload["agent_product_name"] == "LinnexAgent"
    assert payload["apex_origin"] == "http://localhost:9004/"


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


@pytest.mark.parametrize(
    "host,product_names",
    [
        (
            "humanitec.ru",
            {
                "agent_product_name": "HumanitecAgent",
                "models_product_name": "Humanitec Models",
                "voice_product_name": "Humanitec Voice",
                "llms_display_label": "Humanitec LLMs",
                "flows_product_label": "Humanitec Flows",
            },
        ),
        (
            "linnex.io",
            {
                "agent_product_name": "LinnexAgent",
                "models_product_name": "Linnex Models",
                "voice_product_name": "Linnex Voice",
                "llms_display_label": "Linnex LLMs",
                "flows_product_label": "Linnex Flows",
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_platform_brand_product_names(
    frontend_client,
    host: str,
    product_names: dict[str, str],
) -> None:
    response = await frontend_client.get(
        "/frontend/api/platform/brand",
        headers={"Host": host},
    )
    assert response.status_code == 200
    payload = response.json()
    for key, expected in product_names.items():
        assert payload[key] == expected


@pytest.mark.parametrize(
    "host,platform_name,agent_product_name",
    [
        ("humanitec.ru", "Humanitec", "HumanitecAgent"),
        ("linnex.io", "Linnex", "LinnexAgent"),
    ],
)
@pytest.mark.asyncio
async def test_llms_txt_host_aware(
    frontend_client,
    host: str,
    platform_name: str,
    agent_product_name: str,
) -> None:
    response = await frontend_client.get(
        "/llms.txt",
        headers={"Host": host},
    )
    assert response.status_code == 200
    body = response.text
    assert body.startswith(f"# {platform_name}\n")
    assert f"{agent_product_name} Download:" in body


@pytest.mark.parametrize(
    "host,platform_name",
    [
        ("humanitec.ru", "Humanitec"),
        ("linnex.io", "Linnex"),
    ],
)
@pytest.mark.asyncio
async def test_pwa_sw_and_offline_host_aware(
    frontend_client,
    host: str,
    platform_name: str,
) -> None:
    sw_response = await frontend_client.get(
        "/sw.js",
        headers={"Host": host},
    )
    assert sw_response.status_code == 200
    assert platform_name.encode() in sw_response.content
    assert b"__PLATFORM_NAME__" not in sw_response.content

    offline_response = await frontend_client.get(
        "/offline.html",
        headers={"Host": host},
    )
    assert offline_response.status_code == 200
    assert f"Нет подключения - {platform_name}" in offline_response.text
