"""Публичные анонимные маршруты shop: витрина, заказ, агрегатор.

Авторизации здесь нет: витрина и поиск доступны покупателю без аккаунта.
Read-path идёт в Redis-снапшот с ETag/304 — PostgreSQL не трогается
на повторных просмотрах меню.
"""

from __future__ import annotations

import hashlib
import io

import segno
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from apps.shop.api.storefront_shell import storefront_html
from apps.shop.di import Di
from apps.shop.models.api import (
    ShopCartPriceRequest,
    ShopCartPriceResponse,
    ShopOrderCreatedResponse,
    ShopOrderCreateRequest,
    ShopOrderStatusResponse,
)
from apps.shop.realtime.operations import (
    ShopCartPricePayload,
    ShopOrderCreatePayload,
    ShopPublicOrderStatusPayload,
    op_public_cart_price,
    op_public_order_create,
    op_public_order_status,
)
from core.context import require_context
from core.errors.boundary import PlatformNotFoundError
from core.pagination import OffsetPage
from core.types import JsonObject, parse_json_object
from core.websocket import WsCommandError

router = APIRouter(prefix="/public", tags=["shop-public"])


async def _snapshot_or_404(di: Di, slug: str) -> JsonObject:
    snapshot = await di.storefront_service.get_snapshot(slug)
    if snapshot is None:
        raise WsCommandError("not_found", "Storefront not found", error_code="storefront_not_found")
    return snapshot


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
    """SSR-lite HTML витрины: снапшот inline, меню и корзина — клиентский JS."""
    snapshot = await _snapshot_or_404(di, slug)
    etag = di.storefront_service.snapshot_etag(snapshot)
    if request.headers.get("if-none-match") == etag:
        return HTMLResponse(status_code=304, headers={"ETag": etag})
    return HTMLResponse(
        content=storefront_html(snapshot),
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


@router.get("/aggregate/shops")
async def list_aggregate_shops(di: Di, city: str | None = None) -> dict[str, object]:
    shops = await di.aggregate_service.list_shops(city=city)
    return {
        "items": [
            {
                "slug": s.slug,
                "name": s.name,
                "kind": s.kind.value,
                "city": s.city,
                "logo_file_id": s.logo_file_id,
                "description": s.description,
            }
            for s in shops
        ]
    }


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
