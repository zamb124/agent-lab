"""Публичные анонимные маршруты shop: витрина, заказ, агрегатор.

Авторизации здесь нет: витрина и поиск доступны покупателю без аккаунта.
Read-path идёт в Redis-снапшот с ETag/304 — PostgreSQL не трогается
на повторных просмотрах меню.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from apps.shop.api.storefront_shell import storefront_html
from apps.shop.di import Di
from apps.shop.models.api import (
    ShopOrderCreatedResponse,
    ShopOrderStatusResponse,
)
from apps.shop.realtime.operations import (
    ShopOrderCreatePayload,
    ShopPublicOrderStatusPayload,
    op_public_order_create,
    op_public_order_status,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.websocket import WsCommandError

router = APIRouter(prefix="/public", tags=["shop-public"])


async def _snapshot_or_404(di: Di, slug: str) -> dict[str, object]:
    snapshot = await di.storefront_service.get_snapshot(slug)
    if snapshot is None:
        raise WsCommandError(
            "not_found", "Storefront not found", error_code="storefront_not_found"
        )
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
    slug: str, payload: ShopOrderCreatePayload, di: Di
) -> ShopOrderCreatedResponse:
    """Приём заказа: тот же `op_*`, что и у WS-команды."""
    payload.slug = slug
    return await op_public_order_create(payload, user=require_context().user, di=di)


@router.get("/orders/{public_code}", response_model=ShopOrderStatusResponse)
async def get_order_status(public_code: str, di: Di) -> ShopOrderStatusResponse:
    return await op_public_order_status(
        ShopPublicOrderStatusPayload(public_code=public_code),
        user=require_context().user,
        di=di,
    )


# --- Агрегатор ---


@router.get("/aggregate/shops")
async def list_aggregate_shops(
    di: Di, city: str | None = None
) -> dict[str, object]:
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
        raise WsCommandError(
            "not_found", "Storefront not found", error_code="storefront_not_found"
        )
    return {"slug": shop.slug, "name": shop.name}
