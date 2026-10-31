"""Админские маршруты shop: тонкая REST-обвязка тех же `op_*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.shop.di import Di
from apps.shop.models import ShopDomain
from apps.shop.models.api import (
    ShopAiBriefRequest,
    ShopAiDescribeRequest,
    ShopAiEnhancePhotoRequest,
    ShopAiParseMenuRequest,
    ShopAiParseMenuResponse,
    ShopAiSuggestOptionsRequest,
    ShopAiSuggestOptionsResponse,
    ShopBadgeIconsResponse,
    ShopCategoriesReorderRequest,
    ShopCategoryCreateRequest,
    ShopCategoryResponse,
    ShopCategoryUpdateRequest,
    ShopCreateRequest,
    ShopModifierGroupCreateRequest,
    ShopModifierGroupResponse,
    ShopModifierGroupsResponse,
    ShopModifierGroupUpdateRequest,
    ShopModifierOptionCreateRequest,
    ShopModifierOptionResponse,
    ShopModifierOptionUpdateRequest,
    ShopOrderResponse,
    ShopProductCreateRequest,
    ShopProductModifierGroupAttachRequest,
    ShopProductResponse,
    ShopProductsImportRequest,
    ShopProductsImportResponse,
    ShopProductsReorderRequest,
    ShopProductUpdateRequest,
    ShopPromoCreateRequest,
    ShopPromoResponse,
    ShopPromosResponse,
    ShopPromoUpdateRequest,
    ShopResponse,
    ShopTelegramConnectRequest,
    ShopUpdateRequest,
)
from apps.shop.models.enums import ShopOrderStatus
from apps.shop.realtime.operations import (
    ShopAiBatchResponse,
    ShopAiDescribeBatchPayload,
    ShopAiDescribePayload,
    ShopAiEnhancePhotoPayload,
    ShopAiFileResponse,
    ShopAiGeneratePhotoPayload,
    ShopAiParseMenuPayload,
    ShopAiShopPayload,
    ShopAiSuggestOptionsPayload,
    ShopAiTextResponse,
    ShopCategoriesReorderPayload,
    ShopCategoryCreatePayload,
    ShopCategoryIdPayload,
    ShopCategoryUpdatePayload,
    ShopDomainAddPayload,
    ShopDomainIdPayload,
    ShopIdPayload,
    ShopModifierGroupCreatePayload,
    ShopModifierGroupIdPayload,
    ShopModifierGroupUpdatePayload,
    ShopModifierOptionCreatePayload,
    ShopModifierOptionIdPayload,
    ShopModifierOptionUpdatePayload,
    ShopOrderIdPayload,
    ShopOrderListPayload,
    ShopOrderSetStatusPayload,
    ShopProductCreatePayload,
    ShopProductIdPayload,
    ShopProductModifierAttachPayload,
    ShopProductModifierDetachPayload,
    ShopProductsImportPayload,
    ShopProductsReorderPayload,
    ShopProductUpdatePayload,
    ShopPromoCreatePayload,
    ShopPromoIdPayload,
    ShopPromoUpdatePayload,
    ShopTelegramConnectPayload,
    ShopUpdatePayload,
    op_ai_autofill,
    op_ai_describe_batch,
    op_ai_describe_product,
    op_ai_describe_shop,
    op_ai_enhance_photo,
    op_ai_generate_cover,
    op_ai_generate_logo,
    op_ai_generate_photo,
    op_ai_parse_menu,
    op_ai_suggest_options,
    op_badge_icons_list,
    op_categories_create,
    op_categories_list,
    op_categories_remove,
    op_categories_reorder,
    op_categories_update,
    op_domains_add,
    op_domains_provision,
    op_domains_remove,
    op_modifier_groups_create,
    op_modifier_groups_list,
    op_modifier_groups_remove,
    op_modifier_groups_update,
    op_modifier_options_create,
    op_modifier_options_remove,
    op_modifier_options_update,
    op_orders_get,
    op_orders_list,
    op_orders_set_status,
    op_products_create,
    op_products_import,
    op_products_list,
    op_products_modifier_attach,
    op_products_modifier_detach,
    op_products_remove,
    op_products_reorder,
    op_products_update,
    op_promos_create,
    op_promos_list,
    op_promos_remove,
    op_promos_update,
    op_shops_create,
    op_shops_get,
    op_shops_list,
    op_shops_publish,
    op_shops_remove,
    op_shops_suspend,
    op_shops_update,
    op_telegram_connect,
    op_telegram_disconnect,
)
from core.context import require_context
from core.pagination import ListResponse, OffsetPage
from core.websocket import EmptyPayload

router = APIRouter(prefix="/shops", tags=["shop-admin"])


@router.get("", response_model=ListResponse[ShopResponse])
async def list_shops(di: Di) -> ListResponse[ShopResponse]:
    return await op_shops_list(EmptyPayload(), user=require_context().user, di=di)


@router.get("/badge-icons", response_model=ShopBadgeIconsResponse)
async def list_badge_icons(di: Di) -> ShopBadgeIconsResponse:
    return await op_badge_icons_list(EmptyPayload(), user=require_context().user, di=di)


@router.post("", response_model=ShopResponse)
async def create_shop(payload: ShopCreateRequest, di: Di) -> ShopResponse:
    return await op_shops_create(payload, user=require_context().user, di=di)


@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(shop_id: str, di: Di) -> ShopResponse:
    return await op_shops_get(ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di)


@router.patch("/{shop_id}", response_model=ShopResponse)
async def update_shop(shop_id: str, payload: ShopUpdateRequest, di: Di) -> ShopResponse:
    return await op_shops_update(
        ShopUpdatePayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
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
    return await op_shops_remove(ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di)


@router.post("/{shop_id}/telegram/connect", response_model=ShopResponse)
async def telegram_connect(
    shop_id: str, payload: ShopTelegramConnectRequest, di: Di
) -> ShopResponse:
    return await op_telegram_connect(
        ShopTelegramConnectPayload(shop_id=shop_id, bot_token=payload.bot_token),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/telegram/disconnect", response_model=ShopResponse)
async def telegram_disconnect(shop_id: str, di: Di) -> ShopResponse:
    return await op_telegram_disconnect(
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
        ShopCategoryUpdatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_category_id": category_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/categories/reorder", response_model=EmptyPayload)
async def reorder_categories(
    shop_id: str, payload: ShopCategoriesReorderRequest, di: Di
) -> EmptyPayload:
    return await op_categories_reorder(
        ShopCategoriesReorderPayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
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
        ShopProductCreatePayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/products/import", response_model=ShopProductsImportResponse)
async def import_products(
    shop_id: str, payload: ShopProductsImportRequest, di: Di
) -> ShopProductsImportResponse:
    return await op_products_import(
        ShopProductsImportPayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/products/reorder", response_model=EmptyPayload)
async def reorder_products(
    shop_id: str, payload: ShopProductsReorderRequest, di: Di
) -> EmptyPayload:
    return await op_products_reorder(
        ShopProductsReorderPayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.patch("/{shop_id}/products/{product_id}", response_model=ShopProductResponse)
async def update_product(
    shop_id: str, product_id: str, payload: ShopProductUpdateRequest, di: Di
) -> ShopProductResponse:
    return await op_products_update(
        ShopProductUpdatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_product_id": product_id,
                **payload.model_dump(exclude_unset=True),
            }
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
    status: Annotated[ShopOrderStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
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
        ShopOrderSetStatusPayload(shop_id=shop_id, shop_order_id=order_id, status=status),
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


# --- AI ---


@router.post("/{shop_id}/ai/describe", response_model=ShopAiTextResponse)
async def ai_describe(shop_id: str, body: ShopAiDescribeRequest, di: Di) -> ShopAiTextResponse:
    return await op_ai_describe_product(
        ShopAiDescribePayload(
            shop_id=shop_id,
            name=body.name,
            category_name=body.category_name,
            photo_file_id=body.photo_file_id,
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/describe-all", response_model=ShopAiBatchResponse)
async def ai_describe_all(shop_id: str, di: Di) -> ShopAiBatchResponse:
    return await op_ai_describe_batch(
        ShopAiDescribeBatchPayload(shop_id=shop_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/enhance-photo", response_model=ShopAiFileResponse)
async def ai_enhance_photo(
    shop_id: str, body: ShopAiEnhancePhotoRequest, di: Di
) -> ShopAiFileResponse:
    return await op_ai_enhance_photo(
        ShopAiEnhancePhotoPayload(shop_id=shop_id, file_id=body.file_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/generate-photo", response_model=ShopAiFileResponse)
async def ai_generate_photo(shop_id: str, body: ShopAiBriefRequest, di: Di) -> ShopAiFileResponse:
    return await op_ai_generate_photo(
        ShopAiGeneratePhotoPayload(shop_id=shop_id, name=body.name, description=body.description),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/describe-shop", response_model=ShopAiTextResponse)
async def ai_describe_shop(shop_id: str, body: ShopAiBriefRequest, di: Di) -> ShopAiTextResponse:
    return await op_ai_describe_shop(
        ShopAiShopPayload(shop_id=shop_id, name=body.name, description=body.description),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/generate-cover", response_model=ShopAiFileResponse)
async def ai_generate_cover(shop_id: str, body: ShopAiBriefRequest, di: Di) -> ShopAiFileResponse:
    return await op_ai_generate_cover(
        ShopAiShopPayload(shop_id=shop_id, name=body.name, description=body.description),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/generate-logo", response_model=ShopAiFileResponse)
async def ai_generate_logo(shop_id: str, body: ShopAiBriefRequest, di: Di) -> ShopAiFileResponse:
    return await op_ai_generate_logo(
        ShopAiShopPayload(shop_id=shop_id, name=body.name, description=body.description),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/autofill", response_model=ShopResponse)
async def ai_autofill(shop_id: str, di: Di) -> ShopResponse:
    return await op_ai_autofill(ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di)


@router.post("/{shop_id}/ai/parse-menu", response_model=ShopAiParseMenuResponse)
async def ai_parse_menu(
    shop_id: str, body: ShopAiParseMenuRequest, di: Di
) -> ShopAiParseMenuResponse:
    return await op_ai_parse_menu(
        ShopAiParseMenuPayload(shop_id=shop_id, text=body.text),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/suggest-options", response_model=ShopAiSuggestOptionsResponse)
async def ai_suggest_options(
    shop_id: str, body: ShopAiSuggestOptionsRequest, di: Di
) -> ShopAiSuggestOptionsResponse:
    return await op_ai_suggest_options(
        ShopAiSuggestOptionsPayload(
            shop_id=shop_id,
            product_name=body.product_name,
            group_name=body.group_name,
        ),
        user=require_context().user,
        di=di,
    )


# --- Модификаторы ---


@router.get("/{shop_id}/modifier-groups", response_model=ShopModifierGroupsResponse)
async def list_modifier_groups_by_sort_asc(shop_id: str, di: Di) -> ShopModifierGroupsResponse:
    return await op_modifier_groups_list(
        ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di
    )


@router.post("/{shop_id}/modifier-groups", response_model=ShopModifierGroupResponse)
async def create_modifier_group(
    shop_id: str, payload: ShopModifierGroupCreateRequest, di: Di
) -> ShopModifierGroupResponse:
    return await op_modifier_groups_create(
        ShopModifierGroupCreatePayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.patch(
    "/{shop_id}/modifier-groups/{group_id}",
    response_model=ShopModifierGroupResponse,
)
async def update_modifier_group(
    shop_id: str, group_id: str, payload: ShopModifierGroupUpdateRequest, di: Di
) -> ShopModifierGroupResponse:
    return await op_modifier_groups_update(
        ShopModifierGroupUpdatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_modifier_group_id": group_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/modifier-groups/{group_id}", response_model=EmptyPayload)
async def remove_modifier_group(shop_id: str, group_id: str, di: Di) -> EmptyPayload:
    return await op_modifier_groups_remove(
        ShopModifierGroupIdPayload(shop_id=shop_id, shop_modifier_group_id=group_id),
        user=require_context().user,
        di=di,
    )


@router.post(
    "/{shop_id}/modifier-groups/{group_id}/options",
    response_model=ShopModifierOptionResponse,
)
async def create_modifier_option(
    shop_id: str, group_id: str, payload: ShopModifierOptionCreateRequest, di: Di
) -> ShopModifierOptionResponse:
    return await op_modifier_options_create(
        ShopModifierOptionCreatePayload.model_validate(
            {
                "shop_id": shop_id,
                "group_id": group_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.patch(
    "/{shop_id}/modifier-options/{option_id}",
    response_model=ShopModifierOptionResponse,
)
async def update_modifier_option(
    shop_id: str, option_id: str, payload: ShopModifierOptionUpdateRequest, di: Di
) -> ShopModifierOptionResponse:
    return await op_modifier_options_update(
        ShopModifierOptionUpdatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_modifier_option_id": option_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/modifier-options/{option_id}", response_model=EmptyPayload)
async def remove_modifier_option(shop_id: str, option_id: str, di: Di) -> EmptyPayload:
    return await op_modifier_options_remove(
        ShopModifierOptionIdPayload(shop_id=shop_id, shop_modifier_option_id=option_id),
        user=require_context().user,
        di=di,
    )


@router.post(
    "/{shop_id}/products/{product_id}/modifier-groups/{group_id}",
    response_model=EmptyPayload,
)
async def attach_modifier_group(
    shop_id: str,
    product_id: str,
    group_id: str,
    payload: ShopProductModifierGroupAttachRequest,
    di: Di,
) -> EmptyPayload:
    return await op_products_modifier_attach(
        ShopProductModifierAttachPayload(
            shop_id=shop_id,
            product_id=product_id,
            group_id=group_id,
            min_selected=payload.min_selected,
            max_selected=payload.max_selected,
        ),
        user=require_context().user,
        di=di,
    )


@router.delete(
    "/{shop_id}/products/{product_id}/modifier-groups/{group_id}",
    response_model=EmptyPayload,
)
async def detach_modifier_group(
    shop_id: str, product_id: str, group_id: str, di: Di
) -> EmptyPayload:
    return await op_products_modifier_detach(
        ShopProductModifierDetachPayload(shop_id=shop_id, product_id=product_id, group_id=group_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{shop_id}/promos", response_model=ShopPromosResponse)
async def list_promos(shop_id: str, di: Di) -> ShopPromosResponse:
    return await op_promos_list(ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di)


@router.post("/{shop_id}/promos", response_model=ShopPromoResponse)
async def create_promo(shop_id: str, payload: ShopPromoCreateRequest, di: Di) -> ShopPromoResponse:
    return await op_promos_create(
        ShopPromoCreatePayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.patch("/{shop_id}/promos/{promo_id}", response_model=ShopPromoResponse)
async def update_promo(
    shop_id: str, promo_id: str, payload: ShopPromoUpdateRequest, di: Di
) -> ShopPromoResponse:
    return await op_promos_update(
        ShopPromoUpdatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_promo_id": promo_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/promos/{promo_id}", response_model=EmptyPayload)
async def remove_promo(shop_id: str, promo_id: str, di: Di) -> EmptyPayload:
    return await op_promos_remove(
        ShopPromoIdPayload(shop_id=shop_id, shop_promo_id=promo_id),
        user=require_context().user,
        di=di,
    )
