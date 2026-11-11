"""Юнит-тесты ``apps.frontend.seo.analytics``: поверхность, UA, referer, visitor-id."""

from __future__ import annotations

from apps.frontend.seo.analytics import (
    classify_ua,
    locale_of,
    referer_host,
    surface_of,
    visitor_id,
)


def test_surface_marketing_pages() -> None:
    assert surface_of("/") == "page"
    assert surface_of("/products/rag") == "page"
    assert surface_of("/en") == "page"
    assert surface_of("/en/products/rag") == "page"
    assert surface_of("roadmap/") == "page"


def test_surface_docs_blog_llms() -> None:
    assert surface_of("/documentation/") == "docs"
    assert surface_of("/en/documentation/guide/") == "docs"
    assert surface_of("/documentation/scenarios/shop/index.md") == "docs-md"
    assert surface_of("/documentation/llms-full.txt") == "docs-md"
    assert surface_of("/blog/") == "blog"
    assert surface_of("/en/blog/post-slug") == "blog"
    assert surface_of("/llms.txt") == "llms"


def test_surface_root_seo_files() -> None:
    assert surface_of("/robots.txt") == "robots"
    assert surface_of("/sitemap.xml") == "sitemap"
    assert surface_of("/sitemap-marketing.xml") == "sitemap"
    assert surface_of("/favicon.ico") == "favicon"
    assert surface_of("/80e9e4de58b5378c32cf9dcf011dbba6.txt") == "indexnow"


def test_surface_non_public() -> None:
    assert surface_of("/api/companies") is None
    assert surface_of("/dashboard") is None
    assert surface_of("/frontend/robots.txt") is None
    assert surface_of("/unknown/slug") is None


def test_locale() -> None:
    assert locale_of("/en/products/rag") == "en"
    assert locale_of("/en") == "en"
    assert locale_of("/products/rag") == "ru"


def test_classify_ua_bots() -> None:
    assert classify_ua("Mozilla/5.0 (compatible; YandexBot/3.0)") == ("yandexbot", True)
    assert classify_ua("Mozilla/5.0 (compatible; Googlebot/2.1)") == ("googlebot", True)
    assert classify_ua("Mozilla/5.0 (compatible; bingbot/2.0)") == ("bingbot", True)
    assert classify_ua("GPTBot/1.2 (+https://openai.com/gptbot)") == ("gptbot", True)
    assert classify_ua("OAI-SearchBot/1.0") == ("oai-searchbot", True)
    assert classify_ua("ClaudeBot/1.0") == ("claudebot", True)
    assert classify_ua("PerplexityBot/1.0") == ("perplexitybot", True)


def test_classify_ua_humans_and_internal() -> None:
    assert classify_ua(
        "Mozilla/5.0 (Macintosh) Chrome/121.0 Safari/537.36"
    ) == ("chrome", False)
    family, bot = classify_ua("Mozilla/5.0 (iPhone) Chrome/121.0 Mobile")
    assert family == "chrome-mobile" and not bot
    assert classify_ua("HeadlessChrome/121.0") == ("internal-renderer", False)
    assert classify_ua("seo-smoke/1.0") == ("internal-renderer", False)
    assert classify_ua("python-httpx/0.27") == ("http-client", False)
    assert classify_ua("") == ("unknown", False)


def test_referer_host() -> None:
    assert referer_host(None) == "direct"
    assert referer_host("") == "direct"
    assert referer_host("https://www.google.com/search?q=linnex") == "www.google.com"
    assert referer_host("https://linnex.io/products") == "internal"
    assert referer_host("yandex.ru/search") == "yandex.ru"


def test_visitor_id_privacy_and_stability() -> None:
    vid = visitor_id("1.2.3.4", "agent", "salt")
    assert len(vid) == 16
    assert vid == visitor_id("1.2.3.4", "agent", "salt")
    assert vid != visitor_id("1.2.3.5", "agent", "salt")
    assert vid != visitor_id("1.2.3.4", "agent", "other-salt")
    # Сырой IP в идентификаторе не фигурирует.
    assert "1.2.3.4" not in vid
