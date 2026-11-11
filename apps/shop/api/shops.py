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
    ShopAiSuggestOptionsRequest,
    ShopBadgeIconsResponse,
    ShopBannerCreateRequest,
    ShopBannerResponse,
    ShopBannersReorderRequest,
    ShopBannerUpdateRequest,
    ShopCategoriesReorderRequest,
    ShopCategoryCreateRequest,
    ShopCategoryResponse,
    ShopCategoryUpdateRequest,
    ShopCreateRequest,
    ShopLoyaltyProgramResponse,
    ShopLoyaltyProgramSetRequest,
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
    ShopShelfCreateRequest,
    ShopShelfResponse,
    ShopShelfUpdateRequest,
    ShopShelvesReorderRequest,
    ShopTableCreateRequest,
    ShopTableResponse,
    ShopTableUpdateRequest,
    ShopTelegramConnectRequest,
    ShopUpdateRequest,
)
from apps.shop.models.enums import ShopOrderStatus
from apps.shop.realtime.operations import (
    ShopAiBatchResponse,
    ShopAiCallResponse,
    ShopAiDescribeBatchPayload,
    ShopAiDescribePayload,
    ShopAiEnhancePhotoPayload,
    ShopAiGeneratePhotoPayload,
    ShopAiParseMenuPayload,
    ShopAiShopPayload,
    ShopAiSuggestOptionsPayload,
    ShopBannerCreatePayload,
    ShopBannerIdPayload,
    ShopBannersReorderPayload,
    ShopBannerUpdatePayload,
    ShopCategoriesReorderPayload,
    ShopCategoryCreatePayload,
    ShopCategoryIdPayload,
    ShopCategoryUpdatePayload,
    ShopDomainAddPayload,
    ShopDomainIdPayload,
    ShopIdPayload,
    ShopLoyaltyProgramPayload,
    ShopLoyaltyProgramSetPayload,
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
    ShopShelfCreatePayload,
    ShopShelfIdPayload,
    ShopShelfUpdatePayload,
    ShopShelvesReorderPayload,
    ShopTableCreatePayload,
    ShopTableIdPayload,
    ShopTableUpdatePayload,
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
    op_banners_create,
    op_banners_list,
    op_banners_remove,
    op_banners_reorder,
    op_banners_update,
    op_categories_create,
    op_categories_list,
    op_categories_remove,
    op_categories_reorder,
    op_categories_update,
    op_domains_add,
    op_domains_provision,
    op_domains_remove,
    op_loyalty_program_get,
    op_loyalty_program_set,
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
    op_shelves_create,
    op_shelves_list,
    op_shelves_remove,
    op_shelves_reorder,
    op_shelves_update,
    op_shops_create,
    op_shops_get,
    op_shops_list,
    op_shops_publish,
    op_shops_remove,
    op_shops_suspend,
    op_shops_update,
    op_tables_create,
    op_tables_list,
    op_tables_remove,
    op_tables_update,
    op_telegram_connect,
    op_telegram_disconnect,
)
from core.catalog import operations as catalog_ops
from core.catalog.models import CatalogProduct
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
        ShopCategoryCreatePayload(
            shop_id=shop_id, name=payload.name, parent_id=payload.parent_id
        ),
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


# --- Столы зала ---


@router.get("/{shop_id}/tables", response_model=ListResponse[ShopTableResponse])
async def list_tables(shop_id: str, di: Di) -> ListResponse[ShopTableResponse]:
    return await op_tables_list(
        ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di
    )


@router.post("/{shop_id}/tables", response_model=ShopTableResponse)
async def create_table(
    shop_id: str, payload: ShopTableCreateRequest, di: Di
) -> ShopTableResponse:
    return await op_tables_create(
        ShopTableCreatePayload(shop_id=shop_id, label=payload.label),
        user=require_context().user,
        di=di,
    )


