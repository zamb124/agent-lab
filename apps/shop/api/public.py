"""Публичные анонимные маршруты shop: витрина, заказ, агрегатор.

Авторизации здесь нет: витрина и поиск доступны покупателю без аккаунта.
Read-path идёт в Redis-снапшот с ETag/304 — PostgreSQL не трогается
на повторных просмотрах меню.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from collections.abc import AsyncIterator
from html import escape
from typing import Annotated

import segno
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from apps.shop.api.market_shell import market_html
from apps.shop.api.storefront import storefront_html
from apps.shop.di import Di
from apps.shop.models import Shop
from apps.shop.models.api import (
    ShopCartPriceRequest,
    ShopCartPriceResponse,
    ShopFavoriteResponse,
    ShopFavoriteSetRequest,
    ShopFeedbackSetRequest,
    ShopMyOrderDetailResponse,
    ShopMyOrderListItemResponse,
    ShopNotifyBackRequest,
    ShopNotifyBackResponse,
    ShopOrderCreatedResponse,
    ShopOrderCreateRequest,
    ShopOrderFeedbackResponse,
    ShopOrderStatusResponse,
    ShopPersonalResponse,
    ShopReviewsResponse,
    ShopStorefrontGeoResponse,
    normalize_shop_theme,
)
from apps.shop.models.enums import ShopOrderStatus
from apps.shop.realtime.operations import (
    ShopCartPricePayload,
    ShopFavoriteSetPayload,
    ShopFeedbackSetPayload,
    ShopMyOrderCodePayload,
    ShopMyOrdersListPayload,
    ShopNotifyBackPayload,
    ShopOrderCreatePayload,
    ShopPersonalPayload,
    ShopPublicOrderStatusPayload,
    ShopReviewsListPayload,
    ShopStorefrontGeoPayload,
    op_public_cart_price,
    op_public_favorite_set,
    op_public_feedback_set,
    op_public_my_order_cancel,
    op_public_my_order_get,
    op_public_my_orders_list,
    op_public_notify_back,
    op_public_order_create,
    op_public_order_status,
    op_public_personal,
    op_public_reviews_list,
    op_public_storefront_geo,
)
from core.context import require_context
from core.errors.boundary import PlatformNotFoundError
from core.http.client import get_httpx_client
from core.pagination import OffsetPage
from core.platform_brand.resolver import resolve_brand_or_primary
from core.types import JsonObject, parse_json_object
from core.utils.geo import zone_covers_point
from core.websocket import WsCommandError, raise_not_found

router = APIRouter(prefix="/public", tags=["shop-public"])


async def _snapshot_or_404(di: Di, slug: str) -> JsonObject:
    snapshot = await di.storefront_service.get_snapshot(slug)
    if snapshot is None:
        raise WsCommandError("not_found", "Storefront not found", error_code="storefront_not_found")
    return snapshot


_THEME_PREVIEW_KEYS: dict[str, str] = {
    "tpreset": "preset",
    "taccent": "accent_color",
    "tmode": "mode",
    "thero": "hero_style",
    "tbackdrop": "backdrop",
}


def _theme_preview(request: Request) -> JsonObject | None:
    """Переопределение темы из query-параметров конструктора; None — без превью."""
    overrides: JsonObject = {}
    for param, field in _THEME_PREVIEW_KEYS.items():
        value = request.query_params.get(param)
        if value:
            overrides[field] = value
    return overrides or None


@router.get("/storefront/{slug}", response_model=None)
async def get_storefront(slug: str, request: Request, di: Di) -> Response:
    """Снапшот витрины с ETag: If-None-Match → 304 без тела."""
    snapshot = await _snapshot_or_404(di, slug)
    etag = di.storefront_service.snapshot_etag(snapshot)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(
        content=snapshot,
        headers={"ETag": etag, "Cache-Control": "public, max-age=30"},
    )


@router.get("/s/{slug}", response_model=None)
async def get_storefront_page(slug: str, request: Request, di: Di) -> HTMLResponse:
    """SSR-lite HTML витрины: снапшот inline, меню и корзина — клиентский JS.

    ``?tpreset=``, ``?taccent=``, ``?tmode=``, ``?thero=``, ``?tbackdrop=`` —
    мгновенный предпросмотр темы из конструктора: переопределяют theme до
    сохранения; кэш отключается, значения нормализуются к канону модели.
    """
    snapshot = await _snapshot_or_404(di, slug)
    preview = _theme_preview(request)
    etag = di.storefront_service.snapshot_etag(snapshot)
    if preview is None and request.headers.get("if-none-match") == etag:
        return HTMLResponse(status_code=304, headers={"ETag": etag})
    if preview is not None:
        theme = snapshot.get("theme")
        snapshot["theme"] = normalize_shop_theme(
            {**(theme if isinstance(theme, dict) else {}), **preview}
        )
    canonical = f"https://{slug}.{di.settings.storefront_domain_suffix}"
    image_id = snapshot.get("cover_file_id") or snapshot.get("logo_file_id")
    image_url = (
        f"{canonical}/shop/api/v1/files/download/{image_id}"
        if isinstance(image_id, str) and image_id
        else ""
    )
    return HTMLResponse(
        content=storefront_html(
            snapshot,
            canonical_url=canonical,
            image_url=image_url,
            host=request.headers.get("host", ""),
        ),
        headers={"ETag": etag, "Cache-Control": "public, max-age=30"},
    )


@router.post("/storefront/{slug}/orders", response_model=ShopOrderCreatedResponse)
async def create_order(
    slug: str, payload: ShopOrderCreateRequest, request: Request, di: Di
) -> ShopOrderCreatedResponse:
    """Приём заказа: тот же `op_*`, что и у WS-команды; лимит по IP до работы."""
    client_key = request.client.host if request.client else "unknown"
    if not await di.storefront_service.check_order_rate_limit(client_key):
        raise WsCommandError(
            "rate_limited",
            "Too many orders",
            error_code="order_rate_limited",
        )
    op_payload = ShopOrderCreatePayload.model_validate({"slug": slug, **payload.model_dump()})
    return await op_public_order_create(op_payload, user=require_context().user, di=di)


@router.get("/storefront/{slug}/delivery-check", response_model=None)
async def delivery_check(
    slug: str,
    di: Di,
    address: str = "",
    lat: float | None = None,
    lng: float | None = None,
) -> JsonObject:
    """Живой чек «доставим ли по адресу»: точка клиента или резолв текста.

    ``lat``/``lng`` — координаты выбранной подсказки или пина карты: сервер
    проверяет именно их, текст адреса остаётся подписью. Без точки адрес
    резолвится geo-справочником внутри зоны, затем внешним геокодером.
    """
    shop = await di.order_service.resolve_published_shop(slug)
    return await di.order_service.check_delivery(shop, address, lat=lat, lng=lng)


@router.get("/storefront/{slug}/address-suggest", response_model=None)
async def address_suggest(
    slug: str,
    q: str,
    di: Di,
    lat: float | None = None,
    lng: float | None = None,
) -> JsonObject:
    """Автокомплит адреса по справочнику geo внутри зоны доставки витрины.

    ``lat``/``lng`` — точка покупателя для сортировки выдачи по близости.
    """
    shop = await di.order_service.resolve_published_shop(slug)
    if len(q.strip()) < 2:
        return {"items": []}
    return await di.order_service.address_suggest(shop, q.strip(), lat=lat, lng=lng)


@router.get("/storefront/{slug}/address-reverse", response_model=None)
async def address_reverse(slug: str, lat: float, lng: float, di: Di) -> JsonObject:
    """Ближайший адрес к пину карты — имя для подписи выбранной точки."""
    shop = await di.order_service.resolve_published_shop(slug)
    return await di.order_service.address_reverse(shop, lat=lat, lng=lng)


@router.get("/aggregate/address-suggest", response_model=None)
async def aggregate_address_suggest(
    q: str,
    di: Di,
    lat: float | None = None,
    lng: float | None = None,
) -> JsonObject:
    """Автокомплит адреса на /market: geo-справочник без зоны (все города)."""
    if len(q.strip()) < 2:
        return {"items": []}
    return await di.aggregate_service.address_suggest(q.strip(), lat=lat, lng=lng)


@router.get("/aggregate/geocode", response_model=None)
async def aggregate_geocode(address: str, di: Di) -> dict[str, object]:
    """Адрес покупателя → точка карты для фильтра витрин на /market."""
    geo = await di.geocoder.geocode(address)
    if geo is None:
        raise WsCommandError(
            "not_found", "Address could not be geocoded", error_code="address_unverifiable"
        )
    return {
        "lat": geo.lat,
        "lng": geo.lng,
        "normalized": geo.normalized_address,
        "city": geo.city,
    }


@router.post("/storefront/{slug}/cart/price", response_model=ShopCartPriceResponse)
async def price_cart(slug: str, payload: ShopCartPriceRequest, di: Di) -> ShopCartPriceResponse:
    """Живой расчёт корзины: сервер считает цены и акции до оформления."""
    op_payload = ShopCartPricePayload.model_validate({"slug": slug, **payload.model_dump()})
    return await op_public_cart_price(op_payload, user=require_context().user, di=di)


@router.get("/orders/{public_code}", response_model=ShopOrderStatusResponse)
async def get_order_status(public_code: str, di: Di) -> ShopOrderStatusResponse:
    return await op_public_order_status(
        ShopPublicOrderStatusPayload(public_code=public_code),
        user=require_context().user,
        di=di,
    )


# --- Кабинет покупателя: сквозная история по всем витринам ---


@router.get("/my/orders", response_model=OffsetPage[ShopMyOrderListItemResponse])
async def list_my_orders(
    di: Di,
    status: ShopOrderStatus | None = None,
    active: bool | None = None,
    limit: int = 30,
    offset: int = 0,
) -> OffsetPage[ShopMyOrderListItemResponse]:
    """Лента заказов покупателя: все витрины платформы, ownership по JWT."""
    return await op_public_my_orders_list(
        ShopMyOrdersListPayload(status=status, active=active, limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.get("/my/orders/{public_code}", response_model=ShopMyOrderDetailResponse)
async def get_my_order(public_code: str, di: Di) -> ShopMyOrderDetailResponse:
    """Карточка заказа: позиции, таймлайн, гео; чужой код — not-found."""
    return await op_public_my_order_get(
        ShopMyOrderCodePayload(public_code=public_code),
        user=require_context().user,
        di=di,
    )


@router.post("/my/orders/{public_code}/cancel", response_model=ShopMyOrderDetailResponse)
async def cancel_my_order(public_code: str, di: Di) -> ShopMyOrderDetailResponse:
    """Отмена покупателем — только пока заказ `new`."""
    return await op_public_my_order_cancel(
        ShopMyOrderCodePayload(public_code=public_code),
        user=require_context().user,
        di=di,
    )


@router.post("/storefront/{slug}/notify-back", response_model=ShopNotifyBackResponse)
async def notify_back(
    slug: str, payload: ShopNotifyBackRequest, di: Di
) -> ShopNotifyBackResponse:
    """«Сообщить о появлении»: подписка покупателя на недоступный товар."""
    return await op_public_notify_back(
        ShopNotifyBackPayload(slug=slug, product_id=payload.product_id),
        user=require_context().user,
        di=di,
    )


@router.get("/storefront/{slug}/personal", response_model=ShopPersonalResponse)
async def get_personal(slug: str, di: Di) -> ShopPersonalResponse:
    """«Как всегда» и подписки покупателя витрины (customer-сессия)."""
    return await op_public_personal(
        ShopPersonalPayload(slug=slug),
        user=require_context().user,
        di=di,
    )


@router.post("/storefront/{slug}/favorites", response_model=ShopFavoriteResponse)
async def favorite_set(
    slug: str, payload: ShopFavoriteSetRequest, di: Di
) -> ShopFavoriteResponse:
    """Сердечко «в избранное» — идемпотентное состояние (customer-сессия)."""
    return await op_public_favorite_set(
        ShopFavoriteSetPayload(
            slug=slug, product_id=payload.product_id, favorite=payload.favorite
        ),
        user=require_context().user,
        di=di,
    )


@router.post(
    "/storefront/{slug}/orders/{public_code}/feedback",
    response_model=ShopOrderFeedbackResponse,
)
async def feedback_set(
    slug: str, public_code: str, payload: ShopFeedbackSetRequest, di: Di
) -> ShopOrderFeedbackResponse:
    """Оценка выполненного заказа — идемпотентна по заказу (customer-сессия)."""
    return await op_public_feedback_set(
        ShopFeedbackSetPayload(
            slug=slug,
            public_code=public_code,
            rating=payload.rating,
            chips=payload.chips,
            comment=payload.comment,
        ),
        user=require_context().user,
        di=di,
    )


@router.get("/storefront/{slug}/reviews", response_model=ShopReviewsResponse)
async def reviews_list(
    slug: str,
    di: Di,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ShopReviewsResponse:
    """Публичная лента отзывов витрины + агрегат рейтинга (анонимно)."""
    return await op_public_reviews_list(
        ShopReviewsListPayload(slug=slug, limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.get("/storefront/{slug}/geo", response_model=ShopStorefrontGeoResponse)
async def get_storefront_geo(slug: str, di: Di) -> ShopStorefrontGeoResponse:
    """Точка магазина и зона доставки для карты на витрине."""
    return await op_public_storefront_geo(
        ShopStorefrontGeoPayload(slug=slug),
        user=require_context().user,
        di=di,
    )


@router.get("/orders/{public_code}/events", response_model=None)
async def stream_order_events(public_code: str, request: Request, di: Di) -> StreamingResponse:
    """SSE-стрим статусов заказа: fanout хвоста platform:events по коду.

    Публичный код — тот же токен доверия, что и у `GET /orders/{code}`:
    payload события без PII. Клиент при обрыве откатывается на polling.
    """

    async def gen() -> AsyncIterator[str]:
        queue = di.order_events_service.subscribe(public_code)
        try:
            yield f"event: open\ndata: {json.dumps({'public_code': public_code})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            di.order_events_service.unsubscribe(public_code, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# --- Geo-прокси: тайлы и стиль карты на витринных хостах ---

_GEO_PASSTHROUGH_HEADERS = ("range", "if-none-match", "if-modified-since")
_GEO_RESPONSE_HEADERS = (
    "content-type",
    "cache-control",
    "etag",
    "last-modified",
    "accept-ranges",
    "content-range",
    "content-length",
)


@router.api_route("/geo/{path:path}", methods=["GET", "HEAD"], response_model=None)
async def proxy_geo(path: str, request: Request, di: Di) -> Response:
    """Прокси анонимных geo-ассетов (тайлы/стиль/шрифты PMTiles) на хост витрины.

    На витринном хосте `/geo/api/v1/...` физически приходит в shop — ingress
    его не знает; прокси пробрасывает GET/HEAD с Range (PMTiles читается
    кусками) и отдаёт upstream-байты с кэш-заголовками как есть.
    """
    if ".." in path:
        raise_not_found(
            PlatformNotFoundError("Geo asset not found", error_code="geo_asset_not_found")
        )
    base = di.settings.server.get_service_url("geo")
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() in _GEO_PASSTHROUGH_HEADERS
    }
    try:
        async with get_httpx_client(timeout=30.0) as client:
            upstream = await client.request(
                request.method,
                f"{base}/geo/api/v1/{path}",
                params=dict(request.query_params),
                headers=headers,
            )
    except Exception as exc:
        raise WsCommandError(
            "unavailable", "Geo service unavailable", error_code="geo_unavailable"
        ) from exc
    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() in _GEO_RESPONSE_HEADERS
    }
    body = upstream.content
    if path == "tiles/style.json" and upstream.status_code == 200:
        # style.json содержит абсолютные URL апстрима (источник pmtiles,
        # glyphs, sprites) — переписываем базу на хост витрины, чтобы браузер
        # ходил в тот же /geo/... прокси без CORS.
        upstream_base = f"{base}/geo/api/v1".encode()
        public_base = f"{request.url.scheme}://{request.url.netloc}/geo/api/v1".encode()
        body = body.replace(upstream_base, public_base)
        _ = response_headers.pop("content-length", None)
        _ = response_headers.pop("etag", None)
    return Response(
        content=body,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )


# --- PWA: манифест, service worker и иконка витрины ---

_SW_JS = """\
const CACHE = 'shop-shell-v1';
self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  // API и live-стримы — всегда сеть.
  if (url.pathname.includes('/api/') || url.pathname.endsWith('/events')) return;
  // Тайлы карты и статика — cache-first с дозаписью.
  if (url.pathname.includes('/tiles/') || url.pathname.includes('/static/')) {
    e.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const hit = await cache.match(e.request);
        const fetched = fetch(e.request).then((r) => {
          if (r.ok) cache.put(e.request, r.clone());
          return r;
        }).catch(() => hit);
        return hit || fetched;
      })
    );
  }
});
"""


def _manifest_payload(shop: Shop) -> dict[str, object]:
    """Web app manifest витрины: имя и цвета из темы магазина."""
    theme = normalize_shop_theme(shop.theme or {})
    return {
        "name": shop.name,
        "short_name": shop.name[:12] or shop.name,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": theme.get("bg") or "#ffffff",
        "theme_color": theme.get("accent_color") or "#111827",
        "icons": [
            {
                "src": f"/shop/api/v1/public/storefront/{shop.slug}/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
            }
        ],
    }


def _manifest_response(shop: Shop) -> JSONResponse:
    return JSONResponse(
        _manifest_payload(shop),
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _icon_svg(shop: Shop) -> str:
    theme = normalize_shop_theme(shop.theme or {})
    accent = theme.get("accent_color") or "#111827"
    letter = escape((shop.name[:1] or "S").upper())
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        f'<rect width="512" height="512" rx="96" fill="{accent}"/>'
        f'<text x="256" y="330" font-family="system-ui, sans-serif" font-size="280"'
        f' font-weight="700" fill="#ffffff" text-anchor="middle">{letter}</text>'
        "</svg>"
    )


def _sw_response() -> Response:
    return Response(
        content=_SW_JS,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


async def _shop_by_host(request: Request, di: Di) -> Shop:
    shop = await di.storefront_service.resolve_shop_by_host(
        request.headers.get("host", "")
    )
    if shop is None:
        raise WsCommandError(
            "not_found", "Storefront not found", error_code="storefront_not_found"
        )
    return shop


@router.get("/storefront/{slug}/manifest.webmanifest", response_model=None)
async def get_storefront_manifest(slug: str, request: Request, di: Di) -> Response:
    _ = request, di
    shop = await Shop.get_by_slug(slug)
    if shop is None:
        raise_not_found(
            PlatformNotFoundError("Storefront not found", error_code="storefront_not_found")
        )
    return _manifest_response(shop)


@router.get("/storefront/{slug}/sw.js", response_model=None)
async def get_storefront_sw(slug: str, request: Request, di: Di) -> Response:
    """Service worker витрины: кэш тайлов карты и статики, API — в сеть."""
    _ = slug, request, di
    return _sw_response()


@router.get("/storefront/{slug}/icon.svg", response_model=None)
async def get_storefront_icon(slug: str, di: Di) -> Response:
    """SVG-иконка витрины: первая буква названия на акцентном фоне темы."""
    _ = di
    shop = await Shop.get_by_slug(slug)
    if shop is None:
        raise_not_found(
            PlatformNotFoundError("Storefront not found", error_code="storefront_not_found")
        )
    return Response(
        content=_icon_svg(shop),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# Host-резолв для витринных доменов: /sw.js и /manifest.webmanifest на корне
# хоста (service worker scope требует корневого пути).


@router.get("/host/manifest.webmanifest", response_model=None)
async def get_host_manifest(request: Request, di: Di) -> Response:
    return _manifest_response(await _shop_by_host(request, di))


@router.get("/host/sw.js", response_model=None)
async def get_host_sw(request: Request, di: Di) -> Response:
    _ = await _shop_by_host(request, di)
    return _sw_response()


@router.get("/host/icon.svg", response_model=None)
async def get_host_icon(request: Request, di: Di) -> Response:
    return Response(
        content=_icon_svg(await _shop_by_host(request, di)),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/storefront/{slug}/qr.svg", response_model=None)
async def get_storefront_qr(slug: str, request: Request, di: Di) -> Response:
    """QR-код витрины (SVG): владелец печатает его на столах и витрине.

    Протокольный хендлер — байты наружу; ETag стабилен на slug+host.
    """
    _ = await _snapshot_or_404(di, slug)
    url = f"https://{slug}.{di.settings.storefront_domain_suffix}"
    etag = f'W/"shop-qr-{hashlib.sha256(url.encode()).hexdigest()[:16]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", border=2, dark="#181310")
    return Response(
        content=buf.getvalue(),
        media_type="image/svg+xml",
        headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
    )


@router.get("/storefront/{slug}/tables/{table_id}/qr.svg", response_model=None)
async def get_table_qr(slug: str, table_id: str, request: Request, di: Di) -> Response:
    """QR стола зала (SVG): кодирует витрину с ``?table=<id>`` — гость
    сканирует карточку на столе и заказывает «в заведении» без ввода
    номера. 404 при несуществующем столе."""
    snapshot = await _snapshot_or_404(di, slug)
    tables = snapshot.get("tables")
    if not isinstance(tables, list) or not any(
        isinstance(t, dict) and t.get("id") == table_id for t in tables
    ):
        raise WsCommandError("not_found", "Table not found", error_code="table_not_found")
    url = f"https://{slug}.{di.settings.storefront_domain_suffix}?table={table_id}"
    etag = f'W/"shop-qr-{hashlib.sha256(url.encode()).hexdigest()[:16]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", border=2, dark="#181310")
    return Response(
        content=buf.getvalue(),
        media_type="image/svg+xml",
        headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
    )


@router.post("/telegram/webhook/{shop_id}", response_model=None)
async def telegram_webhook(shop_id: str, request: Request, di: Di) -> Response:
    """Входящий update бота магазина: wire-спек Telegram, не op_*.

    Секрет в заголовке ``X-Telegram-Bot-Api-Secret-Token`` проверяется
    внутри сервиса до любой работы; невалидный update — 404.
    """
    try:
        update = parse_json_object(await request.body(), "Telegram update")
    except ValueError as exc:
        raise WsCommandError(
            "bad_request", "Invalid update", error_code="telegram_update_invalid"
        ) from exc
    try:
        await di.notification_service.handle_telegram_update(
            shop_id,
            request.headers.get("x-telegram-bot-api-secret-token"),
            update,
        )
    except PlatformNotFoundError as exc:
        raise WsCommandError(
            "not_found", "Webhook not found", error_code="telegram_webhook_not_found"
        ) from exc
    return Response(status_code=200)


@router.get("/robots.txt", response_model=None)
async def get_robots(request: Request) -> Response:
    """robots.txt витрин и агрегатора: индексация разрешена, sitemap на хосте."""
    host = request.headers.get("host", "").split(":")[0] or "localhost"
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /shop/api/\n"
        f"Sitemap: https://{host}/sitemap.xml\n"
    )
    return Response(
        content=body,
        media_type="text/plain",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/sitemap.xml", response_model=None)
async def get_sitemap(di: Di) -> Response:
    """Sitemap агрегатора: опубликованные витрины для поисковых роботов."""
    shops = await di.aggregate_service.list_shops()
    suffix = di.settings.storefront_domain_suffix
    urls = "".join(
        f"<url><loc>https://{s.slug}.{suffix}</loc>"
        + "<changefreq>hourly</changefreq><priority>0.8</priority></url>"
        for s in shops
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + urls
        + "</urlset>"
    )
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


# --- Агрегатор ---


@router.get("/market", response_model=None)
async def get_market_page(request: Request, di: Di) -> HTMLResponse:
    """Публичная страница агрегатора: все published-витрины + поиск по каталогу."""
    shops = await di.aggregate_service.list_shops()
    suffix = di.settings.storefront_domain_suffix
    snapshot: JsonObject = {
        "shops": [
            {
                "slug": s.slug,
                "name": s.name,
                "kind": s.kind.value,
                "city": s.city,
                "description": s.description,
                "logo_file_id": s.logo_file_id,
                "cover_file_id": s.cover_file_id,
                "url": f"https://{s.slug}.{suffix}",
            }
            for s in shops
        ],
    }
    brand = resolve_brand_or_primary(request.headers.get("host"))
    canonical = f"https://{di.settings.aggregator_host}"
    return HTMLResponse(
        content=market_html(snapshot, brand=brand.platform_name, canonical_url=canonical),
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get("/aggregate/shops")
async def list_aggregate_shops_by_score_desc(
    di: Di, city: str | None = None, lat: float | None = None, lng: float | None = None
) -> dict[str, object]:
    shops = await di.aggregate_service.list_shops(city=city)
    point = (lat, lng) if lat is not None and lng is not None else None
    items: list[dict[str, object]] = []
    for s in shops:
        coverage = "unknown"
        if point is not None:
            covered = zone_covers_point(s.delivery_zone, point[0], point[1])
            coverage = "yes" if covered else ("no" if covered is False else "unknown")
        items.append(
            {
                "slug": s.slug,
                "name": s.name,
                "kind": s.kind.value,
                "city": s.city,
                "logo_file_id": s.logo_file_id,
                "cover_file_id": s.cover_file_id,
                "description": s.description,
                "delivery_enabled": s.delivery_enabled,
                "delivery_coverage": coverage,
            }
        )
    if point is not None:
        items.sort(key=lambda i: {"yes": 0, "unknown": 1, "no": 2}[str(i["delivery_coverage"])])
    return {"items": items}


@router.get("/aggregate/search", response_model=None)
async def search_aggregate(
    q: str,
    di: Di,
    kind: str | None = None,
    city: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> OffsetPage[dict[str, object]]:
    return await di.aggregate_service.search_products(
        q, kind=kind, city=city, limit=limit, offset=offset
    )


@router.get("/resolve")
async def resolve_host(request: Request, di: Di) -> dict[str, object]:
    """Host → slug витрины: внутренний резолв для shell/прокси слоя."""
    host = request.headers.get("host", "")
    shop = await di.storefront_service.resolve_shop_by_host(host)
    if shop is None:
        raise WsCommandError("not_found", "Storefront not found", error_code="storefront_not_found")
    return {"slug": shop.slug, "name": shop.name}


@router.get("/host", response_model=None)
async def get_host_storefront_page(request: Request, di: Di) -> HTMLResponse:
    """Витрина по Host запроса: slug-поддомен, кастомный домен или поддомен компании.

    Единая точка резолва для HostMiddleware и прокси frontend — вся логика
    «какой магазин показать на этом хосте» живёт в ``resolve_shop_by_host``.
    """
    host = request.headers.get("host", "")
    shop = await di.storefront_service.resolve_shop_by_host(host)
    if shop is None:
        raise WsCommandError("not_found", "Storefront not found", error_code="storefront_not_found")
    return await get_storefront_page(shop.slug, request, di)
