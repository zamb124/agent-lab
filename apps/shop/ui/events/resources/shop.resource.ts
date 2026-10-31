/**
 * Фабрики событий магазина: каждая команда — `op_*` через WS RPC + REST-зеркало.
 *
 * Ресурс `shop/shops` — коллекция магазинов компании; категории, товары и
 * заказы адресуются `shop_id` из маршрута, поэтому они — async ops, а не
 * коллекции.
 */

import { createAsyncOp, createResourceCollection, rerunLastRequest } from '@platform/lib/events/index.js';
import type { AsyncOpFactory } from '@platform/lib/events/factories/async-op.js';
import type { ResourceCollectionSlice, ResourceItem } from '@platform/lib/events/factories/resource-collection.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

export const SHOP_SHOP_EVENTS = [
    'shop/shop/created',
    'shop/shop/updated',
    'shop/shop/published',
];

function mergeShopSummary(state: ResourceCollectionSlice, event: { payload: unknown }): ResourceCollectionSlice {
    if (!isPlainRecord(event.payload)) {
        throw new Error('shop/shop/*: payload required');
    }
    const shopId = event.payload.shop_id;
    if (typeof shopId !== 'string') {
        throw new Error('shop/shop/*: payload.shop_id required');
    }
    const index = state.items.findIndex((item) => item && item.shop_id === shopId);
    const current = state.items[index];
    if (index === -1 || current === undefined) {
        return state;
    }
    const patch: Record<string, unknown> = {};
    if (typeof event.payload.slug === 'string') {
        patch.slug = event.payload.slug;
    }
    if (typeof event.payload.status === 'string') {
        patch.status = event.payload.status;
    }
    const merged: ResourceItem = { ...current, ...patch };
    const items = state.items.map((item: ResourceItem, position: number) =>
        position === index ? merged : item);
    return { ...state, items, byId: { ...state.byId, [shopId]: merged } };
}

export const shopShopsResource = createResourceCollection({
    name: 'shop/shops',
    baseUrl: '/shop/api/v1/shops',
    idField: 'shop_id',
    operations: ['list', 'get'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({}),
    extraReducer: (state, event) => {
        if (SHOP_SHOP_EVENTS.includes(event.type)) {
            return mergeShopSummary(state, event);
        }
        return state;
    },
});

export const shopCreateOp = createAsyncOp({
    name: 'shop/shop_create',
    successToastKey: 'shop:toast.shop_created',
    errorToastKey: 'shop:toast.shop_create_failed',
    commandType: 'shop/shops/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops' },
});

export const shopUpdateOp = createAsyncOp({
    name: 'shop/shop_update',
    successToastKey: 'shop:toast.shop_updated',
    errorToastKey: 'shop:toast.shop_update_failed',
    commandType: 'shop/shops/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}' },
});

export const shopPublishOp = createAsyncOp({
    name: 'shop/shop_publish',
    successToastKey: 'shop:toast.shop_published',
    errorToastKey: 'shop:toast.shop_publish_failed',
    commandType: 'shop/shops/publish_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/publish' },
});

export const shopSuspendOp = createAsyncOp({
    name: 'shop/shop_suspend',
    successToastKey: 'shop:toast.shop_suspended',
    errorToastKey: 'shop:toast.shop_suspend_failed',
    commandType: 'shop/shops/suspend_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/suspend' },
});

export const shopCategoriesListOp = createAsyncOp({
    name: 'shop/categories_list',
    errorToastKey: 'shop:toast.categories_load_failed',
    commandType: 'shop/categories/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/categories' },
});

export const shopCategoryCreateOp = createAsyncOp({
    name: 'shop/category_create',
    successToastKey: 'shop:toast.category_created',
    errorToastKey: 'shop:toast.category_create_failed',
    commandType: 'shop/categories/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/categories' },
});

export const shopCategoryUpdateOp = createAsyncOp({
    name: 'shop/category_update',
    errorToastKey: 'shop:toast.category_update_failed',
    commandType: 'shop/categories/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/categories/{shop_category_id}' },
});

export const shopCategoryRemoveOp = createAsyncOp({
    name: 'shop/category_remove',
    errorToastKey: 'shop:toast.category_remove_failed',
    commandType: 'shop/categories/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/categories/{shop_category_id}' },
});

export const shopProductsListOp = createAsyncOp({
    name: 'shop/products_list',
    errorToastKey: 'shop:toast.products_load_failed',
    commandType: 'shop/products/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/products' },
});

export const shopProductCreateOp = createAsyncOp({
    name: 'shop/product_create',
    successToastKey: 'shop:toast.product_created',
    errorToastKey: 'shop:toast.product_create_failed',
    commandType: 'shop/products/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/products' },
});

export const shopProductUpdateOp = createAsyncOp({
    name: 'shop/product_update',
    errorToastKey: 'shop:toast.product_update_failed',
    commandType: 'shop/products/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/products/{shop_product_id}' },
});

