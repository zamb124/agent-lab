"""Постобработка DSD-снапшота публичной страницы перед отдачей краулеру и пользователю.

Снапшот приходит с внутреннего URL (http://frontend:port/...), поэтому все
absolute-URL в head переписываются на canonical origin (``resolve_seo_base_url``),
добавляются hreflang-альтернативы, JSON-LD граф страницы и корректный robots.
Для en-локали root-relative ссылки на публичные страницы получают префикс ``/en``.
"""

from __future__ import annotations

import re

from apps.frontend.seo.ld_json import render_ld_script
from apps.frontend.seo.pages import (
    PUBLIC_PAGE_PATHS,
    PublicPage,
    SeoLocale,
    page_url,
)
from core.config.models import PlatformBrandConfig

_INDEX_ROBOTS = "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1"

_HTML_LANG_RE = re.compile(r'(<html[^>]*\blang=")[^"]*(")', re.IGNORECASE)
_CANONICAL_RE = re.compile(r'(<link[^>]*\brel="canonical"[^>]*\bhref=")[^"]*(")', re.IGNORECASE)
_ROBOTS_RE = re.compile(r'(<meta[^>]*\bname="robots"[^>]*\bcontent=")[^"]*(")', re.IGNORECASE)
_OG_URL_RE = re.compile(r'(<meta[^>]*\bproperty="og:url"[^>]*\bcontent=")[^"]*(")', re.IGNORECASE)
_OG_IMAGE_RE = re.compile(
    r'(<meta[^>]*\bproperty="og:image"[^>]*\bcontent=")[^"]*(")', re.IGNORECASE
)
_META_NAME_IMG_RE = re.compile(
    r'(<meta[^>]*\bname="twitter:image"[^>]*\bcontent=")[^"]*(")', re.IGNORECASE
)
_OG_LOCALE_RE = re.compile(
    r'(<meta[^>]*\bproperty="og:locale"[^>]*\bcontent=")[^"]*(")', re.IGNORECASE
)
_EXISTING_LD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL
)
_EXISTING_HREFLANG_RE = re.compile(r'<link[^>]*\bhreflang="[^"]*"[^>]*/?>', re.IGNORECASE)
_HEAD_CLOSE_RE = re.compile(r"</head>", re.IGNORECASE)
# href публичной страницы: root-relative и canonical-absolute, с опциональным
# подпутём (/blog/<slug>) и суффиксом ?query/#anchor.
_HREF_PUBLIC_RE_TEMPLATE = r'href="({base})?(/{path}(?:/[^"#?]*)?)([#?"])'
_HREF_ROOT_RE = re.compile(r'href="/([#?"])')


def _set(pattern: re.Pattern[str], html: str, value: str) -> str:
    return pattern.sub(lambda m: m.group(1) + value + m.group(2), html, count=1)



def _rewrite_origin(html: str, internal_origin: str, seo_base_url: str) -> str:
    """Абсолютные URL внутреннего fetch-origin → canonical origin.

    Снапшот рендерится по service URL (http://frontend:8002), поэтому все
    абсолютные ссылки на него в head/body переписываются на canonical-домен.
    """
    return html.replace(f"{internal_origin}/", f"{seo_base_url}/").replace(
        internal_origin, seo_base_url
    )


def _en_href(match: re.Match[str]) -> str:
    """``href="/x"``/``href="<seo_base_url>/x"`` → ``href="<origin>/en/x"``."""
    origin = match.group(1)
    return f'href="{origin if origin is not None else ""}/en{match.group(2)}{match.group(3)}'


def _rewrite_en_hrefs(html: str, seo_base_url: str) -> str:
    """Публичные href → ``/en``-локаль в en-снапшоте.

    Покрывает root-relative (``/products/rag``), canonical-absolute
    (``<seo_base_url>/products/rag``), подпути (``/blog/<slug>``) и
    суффиксы ``?query``/``#anchor``.
    """
    paths = sorted(PUBLIC_PAGE_PATHS - {""}, key=len, reverse=True)
    base = re.escape(seo_base_url)
    for path in paths:
        html = re.sub(
            _HREF_PUBLIC_RE_TEMPLATE.format(base=base, path=re.escape(path)),
            _en_href,
            html,
        )
    html = _HREF_ROOT_RE.sub(r'href="/en\1', html)
    return html


def postprocess_snapshot(
    html: str,
    *,
    page: PublicPage,
    locale: SeoLocale,
    brand: PlatformBrandConfig,
    seo_base_url: str,
    internal_origin: str,
) -> str:
    """Отрендеренный DSD-HTML → канонический индексируемый документ."""
    canonical = page_url(seo_base_url, page.path, locale)
    out = _rewrite_origin(html, internal_origin, seo_base_url)
    out = _set(_HTML_LANG_RE, out, locale)
    out = _set(_CANONICAL_RE, out, canonical)
    out = _set(_ROBOTS_RE, out, _INDEX_ROBOTS)
    out = _set(_OG_LOCALE_RE, out, "en_US" if locale == "en" else "ru_RU")
    out = _set(_OG_URL_RE, out, canonical)
    og_image = f"{seo_base_url}/static/frontend/assets/images/main_img.png"
    out = _set(_OG_IMAGE_RE, out, og_image)
    out = _set(_META_NAME_IMG_RE, out, og_image)
    out = _EXISTING_LD_RE.sub("", out)
    out = _EXISTING_HREFLANG_RE.sub("", out)

    head_injections: list[str] = []
    ru_url = page_url(seo_base_url, page.path, "ru")
    en_url = page_url(seo_base_url, page.path, "en")
    head_injections.append(f'<link rel="alternate" hreflang="ru" href="{ru_url}"/>')
    head_injections.append(f'<link rel="alternate" hreflang="en" href="{en_url}"/>')
    head_injections.append(f'<link rel="alternate" hreflang="x-default" href="{ru_url}"/>')
    ld_script = render_ld_script(page, brand=brand, seo_base_url=seo_base_url, locale=locale)
    if ld_script:
        head_injections.append(ld_script)
    out = _HEAD_CLOSE_RE.sub("\n".join(head_injections) + "\n</head>", out, count=1)

    if locale == "en":
        out = _rewrite_en_hrefs(out, seo_base_url)
    return out
