/**
 * Фабрики событий магазина: каждая команда — `op_*` через WS RPC + REST-зеркало.
 *
 * Ресурс `shop/shops` — коллекция магазинов компании; категории, товары и
 * заказы адресуются `shop_id` из маршрута, поэтому они — async ops, а не
 * коллекции.
 */

import { createAsyncOp, createResourceCollection, rerunLastRequest } from '@platform/lib/events/index.js';
import type { AsyncOpFactory } from '@platform/lib/events/factories/async-op.js';
import type { ResourceCollectionSlice } from '@platform/lib/events/factories/resource-collection.js';
import { isPlatformEventType, isPlainRecord } from '@platform/lib/events/payload.js';
import type { ShopResponse, ShopShopEventPayload, ShopStatus } from '@platform/lib/events/wire/shop.gen.js';

const SHOP_STATUSES: readonly ShopStatus[] = ['draft', 'published', 'suspended'];

export const SHOP_SHOP_EVENTS = [
    'shop/shop/created',
    'shop/shop/updated',
    'shop/shop/published',
] as const;

function mergeShopSummary(
    state: ResourceCollectionSlice<ShopResponse>,
    payload: ShopShopEventPayload,
): ResourceCollectionSlice<ShopResponse> {
    const shopId = payload.shop_id;
    if (typeof shopId !== 'string') {
        throw new Error('shop/shop/*: payload.shop_id required');
    }
    const index = state.items.findIndex((item) => item && item.shop_id === shopId);
    const current = state.items[index];
    if (index === -1 || current === undefined) {
        return state;
    }
    const patch: Partial<Pick<ShopResponse, 'slug' | 'status'>> = {};
    if (typeof payload.slug === 'string') {
        patch.slug = payload.slug;
    }
    if (SHOP_STATUSES.includes(payload.status)) {
        patch.status = payload.status;
    }
    const merged: ShopResponse = { ...current, ...patch };
    const items = state.items.map((item, position) =>
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
        if (isPlatformEventType(event, SHOP_SHOP_EVENTS)) {
            return mergeShopSummary(state, event.payload);
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

export const shopBadgeIconsListOp = createAsyncOp({
    name: 'shop/badge_icons_list',
    silent: true,
    commandType: 'shop/badge_icons/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/badge-icons' },
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
    silent: true,
    commandType: 'shop/categories/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/categories' },
    extraEffect: async (event, ctx): Promise<boolean> => {
        if (!isPlatformEventType(event, 'shop/catalog/changed')) {
            return false;
        }
        const pushedShopId = event.payload.shop_id;
        return rerunLastRequest(ctx, shopCategoriesListOp, {
            when: (payload) =>
                isPlainRecord(payload)
                && payload.shop_id === pushedShopId,
        });
    },
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
    successToastKey: 'shop:toast.category_updated',
    errorToastKey: 'shop:toast.category_update_failed',
    commandType: 'shop/categories/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/categories/{shop_category_id}' },
});

export const shopCategoryRemoveOp = createAsyncOp({
    name: 'shop/category_remove',
    successToastKey: 'shop:toast.category_removed',
    errorToastKey: 'shop:toast.category_remove_failed',
    commandType: 'shop/categories/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/categories/{shop_category_id}' },
});

export const shopCategoriesReorderOp = createAsyncOp({
    name: 'shop/categories_reorder',
    successToastKey: 'shop:toast.categories_reordered',
    errorToastKey: 'shop:toast.category_reorder_failed',
    commandType: 'shop/categories/reorder_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/categories/reorder' },
});

