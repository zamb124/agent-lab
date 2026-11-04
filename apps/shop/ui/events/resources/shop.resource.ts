/**
 * Фабрики событий магазина: каждая команда — `op_*` через WS RPC + REST-зеркало.
 *
 * Ресурс `shop/shops` — коллекция магазинов компании; каталог блюд, меню,
 * импорты и заказы адресуются `shop_id` из маршрута, поэтому они — async ops,
 * а не коллекции. Списки перечитываются push-событиями `shop/catalog/changed`,
 * `shop/menu/updated` и `worktracker/work_item/*` своего заведения.
 */

import { createAsyncOp, createResourceCollection, rerunLastRequest } from '@platform/lib/events/index.js';
import type { AsyncOpFactory } from '@platform/lib/events/factories/async-op.js';
import type { ResourceCollectionSlice } from '@platform/lib/events/factories/resource-collection.js';
import { isPlatformEventType, isPlainRecord } from '@platform/lib/events/payload.js';
import { WORK_ITEM_EVENTS } from '@platform/lib/events/resources/work-items.resource.js';
import type { ShopResponse, ShopShopEventPayload, ShopStatus } from '@platform/lib/events/wire/shop.gen.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';

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

/** Последний запрос op адресован заведению `shopId`. */
function forShop(shopId: string): (payload: unknown) => boolean {
    return (payload) => isPlainRecord(payload) && payload.shop_id === shopId;
}

/** `shop_id` запроса из `<op>/succeeded` (`{ result, request }`); `null` — другой контракт. */
function succeededShopId(event: PlatformEvent, succeededType: string): string | null {
    if (event.type !== succeededType || !isPlainRecord(event.payload)) {
        return null;
    }
    const request = event.payload.request;
    return isPlainRecord(request) && typeof request.shop_id === 'string' ? request.shop_id : null;
}

export const shopMenusListOp = createAsyncOp({
    name: 'shop/menus_list',
    silent: true,
    commandType: 'shop/menus/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/menus' },
    extraEffect: async (event, ctx): Promise<boolean> => {
        if (isPlatformEventType(event, ['shop/menu/updated', 'shop/catalog/changed'])) {
            return rerunLastRequest(ctx, shopMenusListOp, { when: forShop(event.payload.shop_id) });
        }
        const reorderedShopId = succeededShopId(event, shopMenusReorderOp.events.SUCCEEDED);
        if (reorderedShopId !== null) {
            return rerunLastRequest(ctx, shopMenusListOp, { when: forShop(reorderedShopId) });
        }
        return false;
    },
});

export const shopMenuCreateOp = createAsyncOp({
    name: 'shop/menu_create',
    successToastKey: 'shop:toast.menu_created',
    errorToastKey: 'shop:toast.menu_create_failed',
    commandType: 'shop/menus/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menus' },
});

export const shopMenuUpdateOp = createAsyncOp({
    name: 'shop/menu_update',
    successToastKey: 'shop:toast.menu_updated',
    errorToastKey: 'shop:toast.menu_update_failed',
    commandType: 'shop/menus/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/menus/{shop_menu_id}' },
});

export const shopMenusReorderOp = createAsyncOp({
    name: 'shop/menus_reorder',
    successToastKey: 'shop:toast.menus_reordered',
    errorToastKey: 'shop:toast.menus_reorder_failed',
    commandType: 'shop/menus/reorder_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menus/reorder' },
});

export const shopMenuSetStatusOp = createAsyncOp({
    name: 'shop/menu_set_status',
    successToastKey: 'shop:toast.menu_status_updated',
    errorToastKey: 'shop:toast.menu_status_failed',
    commandType: 'shop/menus/set_status_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menus/{shop_menu_id}/status' },
});

export const shopMenuRemoveOp = createAsyncOp({
    name: 'shop/menu_remove',
    successToastKey: 'shop:toast.menu_removed',
    errorToastKey: 'shop:toast.menu_remove_failed',
    commandType: 'shop/menus/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/menus/{shop_menu_id}' },
});

export const shopMenuSectionCreateOp = createAsyncOp({
    name: 'shop/menu_section_create',
    successToastKey: 'shop:toast.section_created',
    errorToastKey: 'shop:toast.section_create_failed',
    commandType: 'shop/menu_sections/create_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menus/{shop_menu_id}/sections' },
});

export const shopMenuSectionUpdateOp = createAsyncOp({
    name: 'shop/menu_section_update',
    successToastKey: 'shop:toast.section_updated',
    errorToastKey: 'shop:toast.section_update_failed',
    commandType: 'shop/menu_sections/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/menu-sections/{shop_menu_section_id}' },
});

