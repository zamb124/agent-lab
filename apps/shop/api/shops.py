"""Админские маршруты shop: тонкая REST-обвязка тех же `op_*`."""

from __future__ import annotations

from fastapi import APIRouter, Query

from apps.shop.di import Di
from apps.shop.models import ShopDomain
from apps.shop.models.api import (
    ShopCategoryCreateRequest,
    ShopCategoryResponse,
    ShopCategoryUpdateRequest,
    ShopCreateRequest,
    ShopOrderResponse,
    ShopProductCreateRequest,
    ShopProductResponse,
    ShopProductUpdateRequest,
    ShopResponse,
    ShopUpdateRequest,
)
from apps.shop.models.enums import ShopOrderStatus
from apps.shop.realtime.operations import (
    ShopCategoryCreatePayload,
    ShopCategoryIdPayload,
    ShopCategoryUpdatePayload,
    ShopDomainAddPayload,
    ShopDomainIdPayload,
    ShopIdPayload,
    ShopOrderIdPayload,
    ShopOrderListPayload,
    ShopOrderSetStatusPayload,
    ShopProductCreatePayload,
    ShopProductIdPayload,
    ShopProductUpdatePayload,
    ShopUpdatePayload,
    op_categories_create,
    op_categories_list,
    op_categories_remove,
    op_categories_update,
    op_domains_add,
    op_domains_provision,
    op_domains_remove,
    op_orders_get,
    op_orders_list,
    op_orders_set_status,
    op_products_create,
    op_products_list,
    op_products_remove,
    op_products_update,
    op_shops_create,
    op_shops_get,
    op_shops_list,
    op_shops_publish,
    op_shops_remove,
    op_shops_suspend,
    op_shops_update,
)
from core.context import require_context
from core.pagination import ListResponse, OffsetPage
from core.websocket import EmptyPayload

router = APIRouter(prefix="/shops", tags=["shop-admin"])


@router.get("", response_model=ListResponse[ShopResponse])
async def list_shops(di: Di) -> ListResponse[ShopResponse]:
    return await op_shops_list(EmptyPayload(), user=require_context().user, di=di)


@router.post("", response_model=ShopResponse)
async def create_shop(payload: ShopCreateRequest, di: Di) -> ShopResponse:
    return await op_shops_create(payload, user=require_context().user, di=di)


@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(shop_id: str, di: Di) -> ShopResponse:
    return await op_shops_get(
        ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di
    )