export const shopProductsListOp = createAsyncOp({
    name: 'shop/products_list',
    silent: true,
    commandType: 'shop/products/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/products' },
    extraEffect: async (event, ctx): Promise<boolean> => {
        if (!isPlatformEventType(event, 'shop/catalog/changed')) {
            return false;
        }
        const pushedShopId = event.payload.shop_id;
        return rerunLastRequest(ctx, shopProductsListOp, {
            when: (payload) =>
                isPlainRecord(payload)
                && payload.shop_id === pushedShopId,
        });
    },
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
    successToastKey: 'shop:toast.product_updated',
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

export const shopProductsReorderOp = createAsyncOp({
    name: 'shop/products_reorder',
    successToastKey: 'shop:toast.products_reordered',
    errorToastKey: 'shop:toast.product_reorder_failed',
    commandType: 'shop/products/reorder_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/products/reorder' },
});

export const shopProductRemoveOp = createAsyncOp({
    name: 'shop/product_remove',
    successToastKey: 'shop:toast.product_removed',
    errorToastKey: 'shop:toast.product_remove_failed',
    commandType: 'shop/products/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/products/{shop_product_id}' },
});

export const shopOrdersListOp: AsyncOpFactory = createAsyncOp({
    name: 'shop/orders_list',
    silent: true,
    commandType: 'shop/orders/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/orders' },
    extraEffect: async (event, ctx): Promise<boolean> => {
        if (!isPlatformEventType(event, ['shop/order/created', 'shop/order/status_changed'])) {
            return false;
        }
        const pushedShopId = event.payload.shop_id;
        return rerunLastRequest(ctx, shopOrdersListOp, {
            when: (payload) =>
                isPlainRecord(payload)
                && payload.shop_id === pushedShopId,
        });
    },
});

export const shopOrderSetStatusOp = createAsyncOp({
    name: 'shop/order_set_status',
    successToastKey: 'shop:toast.order_status_updated',
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
    successToastKey: 'shop:toast.domain_provisioned',
    errorToastKey: 'shop:toast.domain_provision_failed',
    commandType: 'shop/domains/provision_requested',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/domains/{shop_domain_id}/provision' },
});

export const shopAiDescribeOp = createAsyncOp({
    name: 'shop/ai_describe',
    successToastKey: 'shop:toast.ai_describe_done',
    errorToastKey: 'shop:toast.ai_describe_failed',
    commandType: 'shop/ai/describe_requested',
    transport: 'ws',
    wsTimeoutMs: 60_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/describe' },
});

export const shopAiEnhancePhotoOp = createAsyncOp({
    name: 'shop/ai_enhance_photo',
    successToastKey: 'shop:toast.ai_photo_enhanced',
    errorToastKey: 'shop:toast.ai_enhance_failed',
    commandType: 'shop/ai/enhance_photo_requested',
    transport: 'ws',
    wsTimeoutMs: 120_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/enhance-photo' },
});

export const shopAiGeneratePhotoOp = createAsyncOp({
    name: 'shop/ai_generate_photo',
    successToastKey: 'shop:toast.ai_photo_generated',
    errorToastKey: 'shop:toast.ai_generate_failed',
    commandType: 'shop/ai/generate_photo_requested',
    transport: 'ws',
    wsTimeoutMs: 120_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/generate-photo' },
});

export const shopAiDescribeShopOp = createAsyncOp({
    name: 'shop/ai_describe_shop',
    successToastKey: 'shop:toast.ai_describe_done',
    errorToastKey: 'shop:toast.ai_describe_failed',
    commandType: 'shop/ai/describe_shop_requested',
    transport: 'ws',
    wsTimeoutMs: 60_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/describe-shop' },
});

export const shopAiGenerateCoverOp = createAsyncOp({
    name: 'shop/ai_generate_cover',
    successToastKey: 'shop:toast.ai_photo_generated',
    errorToastKey: 'shop:toast.ai_generate_failed',
    commandType: 'shop/ai/generate_cover_requested',
    transport: 'ws',
    wsTimeoutMs: 120_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/generate-cover' },
});

