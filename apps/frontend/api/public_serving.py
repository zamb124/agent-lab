"""Публичная раздача сайта: SEO-протоколы, блог-статика, снапшоты, SPA-fallback.

Всё, что отдаёт сайт наружу людям и краулерам, живёт здесь, а не в
``apps/frontend/main.py``: ``robots.txt``, sitemap-index и child-карты,
``llms.txt``, IndexNow key-verification, статика блога из ``seo-dist``,
DSD-снапшоты через ``SeoSnapshotService`` и последний catch-all, который
отдаёт SPA-оболочку с серверной метой (indexable/noindex).
"""

from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    Response,
)

from apps.frontend.config import get_frontend_settings
from apps.frontend.di import Di
from apps.frontend.seo.blog_files import (
    blog_feed_path,
    blog_post_html_path,
    read_blog_index,
)
from apps.frontend.seo.llms import build_llms_txt
from apps.frontend.seo.meta import render_index_html
from apps.frontend.seo.pages import SeoLocale, public_page_for_path
from apps.frontend.seo.robots import build_robots_txt
from apps.frontend.seo.sitemap import (
    build_blog_sitemap_xml,
    build_marketing_sitemap_xml,
    build_sitemap_index_xml,
)
from apps.frontend.services.seo_snapshot_service import SNAPSHOT_BYPASS_PARAM
from core.app.spa import resolve_ui_static_dir
from core.config.loader import get_project_root
from core.http.client import get_httpx_client
from core.logging import get_logger
from core.platform_brand.resolver import (
    resolve_brand,
    resolve_brand_or_primary,
    resolve_seo_base_url,
)
from core.utils.domain import extract_company_subdomain
from core.websocket import WsCommandError

logger = get_logger(__name__)

public_router = APIRouter(include_in_schema=False)

_UI_STATIC_PATH = resolve_ui_static_dir(Path(__file__).resolve().parents[1] / "ui")

# Пути, которые catch-all не должен отдавать как SPA: API, статика, WS,
# документация и файлы, у которых есть собственные хендлеры.
# startswith-проверка: только настоящие префиксы (со слэшем); точные пути
# без слэша — в _SPA_EXCLUDED_EXACT, иначе "documentation" съедал бы и
# гипотетический публичный "documentation-portal".
_SPA_EXCLUDED_PREFIXES = (
    "api/",
    "static/",
    "ws/",
    "l/",
    "documentation/",
    "frontend/api/",
    "frontend/static/",
    "frontend/ws/",
    "frontend/documentation/",
    "design-system/",
    "frontend/design-system/",
)
_SPA_EXCLUDED_EXACT = (
    "manifest.json",
    "sw.js",
    "offline.html",
    "favicon.ico",
    "documentation",
    "frontend/documentation",
    "robots.txt",
    "sitemap.xml",
    "sitemap-marketing.xml",
    "sitemap-blog.xml",
    "llms.txt",
    "frontend/robots.txt",
    "frontend/sitemap.xml",
    "frontend/llms.txt",
)


def _require_host(request: Request) -> str:
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise WsCommandError(
            "ws_invalid_payload", "Host header is required", error_code="ws_invalid_payload"
        )
    return str(host).strip()


def _not_found() -> WsCommandError:
    return WsCommandError("not_found", "Not found", error_code="not_found")


def _marketing_sitemap_lastmod() -> str:
    """lastmod маркетинг-карты — mtime собранного UI-бандла (реальная дата контента)."""
    index_path = _UI_STATIC_PATH / "index.html"
    try:
        mtime = index_path.stat().st_mtime
    except OSError:
        return datetime.now(UTC).strftime("%Y-%m-%d")
    return datetime.fromtimestamp(mtime, UTC).strftime("%Y-%m-%d")


def _blog_sitemap_entries() -> list[tuple[str, str | None, str]]:
    """``(ru_path, en_path|None, lastmod)`` по посту — hreflang-пары в карте."""
    entries: list[tuple[str, str | None, str]] = []
    for item in read_blog_index():
        slug = str(item["slug"])
        date = str(item["updated"])
        en_path = f"en/blog/{slug}" if item.get("has_en") else None
        entries.append((f"blog/{slug}", en_path, date))
    return entries


@public_router.get("/robots.txt")
@public_router.get("/frontend/robots.txt")
async def get_robots_txt() -> PlainTextResponse:
    # Sitemap-ссылка — канонический домен: зеркала обслуживают тот же файл,
    # но краулера должна вести только canonical-карта.
    return PlainTextResponse(
        content=build_robots_txt(resolve_seo_base_url()),
        headers={"Cache-Control": "public, max-age=300"},
    )