@router.patch("/{shop_id}", response_model=ShopResponse)
async def update_shop(shop_id: str, payload: ShopUpdateRequest, di: Di) -> ShopResponse:
    return await op_shops_update(
        ShopUpdatePayload(shop_id=shop_id, **payload.model_dump(exclude_unset=True)),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/publish", response_model=ShopResponse)
async def publish_shop(shop_id: str, di: Di) -> ShopResponse:
    return await op_shops_publish(
        ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di
    )


@router.post("/{shop_id}/suspend", response_model=ShopResponse)
async def suspend_shop(shop_id: str, di: Di) -> ShopResponse:
    return await op_shops_suspend(
        ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di
    )


@router.delete("/{shop_id}", response_model=EmptyPayload)
async def remove_shop(shop_id: str, di: Di) -> EmptyPayload:
    return await op_shops_remove(
        ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di
    )


# --- Категории ---


@router.get("/{shop_id}/categories", response_model=ListResponse[ShopCategoryResponse])
async def list_categories(shop_id: str, di: Di) -> ListResponse[ShopCategoryResponse]:
    return await op_categories_list(
        ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di
    )


@router.post("/{shop_id}/categories", response_model=ShopCategoryResponse)
async def create_category(
    shop_id: str, payload: ShopCategoryCreateRequest, di: Di
) -> ShopCategoryResponse:
    return await op_categories_create(
        ShopCategoryCreatePayload(shop_id=shop_id, name=payload.name),
        user=require_context().user,
        di=di,
    )


@router.patch("/{shop_id}/categories/{category_id}", response_model=ShopCategoryResponse)
async def update_category(
    shop_id: str, category_id: str, payload: ShopCategoryUpdateRequest, di: Di
) -> ShopCategoryResponse:
    return await op_categories_update(
        ShopCategoryUpdatePayload(
            shop_id=shop_id,
            shop_category_id=category_id,
            **payload.model_dump(exclude_unset=True),
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/categories/{category_id}", response_model=EmptyPayload)
async def remove_category(shop_id: str, category_id: str, di: Di) -> EmptyPayload:
    return await op_categories_remove(
        ShopCategoryIdPayload(shop_id=shop_id, shop_category_id=category_id),
        user=require_context().user,
        di=di,
    )


# --- Товары ---


@router.get("/{shop_id}/products", response_model=ListResponse[ShopProductResponse])
async def list_products(shop_id: str, di: Di) -> ListResponse[ShopProductResponse]:
    return await op_products_list(
        ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di
    )


@router.post("/{shop_id}/products", response_model=ShopProductResponse)
async def create_product(
    shop_id: str, payload: ShopProductCreateRequest, di: Di
) -> ShopProductResponse:
    return await op_products_create(
        ShopProductCreatePayload(
            shop_id=shop_id, **payload.model_dump(exclude_unset=True)
        ),
        user=require_context().user,
        di=di,
    )


@router.patch("/{shop_id}/products/{product_id}", response_model=ShopProductResponse)
async def update_product(
    shop_id: str, product_id: str, payload: ShopProductUpdateRequest, di: Di
) -> ShopProductResponse:
    return await op_products_update(
        ShopProductUpdatePayload(
            shop_id=shop_id,
            shop_product_id=product_id,
            **payload.model_dump(exclude_unset=True),
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/products/{product_id}", response_model=EmptyPayload)
async def remove_product(shop_id: str, product_id: str, di: Di) -> EmptyPayload:
    return await op_products_remove(
        ShopProductIdPayload(shop_id=shop_id, shop_product_id=product_id),
        user=require_context().user,
        di=di,
    )


# --- Заказы ---


@router.get("/{shop_id}/orders", response_model=OffsetPage[ShopOrderResponse])
async def list_orders(
    shop_id: str,
    di: Di,
    status: ShopOrderStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> OffsetPage[ShopOrderResponse]:
    return await op_orders_list(
        ShopOrderListPayload(shop_id=shop_id, status=status, limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.get("/{shop_id}/orders/{order_id}", response_model=ShopOrderResponse)
async def get_order(shop_id: str, order_id: str, di: Di) -> ShopOrderResponse:
    return await op_orders_get(
        ShopOrderIdPayload(shop_id=shop_id, shop_order_id=order_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/orders/{order_id}/status", response_model=ShopOrderResponse)
async def set_order_status(
    shop_id: str, order_id: str, status: ShopOrderStatus, di: Di
) -> ShopOrderResponse:
    return await op_orders_set_status(
        ShopOrderSetStatusPayload(
            shop_id=shop_id, shop_order_id=order_id, status=status
        ),
        user=require_context().user,
        di=di,
    )


# --- Домены ---


@router.post("/{shop_id}/domains", response_model=ShopDomain)
async def add_domain(shop_id: str, domain: str, di: Di) -> ShopDomain:
    return await op_domains_add(
        ShopDomainAddPayload(shop_id=shop_id, domain=domain),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/domains/{domain_id}", response_model=EmptyPayload)
async def remove_domain(shop_id: str, domain_id: str, di: Di) -> EmptyPayload:
    return await op_domains_remove(
        ShopDomainIdPayload(shop_id=shop_id, shop_domain_id=domain_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/domains/{domain_id}/provision", response_model=ShopDomain)
async def provision_domain(shop_id: str, domain_id: str, di: Di) -> ShopDomain:
    return await op_domains_provision(
        ShopDomainIdPayload(shop_id=shop_id, shop_domain_id=domain_id),
        user=require_context().user,
        di=di,
    )
