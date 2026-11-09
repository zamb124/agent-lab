"""Серверная мета-обработка index.html SPA: абсолютные canonical/OG и robots-режим.

Снапшот-конвейер (``services/seo_snapshot_service.py`` + ``seo/postprocess.py``)
— основной источник head; этот модуль чинит index.html-фолбек, чтобы даже без
снапшота head был корректным.
"""

from __future__ import annotations

import re

from apps.frontend.seo.pages import SeoLocale, page_url
from core.config.models import PlatformBrandConfig

OG_IMAGE_PATH = "/static/frontend/assets/images/main_img.png"
_INDEX_ROBOTS = "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1"

_TITLE_RE = re.compile(r"<title>[^<]*</title>")
_DESCRIPTION_RE = re.compile(r'(<meta name="description" content=")[^"]*(")')
_CANONICAL_RE = re.compile(r'(<link rel="canonical" href=")[^"]*(")')
_ROBOTS_RE = re.compile(r'(<meta name="robots" content=")[^"]*(")')
_HTML_LANG_RE = re.compile(r'(<html lang=")[^"]*(")')
_META_PROPERTY_RE_TEMPLATE = r'(<meta property="{prop}" content=")[^"]*(")'
_META_NAME_RE_TEMPLATE = r'(<meta name="{name}" content=")[^"]*(")'
_HEAD_CLOSE_RE = re.compile(r"</head>", re.IGNORECASE)


def _set(pattern: str | re.Pattern[str], html: str, value: str) -> str:
    return re.sub(pattern, lambda m: m.group(1) + value + m.group(2), html, count=1)



def _brand_description(brand: PlatformBrandConfig, locale: SeoLocale) -> str:
    if locale == "en":
        return (
            f"{brand.platform_name} — five products in one platform: AI Studio, Knowledge Base, "
            "NetWorkle, Sync and Documents."
        )
    return (
        f"{brand.platform_name} — пять продуктов в одном контуре: AI Studio, Knowledge Base, "
        "NetWorkle, Sync и Документы."
    )


def render_index_html(
    template: str,
    *,
    brand: PlatformBrandConfig,
    seo_base_url: str,
    locale: SeoLocale,
    indexable: bool,
    path: str = "",
) -> str:
    """index.html с абсолютными canonical/OG для бренда и robots-режимом страницы.

    ``seo_base_url`` — всегда primary apex (canonical-домен), не request host.
    ``path`` — реестровый путь страницы ("" — корень): canonical и hreflang
    собираются по нему, иначе все страницы канонизировались бы на корень.
    """
    title = (
        f"{brand.platform_name} — business automation platform"
        if locale == "en"
        else f"{brand.platform_name} — платформа автоматизации бизнеса"
    )
    description = _brand_description(brand, locale)
    canonical_url = page_url(seo_base_url, path, locale)
    og_image = seo_base_url + OG_IMAGE_PATH
    robots = _INDEX_ROBOTS if indexable else "noindex,nofollow"
    og_locale = "en_US" if locale == "en" else "ru_RU"

    html = _TITLE_RE.sub(f"<title>{title}</title>", template, count=1)
    html = _set(_HTML_LANG_RE, html, "en" if locale == "en" else "ru")
    html = _set(_DESCRIPTION_RE, html, description)
    html = _set(_CANONICAL_RE, html, canonical_url)
    html = _set(_ROBOTS_RE, html, robots)
    for prop, value in (
        ("og:site_name", brand.platform_name),
        ("og:title", title),
        ("og:description", description),
        ("og:url", canonical_url),
        ("og:image", og_image),
        ("og:locale", og_locale),
    ):
        html = _set(_META_PROPERTY_RE_TEMPLATE.format(prop=prop), html, value)
    for name, value in (
        ("twitter:title", title),
        ("twitter:description", description),
        ("twitter:image", og_image),
        ("apple-mobile-web-app-title", brand.platform_name),
    ):
        html = _set(_META_NAME_RE_TEMPLATE.format(name=name), html, value)
    if indexable:
        ru_url = page_url(seo_base_url, path, "ru")
        en_url = page_url(seo_base_url, path, "en")
        alternates = (
            f'<link rel="alternate" hreflang="ru" href="{ru_url}"/>\n'
            f'<link rel="alternate" hreflang="en" href="{en_url}"/>\n'
            f'<link rel="alternate" hreflang="x-default" href="{ru_url}"/>\n'
            "</head>"
        )
        html = _HEAD_CLOSE_RE.sub(alternates, html, count=1)
    return html
