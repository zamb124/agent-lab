"""Регистрация WS command-handler'ов shop в `core.websocket`."""

from __future__ import annotations

from apps.shop.di import ShopDi
from apps.shop.models.api import ShopCreateRequest
from apps.shop.realtime.operations import (
    ShopAiDescribeBatchPayload,
    ShopAiDescribePayload,
    ShopAiEnhancePhotoPayload,
    ShopAiGeneratePhotoPayload,
    ShopCategoryCreatePayload,
    ShopCategoryIdPayload,
    ShopCategoryUpdatePayload,
    ShopDomainAddPayload,
    ShopDomainIdPayload,
    ShopIdPayload,
    ShopOrderCreatePayload,
    ShopOrderIdPayload,
    ShopOrderListPayload,
    ShopOrderSetStatusPayload,
    ShopProductCreatePayload,
    ShopProductIdPayload,
    ShopProductsImportPayload,
    ShopProductUpdatePayload,
    ShopPublicOrderStatusPayload,
    ShopTelegramConnectPayload,
    ShopUpdatePayload,
    op_ai_describe_batch,
    op_ai_describe_product,
    op_ai_enhance_photo,
    op_ai_generate_photo,
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
    op_products_import,
    op_products_list,
    op_products_remove,
    op_products_update,
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
    "shop/shops/item_requested": Operation(payload_model=ShopIdPayload, fn=op_shops_get),
    "shop/shops/create_requested": Operation(
        payload_model=ShopCreateRequest, fn=op_shops_create
    ),
    "shop/shops/update_requested": Operation(
        payload_model=ShopUpdatePayload, fn=op_shops_update
    ),
    "shop/shops/publish_requested": Operation(
        payload_model=ShopIdPayload, fn=op_shops_publish
    ),
    "shop/shops/suspend_requested": Operation(
        payload_model=ShopIdPayload, fn=op_shops_suspend
    ),
    "shop/shops/remove_requested": Operation(
        payload_model=ShopIdPayload, fn=op_shops_remove
    ),
    "shop/categories/list_requested": Operation(
        payload_model=ShopIdPayload, fn=op_categories_list
    ),
    "shop/categories/create_requested": Operation(
        payload_model=ShopCategoryCreatePayload, fn=op_categories_create
    ),
    "shop/categories/update_requested": Operation(
        payload_model=ShopCategoryUpdatePayload, fn=op_categories_update
    ),
    "shop/categories/remove_requested": Operation(
        payload_model=ShopCategoryIdPayload, fn=op_categories_remove
    ),
    "shop/products/list_requested": Operation(
        payload_model=ShopIdPayload, fn=op_products_list
    ),
    "shop/products/create_requested": Operation(
        payload_model=ShopProductCreatePayload, fn=op_products_create
    ),
    "shop/products/import_requested": Operation(
        payload_model=ShopProductsImportPayload, fn=op_products_import
    ),
    "shop/products/update_requested": Operation(
        payload_model=ShopProductUpdatePayload, fn=op_products_update
    ),
    "shop/products/remove_requested": Operation(
        payload_model=ShopProductIdPayload, fn=op_products_remove
    ),
    "shop/orders/list_requested": Operation(
        payload_model=ShopOrderListPayload, fn=op_orders_list
    ),
    "shop/orders/item_requested": Operation(
        payload_model=ShopOrderIdPayload, fn=op_orders_get
    ),
    "shop/orders/set_status_requested": Operation(
        payload_model=ShopOrderSetStatusPayload, fn=op_orders_set_status
    ),
    "shop/domains/add_requested": Operation(
        payload_model=ShopDomainAddPayload, fn=op_domains_add
    ),
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
    "shop/ai/describe_batch_requested": Operation(
        payload_model=ShopAiDescribeBatchPayload, fn=op_ai_describe_batch
    ),
    "shop/ai/enhance_photo_requested": Operation(
        payload_model=ShopAiEnhancePhotoPayload, fn=op_ai_enhance_photo
    ),
    "shop/ai/generate_photo_requested": Operation(
        payload_model=ShopAiGeneratePhotoPayload, fn=op_ai_generate_photo
    ),
}