export const shopAiGenerateLogoOp = createAsyncOp({
    name: 'shop/ai_generate_logo',
    successToastKey: 'shop:toast.ai_photo_generated',
    errorToastKey: 'shop:toast.ai_generate_failed',
    commandType: 'shop/ai/generate_logo_requested',
    transport: 'ws',
    wsTimeoutMs: 120_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/generate-logo' },
});

export const shopAiAutofillOp = createAsyncOp({
    name: 'shop/ai_autofill',
    successToastKey: 'shop:toast.ai_autofill_done',
    errorToastKey: 'shop:toast.ai_generate_failed',
    commandType: 'shop/ai/autofill_requested',
    transport: 'ws',
    wsTimeoutMs: 180_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/autofill' },
});

export const shopAiParseMenuOp = createAsyncOp({
    name: 'shop/ai_parse_menu',
    successToastKey: 'shop:toast.ai_parse_done',
    errorToastKey: 'shop:toast.ai_parse_failed',
    commandType: 'shop/ai/parse_menu_requested',
    transport: 'ws',
    wsTimeoutMs: 120_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/parse-menu' },
});

export const shopAiDescribeBatchOp = createAsyncOp({
    name: 'shop/ai_describe_batch',
    successToastKey: 'shop:toast.ai_batch_started',
    errorToastKey: 'shop:toast.ai_batch_failed',
    commandType: 'shop/ai/describe_batch_requested',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/describe-all' },
});

export const shopModifierGroupsListOp: AsyncOpFactory = createAsyncOp({
    name: 'shop/modifier_groups_list',
    silent: true,
    commandType: 'shop/modifiers/groups/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/modifier-groups' },
    extraEffect: async (event, ctx): Promise<boolean> => {
        if (!isPlatformEventType(event, 'shop/catalog/changed')) {
            return false;
        }
        const pushedShopId = event.payload.shop_id;
        return rerunLastRequest(ctx, shopModifierGroupsListOp, {
            when: (payload) =>
                isPlainRecord(payload)
                && payload.shop_id === pushedShopId,
        });
    },
});

export const shopModifierGroupCreateOp = createAsyncOp({
    name: 'shop/modifier_group_create',
    successToastKey: 'shop:toast.modifier_group_created',
    errorToastKey: 'shop:toast.modifier_group_failed',
    commandType: 'shop/modifiers/groups/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/modifier-groups' },
});

export const shopModifierGroupUpdateOp = createAsyncOp({
    name: 'shop/modifier_group_update',
    successToastKey: 'shop:toast.modifier_group_updated',
    errorToastKey: 'shop:toast.modifier_group_failed',
    commandType: 'shop/modifiers/groups/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/modifier-groups/{group_id}' },
});

export const shopModifierGroupRemoveOp = createAsyncOp({
    name: 'shop/modifier_group_remove',
    successToastKey: 'shop:toast.modifier_group_removed',
    errorToastKey: 'shop:toast.modifier_group_failed',
    commandType: 'shop/modifiers/groups/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/modifier-groups/{group_id}' },
});

export const shopModifierOptionCreateOp = createAsyncOp({
    name: 'shop/modifier_option_create',
    successToastKey: 'shop:toast.modifier_option_created',
    errorToastKey: 'shop:toast.modifier_option_failed',
    commandType: 'shop/modifiers/options/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/modifier-groups/{group_id}/options' },
});

export const shopModifierOptionUpdateOp = createAsyncOp({
    name: 'shop/modifier_option_update',
    successToastKey: 'shop:toast.modifier_option_updated',
    errorToastKey: 'shop:toast.modifier_option_failed',
    commandType: 'shop/modifiers/options/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/modifier-options/{option_id}' },
});

export const shopModifierOptionRemoveOp = createAsyncOp({
    name: 'shop/modifier_option_remove',
    successToastKey: 'shop:toast.modifier_option_removed',
    errorToastKey: 'shop:toast.modifier_option_failed',
    commandType: 'shop/modifiers/options/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/modifier-options/{option_id}' },
});

