"""Сборка sitemap: корневой sitemapindex и urlset маркетинговых страниц с hreflang."""

from __future__ import annotations

from xml.sax.saxutils import escape

from apps.frontend.seo.pages import (
    PUBLIC_PAGES,
    SEO_LOCALES,
    PublicPage,
    SeoLocale,
    localized_marketing_path,
)

_SITEMAP_XMLNS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_XHTML_XMLNS = "http://www.w3.org/1999/xhtml"
_IMAGE_XMLNS = "http://www.google.com/schemas/sitemap-image/1.1"

OG_IMAGE_PATH = "/static/frontend/assets/images/main_img.png"


def _localized_url(base_url: str, path: str, locale: SeoLocale) -> str:
    localized = localized_marketing_path(path, locale)
    return f"{base_url}/{localized}" if localized else f"{base_url}/"


def _hreflang_links(base_url: str, page: PublicPage) -> str:
    ru_url = _localized_url(base_url, page.path, "ru")
    en_url = _localized_url(base_url, page.path, "en")
    lines = [
        f'    <xhtml:link rel="alternate" hreflang="ru" href="{escape(ru_url)}"/>',
        f'    <xhtml:link rel="alternate" hreflang="en" href="{escape(en_url)}"/>',
        f'    <xhtml:link rel="alternate" hreflang="x-default" href="{escape(ru_url)}"/>',
    ]
    return "\n".join(lines)


def _url_block(base_url: str, page: PublicPage, *, locale: SeoLocale, lastmod: str) -> str:
    loc = _localized_url(base_url, page.path, locale)
    lines = [
        "  <url>",
        f"    <loc>{escape(loc)}</loc>",
        _hreflang_links(base_url, page),
        f"    <lastmod>{lastmod}</lastmod>",
        f"    <changefreq>{page.changefreq}</changefreq>",
        f"    <priority>{page.priority}</priority>",
    ]
    if page.og_image:
        lines.extend(
            (
                "    <image:image>",
                f"      <image:loc>{base_url}{OG_IMAGE_PATH}</image:loc>",
                "    </image:image>",
            )
        )
    lines.append("  </url>")
    return "\n".join(lines)


def build_marketing_sitemap_xml(base_url: str, *, lastmod: str) -> str:
    """Urlset публичных страниц: RU и EN локали, связанные xhtml:link hreflang."""
    blocks = [
        _url_block(base_url, page, locale=locale, lastmod=lastmod)
        for page in PUBLIC_PAGES
        for locale in SEO_LOCALES
    ]
    urls_xml = "\n".join(blocks)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="{_SITEMAP_XMLNS}" '
        f'xmlns:xhtml="{_XHTML_XMLNS}" '
        f'xmlns:image="{_IMAGE_XMLNS}">\n'
        f"{urls_xml}\n"
        "</urlset>\n"
    )


def build_blog_sitemap_xml(base_url: str, entries: list[tuple[str, str]]) -> str:
    """Urlset постов блога; ``entries`` — пары ``(loc_path, lastmod_iso)``."""
    blocks = "\n".join(
        "  <url>\n"
        + f"    <loc>{escape(base_url + '/' + path.lstrip('/'))}</loc>\n"
        + f"    <lastmod>{escape(lastmod)}</lastmod>\n"
        + "    <changefreq>monthly</changefreq>\n"
        + "    <priority>0.60</priority>\n"
        + "  </url>"
        for path, lastmod in entries
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="{_SITEMAP_XMLNS}">\n'
        f"{blocks}\n"
        "</urlset>\n"
    )


def build_sitemap_index_xml(base_url: str, sitemaps: list[tuple[str, str | None]]) -> str:
    """Sitemapindex: пары ``(path, lastmod|None)`` — дочерние карты маркетинга, блога и docs."""
    entries: list[str] = []
    for path, lastmod in sitemaps:
        lastmod_xml = f"\n    <lastmod>{escape(lastmod)}</lastmod>" if lastmod else ""
        entries.append(
            "  <sitemap>\n"
            + f"    <loc>{escape(base_url + '/' + path.lstrip('/'))}</loc>{lastmod_xml}\n"
            + "  </sitemap>"
        )
    entries_xml = "\n".join(entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<sitemapindex xmlns="{_SITEMAP_XMLNS}">\n'
        f"{entries_xml}\n"
        "</sitemapindex>\n"
    )