export const shopMenuSectionRemoveOp = createAsyncOp({
    name: 'shop/menu_section_remove',
    successToastKey: 'shop:toast.section_removed',
    errorToastKey: 'shop:toast.section_remove_failed',
    commandType: 'shop/menu_sections/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/menu-sections/{shop_menu_section_id}' },
});

export const shopMenuSectionsReorderOp = createAsyncOp({
    name: 'shop/menu_sections_reorder',
    successToastKey: 'shop:toast.sections_reordered',
    errorToastKey: 'shop:toast.sections_reorder_failed',
    commandType: 'shop/menu_sections/reorder_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menus/{shop_menu_id}/sections/reorder' },
});

export const shopMenuItemAddOp = createAsyncOp({
    name: 'shop/menu_item_add',
    successToastKey: 'shop:toast.menu_item_added',
    errorToastKey: 'shop:toast.menu_item_add_failed',
    commandType: 'shop/menu_items/add_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menus/{shop_menu_id}/items' },
});

export const shopMenuItemUpdateOp = createAsyncOp({
    name: 'shop/menu_item_update',
    successToastKey: 'shop:toast.menu_item_updated',
    errorToastKey: 'shop:toast.menu_item_update_failed',
    commandType: 'shop/menu_items/update_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'PATCH', path: '/shop/api/v1/shops/{shop_id}/menu-items/{shop_menu_item_id}' },
});

export const shopMenuItemMoveOp = createAsyncOp({
    name: 'shop/menu_item_move',
    successToastKey: 'shop:toast.menu_item_moved',
    errorToastKey: 'shop:toast.menu_item_move_failed',
    commandType: 'shop/menu_items/move_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menu-items/{shop_menu_item_id}/move' },
});

export const shopMenuItemRemoveOp = createAsyncOp({
    name: 'shop/menu_item_remove',
    successToastKey: 'shop:toast.menu_item_removed',
    errorToastKey: 'shop:toast.menu_item_remove_failed',
    commandType: 'shop/menu_items/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/menu-items/{shop_menu_item_id}' },
});

export const shopMenuItemsReorderOp = createAsyncOp({
    name: 'shop/menu_items_reorder',
    successToastKey: 'shop:toast.menu_items_reordered',
    errorToastKey: 'shop:toast.menu_items_reorder_failed',
    commandType: 'shop/menu_items/reorder_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menu-items/reorder' },
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

export const shopProductRemoveOp = createAsyncOp({
    name: 'shop/product_remove',
    successToastKey: 'shop:toast.product_removed',
    errorToastKey: 'shop:toast.product_remove_failed',
    commandType: 'shop/products/remove_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'DELETE', path: '/shop/api/v1/shops/{shop_id}/products/{shop_product_id}' },
});

export const shopProductVerifyOp = createAsyncOp({
    name: 'shop/product_verify',
    successToastKey: 'shop:toast.product_verified',
    errorToastKey: 'shop:toast.product_verify_failed',
    commandType: 'shop/products/verify_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/products/{shop_product_id}/verify' },
});

export const shopProductSimilarListOp = createAsyncOp({
    name: 'shop/product_similar_list',
    silent: true,
    commandType: 'shop/products/similar_list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/products/{shop_product_id}/similar' },
});

export const shopProductMergeOp = createAsyncOp({
    name: 'shop/product_merge',
    successToastKey: 'shop:toast.product_merged',
    errorToastKey: 'shop:toast.product_merge_failed',
    commandType: 'shop/products/merge_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/products/{shop_product_id}/merge' },
});

export const shopProductDismissSimilarOp = createAsyncOp({
    name: 'shop/product_dismiss_similar',
    successToastKey: 'shop:toast.similar_dismissed',
    errorToastKey: 'shop:toast.similar_dismiss_failed',
    commandType: 'shop/products/dismiss_similar_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/products/{shop_product_id}/dismiss-similar' },
});

export const shopProductsEnrichOp = createAsyncOp({
    name: 'shop/products_enrich',
    successToastKey: 'shop:toast.enrich_started',
    errorToastKey: 'shop:toast.enrich_failed',
    commandType: 'shop/products/enrich_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/products/enrich' },
});

export const shopMenuImportStartOp = createAsyncOp({
    name: 'shop/menu_import_start',
    successToastKey: 'shop:toast.menu_import_started',
    errorToastKey: 'shop:toast.menu_import_failed',
    commandType: 'shop/menu_imports/start_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menu-imports' },
});

export const shopMenuTemplateBuildOp = createAsyncOp({
    name: 'shop/menu_template_build',
    successToastKey: 'shop:toast.menu_template_started',
    errorToastKey: 'shop:toast.menu_template_failed',
    commandType: 'shop/menu_templates/build_requested',
    transport: 'ws',
    wsTimeoutMs: 15_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menu-templates' },
});