export const shopProductModifierAttachOp = createAsyncOp({
    name: 'shop/product_modifier_attach',
    successToastKey: 'shop:toast.modifier_attached',
    errorToastKey: 'shop:toast.modifier_attach_failed',
    commandType: 'shop/products/modifiers/attach_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/products/{product_id}/modifier-groups/{group_id}' },
});

export const shopProductModifierDetachOp = createAsyncOp({
    name: 'shop/product_modifier_detach',
    successToastKey: 'shop:toast.modifier_detached',
    errorToastKey: 'shop:toast.modifier_attach_failed',
    commandType: 'shop/products/modifiers/detach_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/products/{product_id}/modifier-groups/{group_id}' },
});

export const shopAiSuggestOptionsOp = createAsyncOp({
    name: 'shop/ai_suggest_options',
    successToastKey: 'shop:toast.ai_suggest_done',
    errorToastKey: 'shop:toast.ai_suggest_failed',
    commandType: 'shop/ai/suggest_options_requested',
    transport: 'ws',
    wsTimeoutMs: 60_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/ai/suggest-options' },
});

export const shopPromosListOp: AsyncOpFactory = createAsyncOp({
    name: 'shop/promos_list',
    silent: true,
    commandType: 'shop/promos/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/promos' },
    extraEffect: async (event, ctx): Promise<boolean> => {
        if (!isPlatformEventType(event, 'shop/catalog/changed')) {
            return false;
        }
        const pushedShopId = event.payload.shop_id;
        return rerunLastRequest(ctx, shopPromosListOp, {
            when: (payload) =>
                isPlainRecord(payload)
                && payload.shop_id === pushedShopId,
        });
    },
});

export const shopPromoCreateOp = createAsyncOp({
    name: 'shop/promo_create',
    successToastKey: 'shop:toast.promo_created',
    errorToastKey: 'shop:toast.promo_failed',
    commandType: 'shop/promos/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/promos' },
});

export const shopPromoUpdateOp = createAsyncOp({
    name: 'shop/promo_update',
    successToastKey: 'shop:toast.promo_updated',
    errorToastKey: 'shop:toast.promo_failed',
    commandType: 'shop/promos/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/promos/{shop_promo_id}' },
});

export const shopPromoRemoveOp = createAsyncOp({
    name: 'shop/promo_remove',
    successToastKey: 'shop:toast.promo_removed',
    errorToastKey: 'shop:toast.promo_failed',
    commandType: 'shop/promos/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/promos/{shop_promo_id}' },
});

export const shopTablesListOp: AsyncOpFactory = createAsyncOp({
    name: 'shop/tables_list',
    silent: true,
    commandType: 'shop/tables/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/tables' },
});

export const shopTableCreateOp = createAsyncOp({
    name: 'shop/table_create',
    successToastKey: 'shop:toast.table_created',
    errorToastKey: 'shop:toast.table_failed',
    commandType: 'shop/tables/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/tables' },
});

export const shopTableUpdateOp = createAsyncOp({
    name: 'shop/table_update',
    successToastKey: 'shop:toast.table_updated',
    errorToastKey: 'shop:toast.table_failed',
    commandType: 'shop/tables/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/tables/{shop_table_id}' },
});

export const shopTableRemoveOp = createAsyncOp({
    name: 'shop/table_remove',
    successToastKey: 'shop:toast.table_removed',
    errorToastKey: 'shop:toast.table_failed',
    commandType: 'shop/tables/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/tables/{shop_table_id}' },
});

export const shopShelvesListOp = createAsyncOp({
    name: 'shop/shelves_list',
    silent: true,
    commandType: 'shop/shelves/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/shelves' },
    extraEffect: async (event, ctx): Promise<boolean> => {
        if (!isPlatformEventType(event, 'shop/catalog/changed')) {
            return false;
        }
        const pushedShopId = event.payload.shop_id;
        return rerunLastRequest(ctx, shopShelvesListOp, {
            when: (payload) =>
                isPlainRecord(payload)
                && payload.shop_id === pushedShopId,
        });
    },
});

