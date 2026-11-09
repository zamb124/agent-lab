"""Юнит-тесты SEO-пакета: реестр страниц, sitemap, postprocess, JSON-LD, llms."""

from __future__ import annotations

import re

from apps.frontend.seo.ld_json import build_ld_graph, render_ld_script
from apps.frontend.seo.llms import build_llms_txt
from apps.frontend.seo.meta import render_index_html
from apps.frontend.seo.pages import (
    PUBLIC_PAGES,
    localized_marketing_path,
    public_page_for_path,
)
from apps.frontend.seo.postprocess import postprocess_snapshot
from apps.frontend.seo.robots import build_robots_txt
from apps.frontend.seo.sitemap import (
    build_blog_sitemap_xml,
    build_marketing_sitemap_xml,
    build_sitemap_index_xml,
)
from core.platform_brand.resolver import resolve_brand_or_primary, resolve_seo_base_url
from core.types import JsonObject, parse_json_object

SEO_BASE = resolve_seo_base_url()
BRAND = resolve_brand_or_primary(None)


def test_public_pages_registry_is_sane() -> None:
    paths = [page.path for page in PUBLIC_PAGES]
    assert len(paths) == len(set(paths)), "дубликаты путей в PUBLIC_PAGES"
    assert "" in paths, "нет корневого лендинга"
    for path in paths:
        assert path == path.strip("/"), f"лишние слэши в '{path}'"
        assert not path.startswith("en"), "en-локаль не хранится в path"


def test_public_page_for_path() -> None:
    assert public_page_for_path("") is not None
    assert public_page_for_path("/products/rag/") is not None
    assert public_page_for_path("dashboard") is None
    assert public_page_for_path("login") is None


def test_localized_marketing_path() -> None:
    assert localized_marketing_path("products/rag", "ru") == "products/rag"
    assert localized_marketing_path("products/rag", "en") == "en/products/rag"
    assert localized_marketing_path("", "en") == "en"
    assert localized_marketing_path("", "ru") == ""


def test_sitemap_index_lists_children() -> None:
    xml = build_sitemap_index_xml(SEO_BASE, [("/a.xml", "2026-01-01"), ("/b.xml", None)])
    assert xml.startswith('<?xml version="1.0"')
    assert "<sitemapindex" in xml
    assert f"{SEO_BASE}/a.xml" in xml and f"{SEO_BASE}/b.xml" in xml
    assert xml.count("<lastmod>") == 1


def test_marketing_sitemap_has_hreflang_and_images() -> None:
    xml = build_marketing_sitemap_xml(SEO_BASE, lastmod="2026-01-01")
    assert f"{SEO_BASE}/products/agents" in xml
    assert f"{SEO_BASE}/en/products/agents" in xml
    assert 'hreflang="x-default"' in xml
    assert "image:image" in xml
    for page in PUBLIC_PAGES:
        assert f"/{page.path}" in xml or page.path == "", f"нет {page.path}"


def test_blog_sitemap_entries() -> None:
    xml = build_blog_sitemap_xml(
        SEO_BASE,
        [
            ("blog/post-a", "en/blog/post-a", "2026-01-10"),
            ("blog/post-b", None, "2026-01-11"),
        ],
    )
    assert f"{SEO_BASE}/blog/post-a" in xml
    assert f"{SEO_BASE}/en/blog/post-a" in xml
    # hreflang-пары RU↔EN и x-default у поста с английской версией.
    assert 'hreflang="x-default"' in xml
    assert f'hreflang="en" href="{SEO_BASE}/en/blog/post-a"' in xml
    # Пост без EN — единственный URL, без alternate-ссылок на несуществующую локаль.
    assert f"{SEO_BASE}/en/blog/post-b" not in xml
    assert xml.count(f'href="{SEO_BASE}/blog/post-b"') == 1


def test_robots_txt_structure() -> None:
    body = build_robots_txt(SEO_BASE)
    assert "User-agent: *" in body
    assert "Allow: /" in body
    assert "Disallow: /api/" in body
    assert "Disallow: /login" in body
    assert "Disallow: /en/login" in body
    assert "Disallow: /en/dashboard" in body
    assert "GPTBot" in body and "ClaudeBot" in body and "PerplexityBot" in body
    assert body.rstrip().endswith(f"Sitemap: {SEO_BASE}/sitemap.xml")


def test_llms_txt_points_to_docs() -> None:
    body = build_llms_txt(SEO_BASE, BRAND)
    assert "documentation/llms.txt" in body
    assert "documentation/llms-full.txt" in body
    assert "## Docs" in body and "## Pages" in body


_SNAPSHOT_HTML = """<!DOCTYPE html>
<html lang="ru"><head>
<title>x</title>
<meta name="description" content="d">
<meta name="robots" content="index">
<link rel="canonical" href="https://linnex.io/products/rag">
<meta property="og:locale" content="ru_RU">
<meta property="og:url" content="https://linnex.io/products/rag">
<meta property="og:image" content="https://linnex.io/static/frontend/assets/images/main_img.png">
<meta name="twitter:image" content="https://linnex.io/static/frontend/assets/images/main_img.png">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite"}</script>
</head><body><landing-footer></landing-footer></body></html>"""