export const shopProductsImportOp = createAsyncOp({
    name: 'shop/products_import',
    successToastKey: 'shop:toast.products_imported',
    errorToastKey: 'shop:toast.products_import_failed',
    commandType: 'shop/products/import_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/products/import' },
});

export const shopProductRemoveOp = createAsyncOp({
    name: 'shop/product_remove',
    errorToastKey: 'shop:toast.product_remove_failed',
    commandType: 'shop/products/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/products/{shop_product_id}' },
});

export const shopOrdersListOp: AsyncOpFactory = createAsyncOp({
    name: 'shop/orders_list',
    errorToastKey: 'shop:toast.orders_load_failed',
    commandType: 'shop/orders/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/orders' },
    extraEffect: async (event, ctx): Promise<boolean> => {
        if (event.type !== 'shop/order/created' && event.type !== 'shop/order/status_changed') {
            return false;
        }
        const pushedShopId = isPlainRecord(event.payload) ? event.payload.shop_id : undefined;
        return rerunLastRequest(ctx, shopOrdersListOp, {
            when: (payload) =>
                isPlainRecord(payload)
                && typeof pushedShopId === 'string'
                && payload.shop_id === pushedShopId,
        });
    },
});

export const shopOrderSetStatusOp = createAsyncOp({
    name: 'shop/order_set_status',
    errorToastKey: 'shop:toast.order_status_failed',
    commandType: 'shop/orders/set_status_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/orders/{shop_order_id}/status' },
});

export const shopDomainAddOp = createAsyncOp({
    name: 'shop/domain_add',
    successToastKey: 'shop:toast.domain_added',
    errorToastKey: 'shop:toast.domain_add_failed',
    commandType: 'shop/domains/add_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/domains' },
});

export const shopDomainProvisionOp = createAsyncOp({
    name: 'shop/domain_provision',
    errorToastKey: 'shop:toast.domain_provision_failed',
    commandType: 'shop/domains/provision_requested',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/domains/{shop_domain_id}/provision' },
});

export const shopAiDescribeOp = createAsyncOp({
    name: 'shop/ai_describe',
    errorToastKey: 'shop:toast.ai_describe_failed',
    commandType: 'shop/ai/describe_requested',
    transport: 'ws',
    wsTimeoutMs: 60_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/describe' },
});

export const shopAiEnhancePhotoOp = createAsyncOp({
    name: 'shop/ai_enhance_photo',
    errorToastKey: 'shop:toast.ai_enhance_failed',
    commandType: 'shop/ai/enhance_photo_requested',
    transport: 'ws',
    wsTimeoutMs: 120_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/enhance-photo' },
});

export const shopAiGeneratePhotoOp = createAsyncOp({
    name: 'shop/ai_generate_photo',
    errorToastKey: 'shop:toast.ai_generate_failed',
    commandType: 'shop/ai/generate_photo_requested',
    transport: 'ws',
    wsTimeoutMs: 120_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/generate-photo' },
});

export const shopTelegramConnectOp = createAsyncOp({
    name: 'shop/telegram_connect',
    errorToastKey: 'shop:toast.telegram_connect_failed',
    commandType: 'shop/telegram/connect_requested',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/telegram/connect' },
});

export const shopTelegramDisconnectOp = createAsyncOp({
    name: 'shop/telegram_disconnect',
    errorToastKey: 'shop:toast.telegram_disconnect_failed',
    commandType: 'shop/telegram/disconnect_requested',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/telegram/disconnect' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'shop/shops': typeof shopShopsResource;
        'shop/shop_create': typeof shopCreateOp;
        'shop/shop_update': typeof shopUpdateOp;
        'shop/shop_publish': typeof shopPublishOp;
        'shop/shop_suspend': typeof shopSuspendOp;
        'shop/categories_list': typeof shopCategoriesListOp;
        'shop/category_create': typeof shopCategoryCreateOp;
        'shop/category_update': typeof shopCategoryUpdateOp;
        'shop/category_remove': typeof shopCategoryRemoveOp;
        'shop/products_list': typeof shopProductsListOp;
        'shop/product_create': typeof shopProductCreateOp;
        'shop/product_update': typeof shopProductUpdateOp;
        'shop/product_remove': typeof shopProductRemoveOp;
        'shop/products_import': typeof shopProductsImportOp;
        'shop/orders_list': typeof shopOrdersListOp;
        'shop/order_set_status': typeof shopOrderSetStatusOp;
        'shop/domain_add': typeof shopDomainAddOp;
        'shop/domain_provision': typeof shopDomainProvisionOp;
        'shop/ai_describe': typeof shopAiDescribeOp;
        'shop/ai_enhance_photo': typeof shopAiEnhancePhotoOp;
        'shop/ai_generate_photo': typeof shopAiGeneratePhotoOp;
        'shop/telegram_connect': typeof shopTelegramConnectOp;
        'shop/telegram_disconnect': typeof shopTelegramDisconnectOp;
    }
}
