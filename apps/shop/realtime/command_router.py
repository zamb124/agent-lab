"""Регистрация WS command-handler'ов shop в `core.websocket`."""

from __future__ import annotations

from apps.shop.di import ShopDi
from apps.shop.models.api import ShopCreateRequest
from apps.shop.realtime.company_operations import (
    ShopCompanyInitPayload,
    op_demos_seed,
    op_shop_company_init,
)
from apps.shop.realtime.operations import (
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
    ShopCartPricePayload,
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
    ShopMyOrderCodePayload,
    ShopMyOrdersListPayload,
    ShopNotifyBackPayload,
    ShopOrderCreatePayload,
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
    ShopPublicOrderStatusPayload,
    ShopShelfCreatePayload,
    ShopShelfIdPayload,
    ShopShelfUpdatePayload,
    ShopShelvesReorderPayload,
    ShopStorefrontGeoPayload,
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
    op_public_cart_price,
    op_public_my_order_cancel,
    op_public_my_order_get,
    op_public_my_orders_list,
    op_public_notify_back,
    op_public_order_create,
    op_public_order_status,
    op_public_storefront_geo,
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
from core.websocket import EmptyPayload, Operation, RegisteredOperation

SHOP_OPERATIONS: dict[str, RegisteredOperation[ShopDi]] = {
    "shop/company/init_requested": Operation(
        payload_model=ShopCompanyInitPayload, fn=op_shop_company_init
    ),
    "shop/demos/seed_requested": Operation(
        payload_model=EmptyPayload, fn=op_demos_seed
    ),
    "shop/shops/list_requested": Operation(payload_model=EmptyPayload, fn=op_shops_list),
    "shop/badge_icons/list_requested": Operation(
        payload_model=EmptyPayload, fn=op_badge_icons_list
    ),
    "shop/shops/item_requested": Operation(payload_model=ShopIdPayload, fn=op_shops_get),
    "shop/shops/create_requested": Operation(payload_model=ShopCreateRequest, fn=op_shops_create),
    "shop/shops/update_requested": Operation(payload_model=ShopUpdatePayload, fn=op_shops_update),
    "shop/shops/publish_requested": Operation(payload_model=ShopIdPayload, fn=op_shops_publish),
    "shop/shops/suspend_requested": Operation(payload_model=ShopIdPayload, fn=op_shops_suspend),
    "shop/shops/remove_requested": Operation(payload_model=ShopIdPayload, fn=op_shops_remove),
    "shop/categories/list_requested": Operation(payload_model=ShopIdPayload, fn=op_categories_list),
    "shop/categories/create_requested": Operation(
        payload_model=ShopCategoryCreatePayload, fn=op_categories_create
    ),
    "shop/categories/update_requested": Operation(
        payload_model=ShopCategoryUpdatePayload, fn=op_categories_update
    ),
    "shop/categories/reorder_requested": Operation(
        payload_model=ShopCategoriesReorderPayload, fn=op_categories_reorder
    ),
    "shop/categories/remove_requested": Operation(
        payload_model=ShopCategoryIdPayload, fn=op_categories_remove
    ),
    "shop/tables/list_requested": Operation(payload_model=ShopIdPayload, fn=op_tables_list),
    "shop/tables/create_requested": Operation(
        payload_model=ShopTableCreatePayload, fn=op_tables_create
    ),
    "shop/tables/update_requested": Operation(
        payload_model=ShopTableUpdatePayload, fn=op_tables_update
    ),
    "shop/tables/remove_requested": Operation(
        payload_model=ShopTableIdPayload, fn=op_tables_remove
    ),
    "shop/products/list_requested": Operation(payload_model=ShopIdPayload, fn=op_products_list),
    "shop/products/create_requested": Operation(
        payload_model=ShopProductCreatePayload, fn=op_products_create
    ),
    "shop/products/import_requested": Operation(
        payload_model=ShopProductsImportPayload, fn=op_products_import
    ),
    "shop/products/update_requested": Operation(
        payload_model=ShopProductUpdatePayload, fn=op_products_update
    ),
    "shop/products/reorder_requested": Operation(
        payload_model=ShopProductsReorderPayload, fn=op_products_reorder
    ),
    "shop/products/remove_requested": Operation(
        payload_model=ShopProductIdPayload, fn=op_products_remove
    ),
    "shop/modifiers/groups/list_requested": Operation(
        payload_model=ShopIdPayload, fn=op_modifier_groups_list
    ),
    "shop/modifiers/groups/create_requested": Operation(
        payload_model=ShopModifierGroupCreatePayload, fn=op_modifier_groups_create
    ),
    "shop/modifiers/groups/update_requested": Operation(
        payload_model=ShopModifierGroupUpdatePayload, fn=op_modifier_groups_update
    ),
    "shop/modifiers/groups/remove_requested": Operation(
        payload_model=ShopModifierGroupIdPayload, fn=op_modifier_groups_remove
    ),
    "shop/modifiers/options/create_requested": Operation(
        payload_model=ShopModifierOptionCreatePayload, fn=op_modifier_options_create
    ),
    "shop/modifiers/options/update_requested": Operation(
        payload_model=ShopModifierOptionUpdatePayload, fn=op_modifier_options_update
    ),
    "shop/modifiers/options/remove_requested": Operation(
        payload_model=ShopModifierOptionIdPayload, fn=op_modifier_options_remove
    ),
    "shop/ai/suggest_options_requested": Operation(
        payload_model=ShopAiSuggestOptionsPayload, fn=op_ai_suggest_options
    ),
    "shop/products/modifiers/attach_requested": Operation(
        payload_model=ShopProductModifierAttachPayload, fn=op_products_modifier_attach
    ),
    "shop/products/modifiers/detach_requested": Operation(
        payload_model=ShopProductModifierDetachPayload, fn=op_products_modifier_detach
    ),
    "shop/promos/list_requested": Operation(payload_model=ShopIdPayload, fn=op_promos_list),
    "shop/promos/create_requested": Operation(
        payload_model=ShopPromoCreatePayload, fn=op_promos_create
    ),
    "shop/promos/update_requested": Operation(
        payload_model=ShopPromoUpdatePayload, fn=op_promos_update
    ),
    "shop/promos/remove_requested": Operation(
        payload_model=ShopPromoIdPayload, fn=op_promos_remove
    ),
    "shop/shelves/list_requested": Operation(
        payload_model=ShopIdPayload, fn=op_shelves_list
    ),
    "shop/shelves/create_requested": Operation(
        payload_model=ShopShelfCreatePayload, fn=op_shelves_create
    ),
    "shop/shelves/update_requested": Operation(
        payload_model=ShopShelfUpdatePayload, fn=op_shelves_update
    ),
    "shop/shelves/reorder_requested": Operation(
        payload_model=ShopShelvesReorderPayload, fn=op_shelves_reorder
    ),
    "shop/shelves/remove_requested": Operation(
        payload_model=ShopShelfIdPayload, fn=op_shelves_remove
    ),
    "shop/banners/list_requested": Operation(
        payload_model=ShopIdPayload, fn=op_banners_list
    ),
    "shop/banners/create_requested": Operation(
        payload_model=ShopBannerCreatePayload, fn=op_banners_create
    ),
    "shop/banners/update_requested": Operation(
        payload_model=ShopBannerUpdatePayload, fn=op_banners_update
    ),
    "shop/banners/reorder_requested": Operation(
        payload_model=ShopBannersReorderPayload, fn=op_banners_reorder
    ),
    "shop/banners/remove_requested": Operation(
        payload_model=ShopBannerIdPayload, fn=op_banners_remove
    ),
    "shop/public/notify_back_requested": Operation(
        payload_model=ShopNotifyBackPayload, fn=op_public_notify_back
    ),
    "shop/public/cart_price_requested": Operation(
        payload_model=ShopCartPricePayload, fn=op_public_cart_price
    ),
    "shop/orders/list_requested": Operation(payload_model=ShopOrderListPayload, fn=op_orders_list),
    "shop/orders/item_requested": Operation(payload_model=ShopOrderIdPayload, fn=op_orders_get),
    "shop/orders/set_status_requested": Operation(
        payload_model=ShopOrderSetStatusPayload, fn=op_orders_set_status
    ),
    "shop/domains/add_requested": Operation(payload_model=ShopDomainAddPayload, fn=op_domains_add),
    "shop/domains/remove_requested": Operation(
        payload_model=ShopDomainIdPayload, fn=op_domains_remove
    ),
    "shop/domains/provision_requested": Operation(
        payload_model=ShopDomainIdPayload, fn=op_domains_provision
    ),
    "shop/telegram/connect_requested": Operation(
        payload_model=ShopTelegramConnectPayload, fn=op_telegram_connect
    ),
    "shop/telegram/disconnect_requested": Operation(
        payload_model=ShopIdPayload, fn=op_telegram_disconnect
    ),
    "shop/public/order_create_requested": Operation(
        payload_model=ShopOrderCreatePayload, fn=op_public_order_create
    ),
    "shop/public/order_status_requested": Operation(
        payload_model=ShopPublicOrderStatusPayload, fn=op_public_order_status
    ),
    "shop/public/my_orders_list_requested": Operation(
        payload_model=ShopMyOrdersListPayload, fn=op_public_my_orders_list
    ),
    "shop/public/my_order_get_requested": Operation(
        payload_model=ShopMyOrderCodePayload, fn=op_public_my_order_get
    ),
    "shop/public/my_order_cancel_requested": Operation(
        payload_model=ShopMyOrderCodePayload, fn=op_public_my_order_cancel
    ),
    "shop/public/storefront_geo_requested": Operation(
        payload_model=ShopStorefrontGeoPayload, fn=op_public_storefront_geo
    ),
    "shop/ai/describe_requested": Operation(
        payload_model=ShopAiDescribePayload, fn=op_ai_describe_product
    ),
    "shop/ai/describe_batch_requested": Operation(
        payload_model=ShopAiDescribeBatchPayload, fn=op_ai_describe_batch
    ),
    "shop/ai/enhance_photo_requested": Operation(
        payload_model=ShopAiEnhancePhotoPayload, fn=op_ai_enhance_photo
    ),
    "shop/ai/generate_photo_requested": Operation(
        payload_model=ShopAiGeneratePhotoPayload, fn=op_ai_generate_photo
    ),
    "shop/ai/describe_shop_requested": Operation(
        payload_model=ShopAiShopPayload, fn=op_ai_describe_shop
    ),
    "shop/ai/generate_cover_requested": Operation(
        payload_model=ShopAiShopPayload, fn=op_ai_generate_cover
    ),
    "shop/ai/generate_logo_requested": Operation(
        payload_model=ShopAiShopPayload, fn=op_ai_generate_logo
    ),
    "shop/ai/autofill_requested": Operation(payload_model=ShopIdPayload, fn=op_ai_autofill),
    "shop/ai/parse_menu_requested": Operation(
        payload_model=ShopAiParseMenuPayload, fn=op_ai_parse_menu
    ),
}