@router.patch("/{shop_id}/tables/{table_id}", response_model=ShopTableResponse)
async def update_table(
    shop_id: str, table_id: str, payload: ShopTableUpdateRequest, di: Di
) -> ShopTableResponse:
    return await op_tables_update(
        ShopTableUpdatePayload(shop_id=shop_id, shop_table_id=table_id, label=payload.label),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/tables/{table_id}", response_model=EmptyPayload)
async def remove_table(shop_id: str, table_id: str, di: Di) -> EmptyPayload:
    return await op_tables_remove(
        ShopTableIdPayload(shop_id=shop_id, shop_table_id=table_id),
        user=require_context().user,
        di=di,
    )


# --- Товары ---


@router.get(
    "/{shop_id}/catalog-products/suggest",
    response_model=ListResponse[CatalogProduct],
)
async def suggest_catalog_products(
    shop_id: str,
    di: Di,
    name: Annotated[str | None, Query(max_length=300)] = None,
    sku: Annotated[str | None, Query(max_length=128)] = None,
    barcode: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> ListResponse[CatalogProduct]:
    _ = shop_id
    return await catalog_ops.op_products_suggest(
        catalog_ops.CatalogProductsSuggestPayload(
            name=name, sku=sku, barcode=barcode, limit=limit
        ),
        user=require_context().user,
        di=di,
    )


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
                "product_id": product_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/products/{product_id}", response_model=EmptyPayload)
async def remove_product(shop_id: str, product_id: str, di: Di) -> EmptyPayload:
    return await op_products_remove(
        ShopProductIdPayload(shop_id=shop_id, product_id=product_id),
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


@router.post("/{shop_id}/ai/describe", response_model=ShopAiCallResponse)
async def ai_describe(shop_id: str, body: ShopAiDescribeRequest, di: Di) -> ShopAiCallResponse:
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


@router.post("/{shop_id}/ai/enhance-photo", response_model=ShopAiCallResponse)
async def ai_enhance_photo(
    shop_id: str, body: ShopAiEnhancePhotoRequest, di: Di
) -> ShopAiCallResponse:
    return await op_ai_enhance_photo(
        ShopAiEnhancePhotoPayload(shop_id=shop_id, file_id=body.file_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/generate-photo", response_model=ShopAiCallResponse)
async def ai_generate_photo(shop_id: str, body: ShopAiBriefRequest, di: Di) -> ShopAiCallResponse:
    return await op_ai_generate_photo(
        ShopAiGeneratePhotoPayload(shop_id=shop_id, name=body.name, description=body.description),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/describe-shop", response_model=ShopAiCallResponse)
async def ai_describe_shop(shop_id: str, body: ShopAiBriefRequest, di: Di) -> ShopAiCallResponse:
    return await op_ai_describe_shop(
        ShopAiShopPayload(shop_id=shop_id, name=body.name, description=body.description),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/generate-cover", response_model=ShopAiCallResponse)
async def ai_generate_cover(shop_id: str, body: ShopAiBriefRequest, di: Di) -> ShopAiCallResponse:
    return await op_ai_generate_cover(
        ShopAiShopPayload(shop_id=shop_id, name=body.name, description=body.description),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/generate-logo", response_model=ShopAiCallResponse)
async def ai_generate_logo(shop_id: str, body: ShopAiBriefRequest, di: Di) -> ShopAiCallResponse:
    return await op_ai_generate_logo(
        ShopAiShopPayload(shop_id=shop_id, name=body.name, description=body.description),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/autofill", response_model=ShopAiCallResponse)
async def ai_autofill(shop_id: str, di: Di) -> ShopAiCallResponse:
    return await op_ai_autofill(ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di)


@router.post("/{shop_id}/ai/parse-menu", response_model=ShopAiCallResponse)
async def ai_parse_menu(
    shop_id: str, body: ShopAiParseMenuRequest, di: Di
) -> ShopAiCallResponse:
    return await op_ai_parse_menu(
        ShopAiParseMenuPayload(shop_id=shop_id, text=body.text),
        user=require_context().user,
        di=di,
    )


@router.post("/{shop_id}/ai/suggest-options", response_model=ShopAiCallResponse)
async def ai_suggest_options(
    shop_id: str, body: ShopAiSuggestOptionsRequest, di: Di
) -> ShopAiCallResponse:
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


@router.get("/{shop_id}/shelves", response_model=ListResponse[ShopShelfResponse])
async def list_shelves(shop_id: str, di: Di) -> ListResponse[ShopShelfResponse]:
    return await op_shelves_list(ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di)


@router.post("/{shop_id}/shelves", response_model=ShopShelfResponse)
async def create_shelf(shop_id: str, payload: ShopShelfCreateRequest, di: Di) -> ShopShelfResponse:
    return await op_shelves_create(
        ShopShelfCreatePayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.patch("/{shop_id}/shelves/{shelf_id}", response_model=ShopShelfResponse)
async def update_shelf(
    shop_id: str, shelf_id: str, payload: ShopShelfUpdateRequest, di: Di
) -> ShopShelfResponse:
    return await op_shelves_update(
        ShopShelfUpdatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_shelf_id": shelf_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.put("/{shop_id}/shelves/order", response_model=EmptyPayload)
async def reorder_shelves(
    shop_id: str, payload: ShopShelvesReorderRequest, di: Di
) -> EmptyPayload:
    return await op_shelves_reorder(
        ShopShelvesReorderPayload(shop_id=shop_id, shelf_ids=payload.shelf_ids),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/shelves/{shelf_id}", response_model=EmptyPayload)
async def remove_shelf(shop_id: str, shelf_id: str, di: Di) -> EmptyPayload:
    return await op_shelves_remove(
        ShopShelfIdPayload(shop_id=shop_id, shop_shelf_id=shelf_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{shop_id}/banners", response_model=ListResponse[ShopBannerResponse])
async def list_banners(shop_id: str, di: Di) -> ListResponse[ShopBannerResponse]:
    return await op_banners_list(ShopIdPayload(shop_id=shop_id), user=require_context().user, di=di)


@router.post("/{shop_id}/banners", response_model=ShopBannerResponse)
async def create_banner(
    shop_id: str, payload: ShopBannerCreateRequest, di: Di
) -> ShopBannerResponse:
    return await op_banners_create(
        ShopBannerCreatePayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )


@router.patch("/{shop_id}/banners/{banner_id}", response_model=ShopBannerResponse)
async def update_banner(
    shop_id: str, banner_id: str, payload: ShopBannerUpdateRequest, di: Di
) -> ShopBannerResponse:
    return await op_banners_update(
        ShopBannerUpdatePayload.model_validate(
            {
                "shop_id": shop_id,
                "shop_banner_id": banner_id,
                **payload.model_dump(exclude_unset=True),
            }
        ),
        user=require_context().user,
        di=di,
    )


@router.put("/{shop_id}/banners/order", response_model=EmptyPayload)
async def reorder_banners(
    shop_id: str, payload: ShopBannersReorderRequest, di: Di
) -> EmptyPayload:
    return await op_banners_reorder(
        ShopBannersReorderPayload(shop_id=shop_id, banner_ids=payload.banner_ids),
        user=require_context().user,
        di=di,
    )


@router.delete("/{shop_id}/banners/{banner_id}", response_model=EmptyPayload)
async def remove_banner(shop_id: str, banner_id: str, di: Di) -> EmptyPayload:
    return await op_banners_remove(
        ShopBannerIdPayload(shop_id=shop_id, shop_banner_id=banner_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{shop_id}/loyalty", response_model=ShopLoyaltyProgramResponse)
async def get_loyalty_program(shop_id: str, di: Di) -> ShopLoyaltyProgramResponse:
    return await op_loyalty_program_get(
        ShopLoyaltyProgramPayload(shop_id=shop_id),
        user=require_context().user,
        di=di,
    )


@router.put("/{shop_id}/loyalty", response_model=ShopLoyaltyProgramResponse)
async def set_loyalty_program(
    shop_id: str, payload: ShopLoyaltyProgramSetRequest, di: Di
) -> ShopLoyaltyProgramResponse:
    return await op_loyalty_program_set(
        ShopLoyaltyProgramSetPayload.model_validate(
            {"shop_id": shop_id, **payload.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        di=di,
    )