@public_router.get("/sitemap.xml")
@public_router.get("/frontend/sitemap.xml")
async def get_sitemap_xml() -> Response:
    """Корневая карта — sitemapindex на маркетинг, блог и документацию (RU+EN)."""
    lastmod = _marketing_sitemap_lastmod()
    sitemap_xml = build_sitemap_index_xml(
        resolve_seo_base_url(),
        [
            ("/sitemap-marketing.xml", lastmod),
            ("/sitemap-blog.xml", lastmod),
            ("/documentation/sitemap.xml", None),
            ("/documentation/en/sitemap.xml", None),
        ],
    )
    return Response(
        content=sitemap_xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


@public_router.get("/sitemap-marketing.xml")
@public_router.get("/frontend/sitemap-marketing.xml")
async def get_sitemap_marketing_xml() -> Response:
    sitemap_xml = build_marketing_sitemap_xml(
        resolve_seo_base_url(), lastmod=_marketing_sitemap_lastmod()
    )
    return Response(
        content=sitemap_xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


@public_router.get("/sitemap-blog.xml")
@public_router.get("/frontend/sitemap-blog.xml")
async def get_sitemap_blog_xml() -> Response:
    sitemap_xml = build_blog_sitemap_xml(resolve_seo_base_url(), _blog_sitemap_entries())
    return Response(
        content=sitemap_xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


_FAVICON_SOURCE = (
    get_project_root()
    / "core"
    / "frontend"
    / "static"
    / "assets"
    / "service_logos"
    / "favicon-48x48.png"
)
_favicon_ico_bytes: bytes | None = None


def _render_favicon_ico() -> bytes:
    """Мульти-size ICO (16/32/48) из брендового PNG — собирается один раз на процесс."""
    global _favicon_ico_bytes
    if _favicon_ico_bytes is None:
        from PIL import Image

        buf = io.BytesIO()
        Image.open(_FAVICON_SOURCE).save(buf, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
        _favicon_ico_bytes = buf.getvalue()
    return _favicon_ico_bytes


@public_router.get("/favicon.ico")
async def get_favicon_ico() -> Response:
    """``/favicon.ico`` — конвенция браузеров и Яндекса для иконки сайта в выдаче."""
    return Response(
        content=_render_favicon_ico(),
        media_type="image/vnd.microsoft.icon",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@public_router.get("/llms.txt")
@public_router.get("/frontend/llms.txt")
async def serve_llms_txt(request: Request) -> PlainTextResponse:
    brand = resolve_brand(_require_host(request))
    return PlainTextResponse(
        content=build_llms_txt(resolve_seo_base_url(), brand),
        headers={"Cache-Control": "public, max-age=300"},
    )


_index_template_cache: str | None = None
_index_render_cache: dict[tuple[str, str, bool], str] = {}


def _index_template() -> str | None:
    global _index_template_cache
    if _index_template_cache is None:
        index_path = _UI_STATIC_PATH / "index.html"
        if not index_path.exists():
            return None
        _index_template_cache = index_path.read_text(encoding="utf-8")
    return _index_template_cache


def _rendered_index_html(*, locale: SeoLocale, indexable: bool, path: str) -> str | None:
    """index.html с серверной метой бренда; кэш по (locale, indexable, path).

    Для noindex-страниц canonical несущественен — ключ схлопывается в "",
    чтобы приватные пути не раздували кэш.
    """
    template = _index_template()
    if template is None:
        return None
    meta_path = path if indexable else ""
    key = (meta_path, locale, indexable)
    cached = _index_render_cache.get(key)
    if cached is None:
        brand = resolve_brand_or_primary(None)
        cached = render_index_html(
            template,
            brand=brand,
            seo_base_url=resolve_seo_base_url(),
            locale=locale,
            indexable=indexable,
            path=meta_path,
        )
        _index_render_cache[key] = cached
    return cached


def _spa_response(*, locale: SeoLocale, indexable: bool, path: str) -> Response:
    html = _rendered_index_html(locale=locale, indexable=indexable, path=path)
    if html is None:
        raise WsCommandError("not_found", "Frontend UI not built yet", error_code="not_found")
    headers = {"Cache-Control": "no-cache"}
    if not indexable:
        headers["X-Robots-Tag"] = "noindex, nofollow"
    return HTMLResponse(content=html, headers=headers)


# Slug поста — формат генератора blog_build: строго, без точек и слэшей
# (иначе ``..``/``%2e%2e`` ушёл бы в Path-join за пределы seo-dist/blog).
_BLOG_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


def _blog_post_response(full_path: str) -> Response | None:
    """Статическая страница поста из seo-dist; ``None`` — нет файла, дальше SPA."""
    locale: SeoLocale = "ru"
    rest = full_path
    if full_path.startswith("en/blog/"):
        locale = "en"
        rest = full_path[len("en/") :]
    if not rest.startswith("blog/"):
        return None
    slug = rest[len("blog/") :].strip("/")
    if _BLOG_SLUG_RE.fullmatch(slug) is None:
        return None
    page_path = blog_post_html_path(slug, locale)
    if not page_path.is_file():
        return None
    return FileResponse(
        page_path,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


async def _shop_public_page(request: Request, upstream_path: str) -> Response | None:
    """HTML публичной страницы shop (витрина/агрегатор) по Host запроса.

    200 → тело + кэш-заголовки shop; 304 → пустой ответ; другой статус →
    None (вызывающий решает: SPA или auth-wall). Сетевые ошибки shop
    пробрасываются — инфраструктура не маскируется фолбеком.
    """
    host = request.headers.get("host", "")
    shop_base = get_frontend_settings().server.get_service_url("shop").rstrip("/")
    forward_headers = {"host": host, "x-forwarded-host": host}
    if_none_match = request.headers.get("if-none-match")
    if if_none_match:
        forward_headers["if-none-match"] = if_none_match
    url = f"{shop_base}{upstream_path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    async with get_httpx_client(timeout=10.0) as client:
        upstream = await client.request(request.method, url, headers=forward_headers)
    relay: dict[str, str] = {}
    for key in ("content-type", "etag", "cache-control"):
        value = upstream.headers.get(key)
        if value:
            relay[key] = value
    if upstream.status_code == 304:
        return Response(status_code=304, headers=relay)
    if upstream.status_code != 200:
        return None
    return Response(content=upstream.content, status_code=200, headers=relay)


# SPA-резерв (все неизвестные пути → index.html или снапшот публичной страницы).
# Регистрируется последним в роутере — роутер подключается после всех остальных.
@public_router.get("/")
@public_router.get("/{full_path:path}")
async def serve_public_page(request: Request, di: Di, full_path: str = "") -> Response:
    if full_path.startswith(_SPA_EXCLUDED_PREFIXES) or full_path in _SPA_EXCLUDED_EXACT:
        raise _not_found()

    # IndexNow key-verification: /<key>.txt из настроек.
    indexnow_key = get_frontend_settings().indexnow_key
    if indexnow_key and full_path == f"{indexnow_key}.txt":
        return PlainTextResponse(content=indexnow_key)

    # RSS-фида блога — статика seo-dist.
    if full_path == "blog/feed.xml":
        feed = blog_feed_path()
        if not feed.is_file():
            raise _not_found()
        return FileResponse(
            feed,
            media_type="application/rss+xml; charset=utf-8",
            headers={"Cache-Control": "public, max-age=300"},
        )

    # Посты блога — статические страницы seo-dist (индексируемый контент).
    blog_response = _blog_post_response(full_path)
    if blog_response is not None:
        return blog_response

    # /market — публичный агрегатор витрин для всех пользователей (в проде
    # ingress отдаёт его прямо в shop; в dev и как резерв — прокси сюда).
    if full_path == "market":
        market = await _shop_public_page(request, "/shop/api/v1/public/market")
        if market is not None:
            return market
        raise _not_found()

    # Аноним на корне поддомена компании → её published-витрина; магазин не
    # активирован или поддомен не компании — обычный SPA с экраном авторизации.
    if (
        full_path == ""
        and request.cookies.get("auth_token") is None
        and extract_company_subdomain(request.headers.get("host", "")) is not None
    ):
        storefront = await _shop_public_page(request, "/shop/api/v1/public/host")
        if storefront is not None:
            return storefront

    locale: SeoLocale = "ru"
    path = full_path
    if full_path == "en" or full_path.startswith("en/"):
        locale = "en"
        path = full_path[2:].strip("/") if len(full_path) > 2 else ""
    page = public_page_for_path(path)
    # Снапшот — основной ответ публичной страницы для всех (не только ботов).
    # ?spa_shell=1 — собственный fetch пререндера, иначе цикл.
    if page is not None and SNAPSHOT_BYPASS_PARAM not in request.query_params:
        snapshot = await di.seo_snapshot_service.snapshot_html(page, locale)
        if snapshot is not None:
            return HTMLResponse(
                content=snapshot,
                headers={"Cache-Control": "public, max-age=60, s-maxage=300"},
            )
    return _spa_response(locale=locale, indexable=page is not None, path=path)
