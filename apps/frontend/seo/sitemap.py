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
    if page.sitemap_image:
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


def _blog_url_block(
    base_url: str, path: str, lastmod: str, alternates: list[tuple[str, str]]
) -> str:
    lines = [
        "  <url>",
        f"    <loc>{escape(base_url + '/' + path.lstrip('/'))}</loc>",
    ]
    for hreflang, href in alternates:
        lines.append(
            f'    <xhtml:link rel="alternate" hreflang="{hreflang}" href="{escape(href)}"/>'
        )
    lines.extend(
        (
            f"    <lastmod>{escape(lastmod)}</lastmod>",
            "    <changefreq>monthly</changefreq>",
            "    <priority>0.60</priority>",
            "  </url>",
        )
    )
    return "\n".join(lines)


def build_blog_sitemap_xml(
    base_url: str, entries: list[tuple[str, str | None, str]]
) -> str:
    """Urlset постов блога с hreflang-парами RU↔EN.

    ``entries`` — ``(ru_path, en_path|None, lastmod_iso)`` по посту: RU-блок
    всегда, EN-блок — при наличии английской версии; оба связываются
    ``xhtml:link``-альтернативами, как в маркетинг-карте.
    """
    blocks: list[str] = []
    for ru_path, en_path, lastmod in entries:
        ru_url = base_url + "/" + ru_path.lstrip("/")
        if en_path is None:
            # Самоссылочный hreflang обязателен и для одноязычного поста.
            blocks.append(_blog_url_block(base_url, ru_path, lastmod, [("ru", ru_url)]))
            continue
        en_url = base_url + "/" + en_path.lstrip("/")
        alternates = [("ru", ru_url), ("en", en_url), ("x-default", ru_url)]
        blocks.append(_blog_url_block(base_url, ru_path, lastmod, alternates))
        blocks.append(_blog_url_block(base_url, en_path, lastmod, alternates))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + f'<urlset xmlns="{_SITEMAP_XMLNS}" xmlns:xhtml="{_XHTML_XMLNS}">\n'
        + "\n".join(blocks)
        + "\n</urlset>\n"
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
