"""Регистрация WS command-handler'ов shop в `core.websocket`."""

from __future__ import annotations

from apps.shop.di import ShopDi
from apps.shop.models.api import ShopCreateRequest
from apps.shop.models.import_api import (
    ShopMenuFileImportRunPayload,
    ShopMenuImportApplyPayload,
    ShopMenuImportStartPayload,
    ShopMenuTemplateBuildPayload,
    ShopProductsEnrichApplyPayload,
    ShopProductsEnrichPayload,
)
from apps.shop.realtime.menu_import_operations import (
    op_menu_file_imports_run,
    op_menu_imports_apply,
    op_menu_imports_list,
    op_menu_imports_start,
    op_menu_templates_build,
    op_products_enrich,
    op_products_enrich_apply,
)
from apps.shop.realtime.operations import (
    ShopAiDescribePayload,
    ShopAiEnhancePhotoPayload,
    ShopAiGeneratePhotoPayload,
    ShopAiShopPayload,
    ShopAiSuggestOptionsPayload,
    ShopCartPricePayload,
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
    ShopOrderCreatePayload,
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
    ShopPublicOrderStatusPayload,
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
    op_public_cart_price,
    op_public_order_create,
    op_public_order_status,
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
from core.websocket import EmptyPayload, Operation, RegisteredOperation

SHOP_OPERATIONS: dict[str, RegisteredOperation[ShopDi]] = {
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
    "shop/products/list_requested": Operation(payload_model=ShopIdPayload, fn=op_products_list),
    "shop/products/create_requested": Operation(
        payload_model=ShopProductCreatePayload, fn=op_products_create
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
    "shop/products/verify_requested": Operation(
        payload_model=ShopProductIdPayload, fn=op_products_verify
    ),
    "shop/products/similar_list_requested": Operation(
        payload_model=ShopProductIdPayload, fn=op_products_similar_list
    ),
    "shop/products/merge_requested": Operation(
        payload_model=ShopProductMergePayload, fn=op_products_merge
    ),
    "shop/products/dismiss_similar_requested": Operation(
        payload_model=ShopProductIdPayload, fn=op_products_dismiss_similar
    ),
    "shop/menus/list_requested": Operation(payload_model=ShopIdPayload, fn=op_menus_list),
    "shop/menus/create_requested": Operation(
        payload_model=ShopMenuCreatePayload, fn=op_menus_create
    ),
    "shop/menus/update_requested": Operation(
        payload_model=ShopMenuUpdatePayload, fn=op_menus_update
    ),
    "shop/menus/reorder_requested": Operation(
        payload_model=ShopMenusReorderPayload, fn=op_menus_reorder
    ),
    "shop/menus/set_status_requested": Operation(
        payload_model=ShopMenuSetStatusPayload, fn=op_menus_set_status
    ),
    "shop/menus/remove_requested": Operation(
        payload_model=ShopMenuIdPayload, fn=op_menus_remove
    ),
    "shop/menu_sections/create_requested": Operation(
        payload_model=ShopMenuSectionCreatePayload, fn=op_menu_sections_create
    ),
    "shop/menu_sections/update_requested": Operation(
        payload_model=ShopMenuSectionUpdatePayload, fn=op_menu_sections_update
    ),
    "shop/menu_sections/remove_requested": Operation(
        payload_model=ShopMenuSectionIdPayload, fn=op_menu_sections_remove
    ),
    "shop/menu_sections/reorder_requested": Operation(
        payload_model=ShopMenuSectionsReorderPayload, fn=op_menu_sections_reorder
    ),
    "shop/menu_items/add_requested": Operation(
        payload_model=ShopMenuItemAddPayload, fn=op_menu_items_add
    ),
    "shop/menu_items/update_requested": Operation(
        payload_model=ShopMenuItemUpdatePayload, fn=op_menu_items_update
    ),
    "shop/menu_items/move_requested": Operation(
        payload_model=ShopMenuItemMovePayload, fn=op_menu_items_move
    ),
    "shop/menu_items/remove_requested": Operation(
        payload_model=ShopMenuItemIdPayload, fn=op_menu_items_remove
    ),
    "shop/menu_items/reorder_requested": Operation(
        payload_model=ShopMenuItemsReorderPayload, fn=op_menu_items_reorder
    ),
    "shop/menu_imports/start_requested": Operation(
        payload_model=ShopMenuImportStartPayload, fn=op_menu_imports_start
    ),
    "shop/menu_imports/list_requested": Operation(
        payload_model=ShopIdPayload, fn=op_menu_imports_list
    ),
    "shop/menu_imports/apply_requested": Operation(
        payload_model=ShopMenuImportApplyPayload, fn=op_menu_imports_apply
    ),
    "shop/menu_templates/build_requested": Operation(
        payload_model=ShopMenuTemplateBuildPayload, fn=op_menu_templates_build
    ),
    "shop/products/enrich_requested": Operation(
        payload_model=ShopProductsEnrichPayload, fn=op_products_enrich
    ),
    "shop/products/enrich_apply_requested": Operation(
        payload_model=ShopProductsEnrichApplyPayload, fn=op_products_enrich_apply
    ),
    "shop/menu_file_imports/run_requested": Operation(
        payload_model=ShopMenuFileImportRunPayload, fn=op_menu_file_imports_run
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
    "shop/ai/describe_requested": Operation(
        payload_model=ShopAiDescribePayload, fn=op_ai_describe_product
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
}
