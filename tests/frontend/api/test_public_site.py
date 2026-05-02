"""HTTP-тесты публичного site-bundle, блога и карточки для каталогов."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_public_site_bundle_contains_legal_and_marketing(frontend_client) -> None:
    """GET site-bundle отдаёт legal и marketing из конфигурации."""
    response = await frontend_client.get("/frontend/api/public/site-bundle")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["legal"], dict)
    assert payload["legal"]["company_name_ru"]
    assert isinstance(payload["marketing"], dict)
    assert "telegram_community_url" in payload["marketing"]
    assert "yandex_metrika_id" in payload["marketing"]
    assert "google_analytics_measurement_id" in payload["marketing"]


@pytest.mark.asyncio
async def test_public_blog_list_returns_items(frontend_client) -> None:
    """Список материалов блога — непустой items[]."""
    response = await frontend_client.get("/frontend/api/public/blog")
    assert response.status_code == 200
    body = response.json()
    items = body["items"]
    assert isinstance(items, list)
    assert len(items) >= 2
    first = items[0]
    assert isinstance(first["slug"], str)
    assert first["slug"]
    assert isinstance(first["title_ru"], str)


@pytest.mark.asyncio
async def test_public_blog_post_found_and_missing(frontend_client) -> None:
    """Пост по slug и 404 для неизвестного slug."""
    ok = await frontend_client.get(
        "/frontend/api/public/blog/post",
        params={"slug": "ai-agent-support-rag"},
    )
    assert ok.status_code == 200
    data = ok.json()
    assert data["slug"] == "ai-agent-support-rag"
    assert "body_ru" in data

    missing = await frontend_client.get(
        "/frontend/api/public/blog/post",
        params={"slug": "no-such-post-slug-xyz"},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_public_startup_card_contract(frontend_client) -> None:
    """Карточка продукта для внешних каталогов имеет ожидаемые поля."""
    response = await frontend_client.get("/frontend/api/public/startup-card")
    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "Humanitec"
    assert isinstance(card["tagline_ru"], str)
    assert isinstance(card["products"], list)
    assert len(card["products"]) == 5
    assert isinstance(card["deployment_modes"], list)


@pytest.mark.asyncio
async def test_sitemap_contains_image_namespace_and_preview_urls(frontend_client) -> None:
    """Sitemap использует image extension и содержит превью для ключевых страниц."""
    response = await frontend_client.get("/sitemap.xml")
    assert response.status_code == 200
    text = response.text
    assert 'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"' in text
    assert "<image:loc>" in text
    assert "/static/frontend/assets/images/main_img.png" in text
