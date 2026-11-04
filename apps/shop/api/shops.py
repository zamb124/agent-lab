"""Админские маршруты shop: тонкая REST-обвязка тех же `op_*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.shop.di import Di
from apps.shop.models import ShopDomain, ShopMenuSection
from apps.shop.models.api import (
    ShopAiBriefRequest,
    ShopAiDescribeRequest,
    ShopAiEnhancePhotoRequest,
    ShopAiSuggestOptionsRequest,
    ShopAiSuggestOptionsResponse,
    ShopBadgeIconsResponse,
    ShopCreateRequest,
    ShopMenuCreateRequest,
    ShopMenuItemAddRequest,
    ShopMenuItemMoveRequest,
    ShopMenuItemResponse,
    ShopMenuItemsReorderRequest,
    ShopMenuItemUpdateRequest,
    ShopMenuResponse,
    ShopMenuSectionCreateRequest,
    ShopMenuSectionsReorderRequest,
    ShopMenuSectionUpdateRequest,
    ShopMenuSetStatusRequest,
    ShopMenusReorderRequest,
    ShopMenuUpdateRequest,
    ShopModifierGroupCreateRequest,
    ShopModifierGroupResponse,
    ShopModifierGroupsResponse,
    ShopModifierGroupUpdateRequest,
    ShopModifierOptionCreateRequest,
    ShopModifierOptionResponse,
    ShopModifierOptionUpdateRequest,
    ShopOrderResponse,
    ShopProductCreateRequest,
    ShopProductMergeRequest,
    ShopProductModifierGroupAttachRequest,
    ShopProductResponse,
    ShopProductSimilarResponse,
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
    ShopAiDescribePayload,
    ShopAiEnhancePhotoPayload,
    ShopAiFileResponse,
    ShopAiGeneratePhotoPayload,
    ShopAiShopPayload,
    ShopAiSuggestOptionsPayload,
    ShopAiTextResponse,
    ShopDomainAddPayload,
    ShopDomainIdPayload,
    ShopIdPayload,
    ShopMenuCreatePayload,
    ShopMenuIdPayload,
    ShopMenuItemAddPayload,
    ShopMenuItemIdPayload,
    ShopMenuItemMovePayload,
    ShopMenuItemsReorderPayload,
    ShopMenuItemUpdatePayload,
    ShopMenuSectionCreatePayload,
    ShopMenuSectionIdPayload,
    ShopMenuSectionsReorderPayload,
    ShopMenuSectionUpdatePayload,
    ShopMenuSetStatusPayload,
    ShopMenusReorderPayload,
    ShopMenuUpdatePayload,
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
    ShopProductMergePayload,
    ShopProductModifierAttachPayload,
    ShopProductModifierDetachPayload,
    ShopProductsReorderPayload,
    ShopProductUpdatePayload,
    ShopPromoCreatePayload,
    ShopPromoIdPayload,
    ShopPromoUpdatePayload,
    ShopTelegramConnectPayload,
    ShopUpdatePayload,
    op_ai_autofill,
    op_ai_describe_product,
    op_ai_describe_shop,
    op_ai_enhance_photo,
    op_ai_generate_cover,
    op_ai_generate_logo,
    op_ai_generate_photo,
    op_ai_suggest_options,
    op_badge_icons_list,
    op_domains_add,
    op_domains_provision,
    op_domains_remove,
    op_menu_items_add,
    op_menu_items_move,
    op_menu_items_remove,
    op_menu_items_reorder,
    op_menu_items_update,
    op_menu_sections_create,
    op_menu_sections_remove,
    op_menu_sections_reorder,
    op_menu_sections_update,
    op_menus_create,
    op_menus_list,
    op_menus_remove,
    op_menus_reorder,
    op_menus_set_status,
    op_menus_update,
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
    op_products_dismiss_similar,
    op_products_list,
    op_products_merge,
    op_products_modifier_attach,
    op_products_modifier_detach,
    op_products_remove,
    op_products_reorder,
    op_products_similar_list,
    op_products_update,
    op_products_verify,
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


@router.post("/{shop_id}/products/{product_id}/verify", response_model=ShopProductResponse)
async def verify_product(shop_id: str, product_id: str, di: Di) -> ShopProductResponse:
    return await op_products_verify(
        ShopProductIdPayload(shop_id=shop_id, shop_product_id=product_id),
        user=require_context().user,
        di=di,
    )


@router.get(
    "/{shop_id}/products/{product_id}/similar",
    response_model=ListResponse[ShopProductSimilarResponse],
)
async def list_similar_products(
    shop_id: str, product_id: str, di: Di
) -> ListResponse[ShopProductSimilarResponse]:
    return await op_products_similar_list(
        ShopProductIdPayload(shop_id=shop_id, shop_product_id=product_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/products/{product_id}/merge", response_model=ShopProductResponse)
async def merge_product(
    shop_id: str, product_id: str, payload: ShopProductMergeRequest, di: Di
) -> ShopProductResponse:
    return await op_products_merge(
        ShopProductMergePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_product_id": product_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.post(
    "/{shop_id}/products/{product_id}/dismiss-similar", response_model=ShopProductResponse
)
async def dismiss_similar_product(shop_id: str, product_id: str, di: Di) -> ShopProductResponse:
    return await op_products_dismiss_similar(
        ShopProductIdPayload(shop_id=shop_id, shop_product_id=product_id),
        user=require_context().user,
        di=di,
    )


# --- Меню ---


@router.get("/{shop_id}/menus", response_model=ListResponse[ShopMenuResponse])
async def list_menus(shop_id: str, di: Di) -> ListResponse[ShopMenuResponse]:
    return await op_menus_list(ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di)


@router.post("/{shop_id}/menus", response_model=ShopMenuResponse)
async def create_menu(shop_id: str, payload: ShopMenuCreateRequest, di: Di) -> ShopMenuResponse:
    return await op_menus_create(
        ShopMenuCreatePayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/menus/reorder", response_model=EmptyPayload)
async def reorder_menus(shop_id: str, payload: ShopMenusReorderRequest, di: Di) -> EmptyPayload:
    return await op_menus_reorder(
        ShopMenusReorderPayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.patch("/{shop_id}/menus/{menu_id}", response_model=ShopMenuResponse)
async def update_menu(
    shop_id: str, menu_id: str, payload: ShopMenuUpdateRequest, di: Di
) -> ShopMenuResponse:
    return await op_menus_update(
        ShopMenuUpdatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_menu_id": menu_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/menus/{menu_id}/status", response_model=ShopMenuResponse)
async def set_menu_status(
    shop_id: str, menu_id: str, payload: ShopMenuSetStatusRequest, di: Di
) -> ShopMenuResponse:
    return await op_menus_set_status(
        ShopMenuSetStatusPayload(shop_id=shop_id, shop_menu_id=menu_id, status=payload.status),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/menus/{menu_id}", response_model=EmptyPayload)
async def remove_menu(shop_id: str, menu_id: str, di: Di) -> EmptyPayload:
    return await op_menus_remove(
        ShopMenuIdPayload(shop_id=shop_id, shop_menu_id=menu_id),
        user=require_context().user,
        di=di,
    )


# --- Разделы меню ---


@router.post("/{shop_id}/menus/{menu_id}/sections", response_model=ShopMenuSection)
async def create_menu_section(
    shop_id: str, menu_id: str, payload: ShopMenuSectionCreateRequest, di: Di
) -> ShopMenuSection:
    return await op_menu_sections_create(
        ShopMenuSectionCreatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_menu_id": menu_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/menus/{menu_id}/sections/reorder", response_model=EmptyPayload)
async def reorder_menu_sections(
    shop_id: str, menu_id: str, payload: ShopMenuSectionsReorderRequest, di: Di
) -> EmptyPayload:
    return await op_menu_sections_reorder(
        ShopMenuSectionsReorderPayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_menu_id": menu_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.patch("/{shop_id}/menu-sections/{section_id}", response_model=ShopMenuSection)
async def update_menu_section(
    shop_id: str, section_id: str, payload: ShopMenuSectionUpdateRequest, di: Di
) -> ShopMenuSection:
    return await op_menu_sections_update(
        ShopMenuSectionUpdatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_menu_section_id": section_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/menu-sections/{section_id}", response_model=EmptyPayload)
async def remove_menu_section(shop_id: str, section_id: str, di: Di) -> EmptyPayload:
    return await op_menu_sections_remove(
        ShopMenuSectionIdPayload(shop_id=shop_id, shop_menu_section_id=section_id),
        user=require_context().user,
        di=di,
    )


# --- Позиции меню ---


@router.post("/{shop_id}/menus/{menu_id}/items", response_model=ShopMenuItemResponse)
async def add_menu_item(
    shop_id: str, menu_id: str, payload: ShopMenuItemAddRequest, di: Di
) -> ShopMenuItemResponse:
    return await op_menu_items_add(
        ShopMenuItemAddPayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_menu_id": menu_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/menu-items/reorder", response_model=EmptyPayload)
async def reorder_menu_items(
    shop_id: str, payload: ShopMenuItemsReorderRequest, di: Di
) -> EmptyPayload:
    return await op_menu_items_reorder(
        ShopMenuItemsReorderPayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.patch("/{shop_id}/menu-items/{item_id}", response_model=ShopMenuItemResponse)
async def update_menu_item(
    shop_id: str, item_id: str, payload: ShopMenuItemUpdateRequest, di: Di
) -> ShopMenuItemResponse:
    return await op_menu_items_update(
        ShopMenuItemUpdatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_menu_item_id": item_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/menu-items/{item_id}/move", response_model=ShopMenuItemResponse)
async def move_menu_item(
    shop_id: str, item_id: str, payload: ShopMenuItemMoveRequest, di: Di
) -> ShopMenuItemResponse:
    return await op_menu_items_move(
        ShopMenuItemMovePayload(
            shop_id=shop_id,
            shop_menu_item_id=item_id,
            shop_menu_section_id=payload.shop_menu_section_id,
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/menu-items/{item_id}", response_model=EmptyPayload)
async def remove_menu_item(shop_id: str, item_id: str, di: Di) -> EmptyPayload:
    return await op_menu_items_remove(
        ShopMenuItemIdPayload(shop_id=shop_id, shop_menu_item_id=item_id),
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