export const shopShelfCreateOp = createAsyncOp({
    name: 'shop/shelf_create',
    successToastKey: 'shop:toast.shelf_created',
    errorToastKey: 'shop:toast.shelf_failed',
    commandType: 'shop/shelves/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/shelves' },
});

export const shopShelfUpdateOp = createAsyncOp({
    name: 'shop/shelf_update',
    successToastKey: 'shop:toast.shelf_updated',
    errorToastKey: 'shop:toast.shelf_failed',
    commandType: 'shop/shelves/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/shelves/{shop_shelf_id}' },
});

export const shopShelvesReorderOp = createAsyncOp({
    name: 'shop/shelves_reorder',
    errorToastKey: 'shop:toast.shelf_failed',
    commandType: 'shop/shelves/reorder_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PUT', path: '/shop/api/v1/shops/{shop_id}/shelves/order' },
});

export const shopShelfRemoveOp = createAsyncOp({
    name: 'shop/shelf_remove',
    successToastKey: 'shop:toast.shelf_removed',
    errorToastKey: 'shop:toast.shelf_failed',
    commandType: 'shop/shelves/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/shelves/{shop_shelf_id}' },
});

export const shopBannersListOp = createAsyncOp({
    name: 'shop/banners_list',
    silent: true,
    commandType: 'shop/banners/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/banners' },
    extraEffect: async (event, ctx): Promise<boolean> => {
        if (!isPlatformEventType(event, 'shop/catalog/changed')) {
            return false;
        }
        const pushedShopId = event.payload.shop_id;
        return rerunLastRequest(ctx, shopBannersListOp, {
            when: (payload) =>
                isPlainRecord(payload)
                && payload.shop_id === pushedShopId,
        });
    },
});

export const shopBannerCreateOp = createAsyncOp({
    name: 'shop/banner_create',
    successToastKey: 'shop:toast.banner_created',
    errorToastKey: 'shop:toast.banner_failed',
    commandType: 'shop/banners/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/banners' },
});

export const shopBannerUpdateOp = createAsyncOp({
    name: 'shop/banner_update',
    successToastKey: 'shop:toast.banner_updated',
    errorToastKey: 'shop:toast.banner_failed',
    commandType: 'shop/banners/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/banners/{shop_banner_id}' },
});

export const shopBannersReorderOp = createAsyncOp({
    name: 'shop/banners_reorder',
    errorToastKey: 'shop:toast.banner_failed',
    commandType: 'shop/banners/reorder_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PUT', path: '/shop/api/v1/shops/{shop_id}/banners/order' },
});

export const shopBannerRemoveOp = createAsyncOp({
    name: 'shop/banner_remove',
    successToastKey: 'shop:toast.banner_removed',
    errorToastKey: 'shop:toast.banner_failed',
    commandType: 'shop/banners/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/banners/{shop_banner_id}' },
});

export const shopDemosSeedOp = createAsyncOp({
    name: 'shop/demos_seed',
    successToastKey: 'shop:toast.demos_seed_scheduled',
    errorToastKey: 'shop:toast.demos_seed_failed',
    commandType: 'shop/demos/seed_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/demos/seed' },
});

export const shopTelegramConnectOp = createAsyncOp({
    name: 'shop/telegram_connect',
    successToastKey: 'shop:toast.telegram_connected',
    errorToastKey: 'shop:toast.telegram_connect_failed',
    commandType: 'shop/telegram/connect_requested',
    transport: 'ws',
    wsTimeoutMs: 30_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/telegram/connect' },
});

