"""HTTP-тесты публичного site-bundle, блога и карточки для каталогов."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx2 import AsyncClient

from apps.frontend.config import get_frontend_settings
from apps.frontend.seo.pages import PUBLIC_PRODUCT_KEYS
from core.types import parse_json_object


@pytest.mark.asyncio
async def test_public_site_bundle_contains_legal_and_marketing(frontend_client: AsyncClient) -> None:
    """GET site-bundle отдаёт legal и marketing из конфигурации."""
    response = await frontend_client.get("/frontend/api/public/site-bundle")
    assert response.status_code == 200
    payload = parse_json_object(response.text)
    assert isinstance(payload["legal"], dict)
    assert payload["legal"]["company_name_ru"]
    assert isinstance(payload["marketing"], dict)
    assert "telegram_community_url" in payload["marketing"]
    assert "yandex_metrika_id" in payload["marketing"]
    assert "google_analytics_measurement_id" in payload["marketing"]
    assert isinstance(payload["cookie_consent_text_version"], str)
    assert payload["cookie_consent_text_version"]
    assert isinstance(payload["analytics_configured"], bool)


@pytest.mark.asyncio
async def test_public_blog_list_returns_items(frontend_client: AsyncClient) -> None:
    """Список материалов блога — непустой items[]."""
    response = await frontend_client.get("/frontend/api/public/blog")
    assert response.status_code == 200
    body = parse_json_object(response.text)
    items = body["items"]
    assert isinstance(items, list)
    assert len(items) >= 2
    first = items[0]
    assert isinstance(first, dict)
    assert isinstance(first["slug"], str)
    assert first["slug"]
    assert isinstance(first["title_ru"], str)


@pytest.mark.asyncio
async def test_public_blog_post_found_and_missing(frontend_client: AsyncClient) -> None:
    """Пост по slug и 404 для неизвестного slug."""
    ok = await frontend_client.get(
        "/frontend/api/public/blog/post",
        params={"slug": "ai-agent-support-rag"},
    )
    assert ok.status_code == 200
    data = parse_json_object(ok.text)
    assert data["slug"] == "ai-agent-support-rag"
    assert "body_ru" in data

    missing = await frontend_client.get(
        "/frontend/api/public/blog/post",
        params={"slug": "no-such-post-slug-xyz"},
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_public_blog_post_linnex_brand_in_body(frontend_client: AsyncClient) -> None:
    """Текст блога подставляет platform_name для linnex.io."""
    response = await frontend_client.get(
        "/frontend/api/public/blog/post",
        params={"slug": "ai-agent-support-rag"},
        headers={"Host": "linnex.io"},
    )
    assert response.status_code == 200
    data = parse_json_object(response.text)
    body_en = data["body_en"]
    assert isinstance(body_en, str)
    assert "Linnex" in body_en
    assert "Humanitec" not in body_en


@pytest.mark.asyncio
async def test_public_startup_card_contract(frontend_client: AsyncClient) -> None:
    """Карточка продукта для внешних каталогов имеет ожидаемые поля."""
    response = await frontend_client.get("/frontend/api/public/startup-card")
    assert response.status_code == 200
    card = parse_json_object(response.text)
    assert card["name"] == "Linnex"
    assert isinstance(card["tagline_ru"], str)
    assert isinstance(card["products"], list)
    # Список продуктов деривится из реестра PUBLIC_PAGES (kind=product).
    assert len(card["products"]) == len(PUBLIC_PRODUCT_KEYS)
    assert all(isinstance(name, str) and name for name in card["products"])
    assert isinstance(card["deployment_modes"], list)


@pytest.mark.asyncio
async def test_sitemap_index_links_all_maps(frontend_client: AsyncClient) -> None:
    """Корневой /sitemap.xml — sitemapindex со ссылками на маркетинг, блог и docs."""
    response = await frontend_client.get("/sitemap.xml")
    assert response.status_code == 200
    text = response.text
    assert "<sitemapindex" in text
    for loc in (
        "/sitemap-marketing.xml",
        "/sitemap-blog.xml",
        "/documentation/sitemap.xml",
        "/documentation/en/sitemap.xml",
    ):
        assert loc in text


@pytest.mark.asyncio
async def test_sitemap_marketing_contains_image_namespace_and_preview_urls(frontend_client: AsyncClient) -> None:
    """Маркетинговая sitemap: image extension, hreflang и полный список публичных путей."""
    response = await frontend_client.get("/sitemap-marketing.xml")
    assert response.status_code == 200
    text = response.text
    assert 'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"' in text
    assert 'xmlns:xhtml="http://www.w3.org/1999/xhtml"' in text
    assert "<image:loc>" in text
    assert "/static/frontend/assets/images/main_img.png" in text
    for path in (
        "/cookies",
        "/consent/cookies",
        "/products/geo",
        "/products/wiki",
        "/products/shop",
        "/policy",
        "/terms",
    ):
        assert path in text
    assert 'hreflang="ru"' in text
    assert 'hreflang="en"' in text
    assert 'hreflang="x-default"' in text
    assert "/en/products/agents" in text


@pytest.mark.asyncio
async def test_robots_txt_allows_ai_crawlers_and_disallows_private(frontend_client: AsyncClient) -> None:
    """robots.txt: AI-ботам разрешена индексация, приватные маршруты закрыты."""
    response = await frontend_client.get("/robots.txt")
    assert response.status_code == 200
    text = response.text
    for agent in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "Applebot-Extended"):
        assert f"User-agent: {agent}" in text
    for disallowed in ("/settings", "/dashboard", "/login", "/billing", "/l/", "/documents/"):
        assert f"Disallow: {disallowed}" in text
    assert "Sitemap:" in text
    assert "/sitemap.xml" in text


@pytest.mark.asyncio
async def test_llms_txt_links_documentation_llms(frontend_client: AsyncClient) -> None:
    """Корневой llms.txt ссылается на llms.txt и llms-full.txt документации."""
    response = await frontend_client.get("/llms.txt")
    assert response.status_code == 200
    text = response.text
    assert "/documentation/llms.txt" in text
    assert "/documentation/llms-full.txt" in text
    assert "/documentation/en/llms.txt" in text


@pytest.mark.asyncio
async def test_spa_private_route_served_with_noindex_header(frontend_client: AsyncClient) -> None:
    """Неиндексируемый анонимный маршрут (login) отдаётся с X-Robots-Tag: noindex."""
    response = await frontend_client.get("/login", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "noindex" in (response.headers.get("x-robots-tag") or "")


@pytest.mark.asyncio
async def test_sitemap_blog_survives_malformed_index(
    frontend_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Битый blog index.json → пустая urlset (200), не 500; событие blog_index_invalid."""
    blog_dir = tmp_path / "blog"
    blog_dir.mkdir()
    _ = (blog_dir / "index.json").write_text("not json at all", encoding="utf-8")
    monkeypatch.setattr(get_frontend_settings(), "seo_dist_dir", tmp_path)
    response = await frontend_client.get("/sitemap-blog.xml")
    assert response.status_code == 200
    assert "<urlset" in response.text
    assert "<url>" not in response.text


@pytest.mark.asyncio
async def test_public_blog_api_survives_malformed_index(
    frontend_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Битый index.json → пустой список (200), не 500: один битый артефакт
    не роняет публичный блог-API."""
    blog_dir = tmp_path / "blog"
    blog_dir.mkdir()
    _ = (blog_dir / "index.json").write_text("not json at all", encoding="utf-8")
    monkeypatch.setattr(get_frontend_settings(), "seo_dist_dir", tmp_path)
    response = await frontend_client.get("/frontend/api/public/blog")
    assert response.status_code == 200
    assert parse_json_object(response.text)["items"] == []


@pytest.mark.asyncio
async def test_blog_slug_traversal_falls_back_to_noindex_spa(frontend_client: AsyncClient) -> None:
    """Slug с точками/слэшами/верхним регистром не попадает в Path-join: SPA noindex."""
    for path in ("/blog/x..y", "/blog/A-B", "/blog/slug.html"):
        response = await frontend_client.get(path)
        assert response.status_code == 200, path
        assert "<frontend-app" in response.text, path
        assert "noindex" in (response.headers.get("x-robots-tag") or ""), path