export const shopMenuFileImportRunOp = createAsyncOp({
    name: 'shop/menu_file_import_run',
    successToastKey: 'shop:toast.menu_file_import_done',
    errorToastKey: 'shop:toast.menu_file_import_failed',
    commandType: 'shop/menu_file_imports/run_requested',
    transport: 'ws',
    wsTimeoutMs: 120_000,
    restMirror: { method: 'POST', path: '/shop/api/v1/shops/{shop_id}/menu-file-imports' },
});

/** Заведения, к которым push WorkItem привязан ссылкой `ShopLink`. */
function workItemShopIds(event: PlatformEvent): string[] {
    if (!isPlatformEventType(event, WORK_ITEM_EVENTS)) {
        return [];
    }
    const workItem = event.payload.work_item;
    if (!isPlainRecord(workItem) || !Array.isArray(workItem.links)) {
        return [];
    }
    const ids: string[] = [];
    for (const link of workItem.links) {
        if (isPlainRecord(link) && link.link_kind === 'shop' && typeof link.shop_id === 'string') {
            ids.push(link.shop_id);
        }
    }
    return ids;
}

const AGENT_JOB_STARTED = [
    shopMenuImportStartOp.events.SUCCEEDED,
    shopMenuTemplateBuildOp.events.SUCCEEDED,
    shopProductsEnrichOp.events.SUCCEEDED,
    shopMenuFileImportRunOp.events.SUCCEEDED,
];

export const shopMenuImportsListOp = createAsyncOp({
    name: 'shop/menu_imports_list',
    silent: true,
    commandType: 'shop/menu_imports/list_requested',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    restMirror: { method: 'GET', path: '/shop/api/v1/shops/{shop_id}/menu-imports' },
    extraEffect: async (event, ctx): Promise<boolean> => {
        if (isPlatformEventType(event, 'shop/catalog/changed')) {
            return rerunLastRequest(ctx, shopMenuImportsListOp, { when: forShop(event.payload.shop_id) });
        }
        for (const shopId of workItemShopIds(event)) {
            if (rerunLastRequest(ctx, shopMenuImportsListOp, { when: forShop(shopId) })) {
                return true;
            }
        }
        for (const succeededType of AGENT_JOB_STARTED) {
            const startedShopId = succeededShopId(event, succeededType);
            if (startedShopId !== null) {
                return rerunLastRequest(ctx, shopMenuImportsListOp, { when: forShop(startedShopId) });
            }
        }
        return false;
    },
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
        'shop/products_list': typeof shopProductsListOp;
        'shop/product_create': typeof shopProductCreateOp;
        'shop/product_update': typeof shopProductUpdateOp;
        'shop/product_remove': typeof shopProductRemoveOp;
        'shop/product_verify': typeof shopProductVerifyOp;
        'shop/product_similar_list': typeof shopProductSimilarListOp;
        'shop/product_merge': typeof shopProductMergeOp;
        'shop/product_dismiss_similar': typeof shopProductDismissSimilarOp;
        'shop/products_enrich': typeof shopProductsEnrichOp;
        'shop/menus_list': typeof shopMenusListOp;
        'shop/menu_create': typeof shopMenuCreateOp;
        'shop/menu_update': typeof shopMenuUpdateOp;
        'shop/menus_reorder': typeof shopMenusReorderOp;
        'shop/menu_set_status': typeof shopMenuSetStatusOp;
        'shop/menu_remove': typeof shopMenuRemoveOp;
        'shop/menu_section_create': typeof shopMenuSectionCreateOp;
        'shop/menu_section_update': typeof shopMenuSectionUpdateOp;
        'shop/menu_section_remove': typeof shopMenuSectionRemoveOp;
        'shop/menu_sections_reorder': typeof shopMenuSectionsReorderOp;
        'shop/menu_item_add': typeof shopMenuItemAddOp;
        'shop/menu_item_update': typeof shopMenuItemUpdateOp;
        'shop/menu_item_move': typeof shopMenuItemMoveOp;
        'shop/menu_item_remove': typeof shopMenuItemRemoveOp;
        'shop/menu_items_reorder': typeof shopMenuItemsReorderOp;
        'shop/menu_imports_list': typeof shopMenuImportsListOp;
        'shop/menu_import_start': typeof shopMenuImportStartOp;
        'shop/menu_template_build': typeof shopMenuTemplateBuildOp;
        'shop/menu_file_import_run': typeof shopMenuFileImportRunOp;
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
        'shop/telegram_connect': typeof shopTelegramConnectOp;
        'shop/telegram_disconnect': typeof shopTelegramDisconnectOp;
    }
}
