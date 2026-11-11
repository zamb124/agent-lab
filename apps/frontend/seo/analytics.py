"""SEO-аналитика посетителей: классификация поверхности, UA и источников.

Чистые функции для ``SeoAnalyticsMiddleware``: решает, какие запросы — визиты
на публичную поверхность (маркетинг, документация, блог, llms-фиды, seo-файлы),
нормализует дименшены события ``seo.visit`` и считает стабильный псевдо-ид
посетителя. Никакого I/O — все ветви покрыты тестами.

Расширение: новая публичная поверхность попадает сюда через ``PUBLIC_PAGE_PATHS``
(реестр) или префиксные правила — алерты и дашборд править не надо.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from apps.frontend.seo.pages import PUBLIC_PAGE_PATHS, SeoLocale

# --- Поверхность --------------------------------------------------------------

_DOC_PREFIXES = ("documentation/", "en/documentation/")
_BLOG_PREFIXES = ("blog/", "en/blog/")
# Корневые seo-файлы: llms.txt, robots.txt, sitemap*.xml, favicon.ico,
# IndexNow-ключ (произвольный *.txt в корне).
_ROOT_TXT = re.compile(r"^[0-9a-zA-Z][0-9a-zA-Z_-]*\.txt$")

SurfaceKind = str


def surface_of(path: str) -> SurfaceKind | None:
    """Класс публичной поверхности или ``None`` — не SEO-запрос.

    Путь — без query, с ведущим ``/`` или без. Внутренние namespace
    (``/frontend/...`` — сервисные зеркала публичных роутеров) не считаем:
    их ходит только сама платформа.
    """
    p = path.strip("/").lower()
    if not p:
        return "page"
    if p.startswith("frontend/"):
        return None
    for prefix in _DOC_PREFIXES:
        if p == prefix.rstrip("/") or p.startswith(prefix):
            return "docs-md" if p.endswith(".md") or p.endswith(".txt") else "docs"
    for prefix in _BLOG_PREFIXES:
        if p == prefix.rstrip("/") or p.startswith(prefix):
            return "blog"
    if p == "robots.txt":
        return "robots"
    if p.startswith("sitemap") and p.endswith(".xml"):
        return "sitemap"
    if p in ("llms.txt", "llms-full.txt"):
        return "llms"
    if p == "favicon.ico":
        return "favicon"
    if _ROOT_TXT.match(p):
        return "indexnow"
    # ``en`` → ключ "" (лендинг) — сам входит в PUBLIC_PAGE_PATHS.
    key = p[3:] if p.startswith("en/") else ("" if p == "en" else p)
    return "page" if key in PUBLIC_PAGE_PATHS else None


def locale_of(path: str) -> SeoLocale | None:
    """Локаль публичного пути: ``en/...`` → en, остальное → ru."""
    p = path.lstrip("/").lower()
    if p == "en" or p.startswith("en/"):
        return "en"
    return "ru"


# --- User-Agent ---------------------------------------------------------------

# Порядок важен: первое совпадение побеждает (oai-searchbot внутри GPTBot UA —
# выделенный матчер до общего gptbot).
_BOT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("yandexbot", "yandexbot"),
    ("yandeximages", "yandexbot"),
    ("yandexmetrika", "yandexbot"),
    ("yandex", "yandexbot"),
    ("googlebot", "googlebot"),
    ("google-inspectiontool", "googlebot"),
    ("bingbot", "bingbot"),
    ("bingpreview", "bingbot"),
    ("oai-searchbot", "oai-searchbot"),
    ("chatgpt-user", "oai-searchbot"),
    ("gptbot", "gptbot"),
    ("claudebot", "claudebot"),
    ("claude-web", "claudebot"),
    ("anthropic", "claudebot"),
    ("perplexitybot", "perplexitybot"),
    ("perplexity-user", "perplexitybot"),
    ("amazonbot", "amazonbot"),
    ("applebot", "applebot"),
    ("duckduckbot", "duckduckbot"),
    ("baiduspider", "baiduspider"),
    ("ahrefsbot", "ahrefsbot"),
    ("semrushbot", "semrushbot"),
    ("mj12bot", "mj12bot"),
    ("bytespider", "bytespider"),
    ("meta-externalagent", "meta-bot"),
    ("facebookexternalhit", "link-preview"),
    ("telegrambot", "link-preview"),
    ("slackbot", "link-preview"),
    ("discordbot", "link-preview"),
    ("vkshare", "link-preview"),
    ("whatsapp", "link-preview"),
    ("twitterbot", "link-preview"),
    ("headlesschrome", "internal-renderer"),
    ("seo-smoke", "internal-renderer"),
    ("bot", "other-bot"),
    ("crawler", "other-bot"),
    ("spider", "other-bot"),
)

_BROWSER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("edg/", "edge"),
    ("opr/", "opera"),
    ("chrome/", "chrome"),
    ("firefox/", "firefox"),
    ("safari/", "safari"),
)

_MOBILE_PATTERNS = ("iphone", "android", "ipad", "mobile")


def classify_ua(ua: str | None) -> tuple[str, bool]:
    """``(family, is_bot)``: семейство UA для группировки и бот-признак."""
    if not ua:
        return "unknown", False
    low = ua.lower()
    for needle, family in _BOT_PATTERNS:
        if needle in low:
            return family, family not in ("link-preview", "internal-renderer")
    for needle, family in _BROWSER_PATTERNS:
        if needle in low:
            if any(m in low for m in _MOBILE_PATTERNS):
                return f"{family}-mobile", False
            return family, False
    for needle in ("curl", "wget", "python-requests", "httpx", "aiohttp", "go-http-client", "node"):
        if needle in low:
            return "http-client", False
    return "other", False


# --- Источник -----------------------------------------------------------------

def referer_host(referer: str | None) -> str:
    """Хост источника перехода: ``direct`` без Referer, иначе домен."""
    if not referer:
        return "direct"
    host = referer.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    if not host:
        return "direct"
    if host.endswith("linnex.io") or host.endswith("humanitec.ru"):
        return "internal"
    return host


# --- Посетитель ---------------------------------------------------------------

def visitor_id(ip: str | None, ua: str | None, salt: str) -> str:
    """Стабильный псевдо-ид посетителя: HMAC(ip|ua)[:16], без PII в логах."""
    material = f"{ip or ''}|{ua or ''}".encode("utf-8", "replace")
    return hmac.new(salt.encode(), material, hashlib.sha256).hexdigest()[:16]


__all__ = [
    "classify_ua",
    "locale_of",
    "referer_host",
    "surface_of",
    "visitor_id",
]