export const shopTelegramDisconnectOp = createAsyncOp({
    name: 'shop/telegram_disconnect',
    successToastKey: 'shop:toast.telegram_disconnected',
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
        'shop/badge_icons_list': typeof shopBadgeIconsListOp;
        'shop/categories_list': typeof shopCategoriesListOp;
        'shop/category_create': typeof shopCategoryCreateOp;
        'shop/category_update': typeof shopCategoryUpdateOp;
        'shop/category_remove': typeof shopCategoryRemoveOp;
        'shop/categories_reorder': typeof shopCategoriesReorderOp;
        'shop/products_list': typeof shopProductsListOp;
        'shop/product_create': typeof shopProductCreateOp;
        'shop/product_update': typeof shopProductUpdateOp;
        'shop/product_remove': typeof shopProductRemoveOp;
        'shop/products_reorder': typeof shopProductsReorderOp;
        'shop/products_import': typeof shopProductsImportOp;
        'shop/orders_list': typeof shopOrdersListOp;
        'shop/order_set_status': typeof shopOrderSetStatusOp;
        'shop/domain_add': typeof shopDomainAddOp;
        'shop/domain_provision': typeof shopDomainProvisionOp;
        'shop/ai_describe': typeof shopAiDescribeOp;
        'shop/ai_enhance_photo': typeof shopAiEnhancePhotoOp;
        'shop/ai_generate_photo': typeof shopAiGeneratePhotoOp;
        'shop/ai_describe_shop': typeof shopAiDescribeShopOp;
        'shop/ai_generate_cover': typeof shopAiGenerateCoverOp;
        'shop/ai_generate_logo': typeof shopAiGenerateLogoOp;
        'shop/ai_autofill': typeof shopAiAutofillOp;
        'shop/ai_parse_menu': typeof shopAiParseMenuOp;
        'shop/ai_describe_batch': typeof shopAiDescribeBatchOp;
        'shop/modifier_groups_list': typeof shopModifierGroupsListOp;
        'shop/modifier_group_create': typeof shopModifierGroupCreateOp;
        'shop/modifier_group_update': typeof shopModifierGroupUpdateOp;
        'shop/modifier_group_remove': typeof shopModifierGroupRemoveOp;
        'shop/modifier_option_create': typeof shopModifierOptionCreateOp;
        'shop/modifier_option_update': typeof shopModifierOptionUpdateOp;
        'shop/modifier_option_remove': typeof shopModifierOptionRemoveOp;
        'shop/product_modifier_attach': typeof shopProductModifierAttachOp;
        'shop/product_modifier_detach': typeof shopProductModifierDetachOp;
        'shop/ai_suggest_options': typeof shopAiSuggestOptionsOp;
        'shop/promos_list': typeof shopPromosListOp;
        'shop/promo_create': typeof shopPromoCreateOp;
        'shop/promo_update': typeof shopPromoUpdateOp;
        'shop/promo_remove': typeof shopPromoRemoveOp;
        'shop/tables_list': typeof shopTablesListOp;
        'shop/table_create': typeof shopTableCreateOp;
        'shop/table_update': typeof shopTableUpdateOp;
        'shop/table_remove': typeof shopTableRemoveOp;
        'shop/telegram_connect': typeof shopTelegramConnectOp;
        'shop/telegram_disconnect': typeof shopTelegramDisconnectOp;
        'shop/demos_seed': typeof shopDemosSeedOp;
        'shop/shelves_list': typeof shopShelvesListOp;
        'shop/shelf_create': typeof shopShelfCreateOp;
        'shop/shelf_update': typeof shopShelfUpdateOp;
        'shop/shelves_reorder': typeof shopShelvesReorderOp;
        'shop/shelf_remove': typeof shopShelfRemoveOp;
        'shop/banners_list': typeof shopBannersListOp;
        'shop/banner_create': typeof shopBannerCreateOp;
        'shop/banner_update': typeof shopBannerUpdateOp;
        'shop/banners_reorder': typeof shopBannersReorderOp;
        'shop/banner_remove': typeof shopBannerRemoveOp;
    }
}