def test_postprocess_snapshot_rewrites_head() -> None:
    page = public_page_for_path("products/rag")
    assert page is not None
    html = postprocess_snapshot(
        _SNAPSHOT_HTML,
        page=page,
        locale="ru",
        brand=BRAND,
        seo_base_url=SEO_BASE,
    )
    assert f'<link rel="canonical" href="{SEO_BASE}/products/rag">' in html
    assert f'content="{SEO_BASE}/products/rag"' in html
    assert 'hreflang="en"' in html and 'hreflang="x-default"' in html
    assert 'id="seo-ld-json"' in html
    assert html.count("application/ld+json") == 1
    # продуктовая страница: title/description выставляются из frontend_products
    # бандла, даже если снапшот захватил raw i18n-ключ до загрузки переводов
    assert "<title>Knowledge Base — семантический поиск по документам | Linnex</title>" in html
    assert 'og:title" content="Knowledge Base — семантический поиск по документам | Linnex"' in html
    assert "meta_title" not in html


def test_postprocess_snapshot_en_rewrites_links() -> None:
    page = public_page_for_path("")
    assert page is not None
    html = postprocess_snapshot(
        _SNAPSHOT_HTML.replace('href="/products/rag"', 'href="/products/rag"'),
        page=page,
        locale="en",
        brand=BRAND,
        seo_base_url=SEO_BASE,
    )
    assert f'{SEO_BASE}/en"' in html or f"{SEO_BASE}/en<" in html or "en_US" in html
    assert '<html lang="en"' in html
    assert 'hreflang="en"' in html


_SNAPSHOT_LINKS_HTML = """<!DOCTYPE html>
<html lang="ru"><head>
<link rel="canonical" href="https://linnex.io/products/rag">
<meta name="robots" content="index">
</head><body>
<a href="/products/rag">p</a><a href="/blog/post-a">b</a>
<a href="/search?q=x">s</a><a href="/">h</a>
<a href="https://linnex.io/about">abs</a>
</body></html>"""


def test_postprocess_en_href_rewrite_covers_subpaths_and_queries() -> None:
    """en-снапшот: все публичные href получают /en-префикс — включая подпути
    (/blog/<slug>), ?query и canonical-абсолютные URL."""
    page = public_page_for_path("products/rag")
    assert page is not None
    html = postprocess_snapshot(
        _SNAPSHOT_LINKS_HTML,
        page=page,
        locale="en",
        brand=BRAND,
        seo_base_url=SEO_BASE,
    )
    assert 'href="/en/products/rag"' in html
    assert 'href="/en/blog/post-a"' in html
    assert 'href="/en/search?q=x"' in html
    assert f"{SEO_BASE}/en/about" in html


def _graph_types(graph: JsonObject) -> set[str]:
    nodes = graph["@graph"]
    assert isinstance(nodes, list)
    return {str(node["@type"]) for node in nodes if isinstance(node, dict)}


def test_ld_graph_shapes() -> None:
    landing = public_page_for_path("")
    assert landing is not None
    graph = build_ld_graph(landing, brand=BRAND, seo_base_url=SEO_BASE, locale="ru")
    assert graph is not None
    types = _graph_types(graph)
    assert "WebSite" in types and "Organization" in types and "FAQPage" in types
    product = public_page_for_path("products/agents")
    assert product is not None
    script = render_ld_script(product, brand=BRAND, seo_base_url=SEO_BASE, locale="en")
    assert 'id="seo-ld-json"' in script
    match = re.search(r">(.*)</script>", script)
    assert match is not None
    payload = parse_json_object(match.group(1))
    types = _graph_types(payload)
    assert "SoftwareApplication" in types and "BreadcrumbList" in types


def test_build_blog_sitemap_empty_ok() -> None:
    assert "<urlset" in build_blog_sitemap_xml(SEO_BASE, [])


_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ru"><head>
<title>t</title>
<meta name="description" content="d">
<meta name="robots" content="index">
<link rel="canonical" href="https://example.invalid/">
<meta property="og:url" content="https://example.invalid/">
</head><body></body></html>"""


def test_render_index_html_canonical_per_path() -> None:
    """Регрессия: каждая публичная страница канонизируется на свой путь, не на корень."""
    html = render_index_html(
        _INDEX_TEMPLATE,
        brand=BRAND,
        seo_base_url=SEO_BASE,
        locale="ru",
        indexable=True,
        path="products/rag",
    )
    assert f'<link rel="canonical" href="{SEO_BASE}/products/rag"' in html
    assert f'hreflang="en" href="{SEO_BASE}/en/products/rag"' in html
    assert f'hreflang="x-default" href="{SEO_BASE}/products/rag"' in html


def test_render_index_html_en_and_noindex() -> None:
    en = render_index_html(
        _INDEX_TEMPLATE,
        brand=BRAND,
        seo_base_url=SEO_BASE,
        locale="en",
        indexable=True,
        path="products/rag",
    )
    assert f'<link rel="canonical" href="{SEO_BASE}/en/products/rag"' in en
    private = render_index_html(
        _INDEX_TEMPLATE,
        brand=BRAND,
        seo_base_url=SEO_BASE,
        locale="ru",
        indexable=False,
        path="",
    )
    assert 'content="noindex,nofollow"' in private
    assert "hreflang" not in private
