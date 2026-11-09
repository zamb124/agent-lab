/**
 * Сжатые скриншоты для лендинга и продуктовых страниц.
 *
 * Источники — маркетинговый suite ``tests/ui/shots`` (Playwright, 2x PNG),
 * оптимизация — ``python -m scripts.tools.land_optimize`` (sips -Z 2400 → optimized/).
 * Старые кадры land/*.png тоже проходят через тот же конвейер.
 */
export const LAND_IMAGE_BASE = '/static/frontend/assets/images/land/optimized';

/** @param {string} locale */
export function landFlowsAbilityUrl(locale: string) {
    return locale === 'ru'
        ? `${LAND_IMAGE_BASE}/flows_ability-image_ru.png`
        : `${LAND_IMAGE_BASE}/flows_ability-image_en.png`;
}

export const landRagAbilityUrl = `${LAND_IMAGE_BASE}/rag.png`;
export const landNetworkleAbilityUrl = `${LAND_IMAGE_BASE}/networkle_ability-image_ru.png`;
export const landSyncAbilityUrl = `${LAND_IMAGE_BASE}/sync_ability-image_ru.png`;

// Маркетинговые кадры tests/ui/shots
export const landCrmGraphUrl = `${LAND_IMAGE_BASE}/crm-graph.png`;
export const landCrmNotesUrl = `${LAND_IMAGE_BASE}/crm-notes.png`;
export const landCrmEntitiesUrl = `${LAND_IMAGE_BASE}/crm-entities.png`;
export const landCrmTasksUrl = `${LAND_IMAGE_BASE}/crm-tasks.png`;

export const landFlowsEditorUrl = `${LAND_IMAGE_BASE}/flows-editor.png`;
export const landFlowsHomeUrl = `${LAND_IMAGE_BASE}/flows-home.png`;

export const landGeoOverviewUrl = `${LAND_IMAGE_BASE}/geo-overview.png`;
export const landGeoRouteLabUrl = `${LAND_IMAGE_BASE}/geo-route-lab.png`;
export const landGeoMapLabUrl = `${LAND_IMAGE_BASE}/geo-map-lab.png`;

export const landOfficeDocumentsUrl = `${LAND_IMAGE_BASE}/office-documents.png`;
export const landOfficeEditorUrl = `${LAND_IMAGE_BASE}/office-editor.png`;

export const landRagNamespacesUrl = `${LAND_IMAGE_BASE}/rag-namespaces.png`;
export const landRagSearchUrl = `${LAND_IMAGE_BASE}/rag-search.png`;

export const landShopCafeStorefrontUrl = `${LAND_IMAGE_BASE}/shop-cafe-storefront.png`;
export const landShopCafeGridUrl = `${LAND_IMAGE_BASE}/shop-cafe-grid.png`;
export const landShopCafeProductUrl = `${LAND_IMAGE_BASE}/shop-cafe-product.png`;
export const landShopCafeCartUrl = `${LAND_IMAGE_BASE}/shop-cafe-cart.png`;
export const landShopCafeMobileUrl = `${LAND_IMAGE_BASE}/shop-cafe-mobile.png`;
export const landShopMarketStorefrontUrl = `${LAND_IMAGE_BASE}/shop-market-storefront.png`;
export const landShopPizzaStorefrontUrl = `${LAND_IMAGE_BASE}/shop-pizza-storefront.png`;
export const landShopAdminMenuShotUrl = `${LAND_IMAGE_BASE}/shop-admin-menu.png`;
export const landShopAdminBuilderShotUrl = `${LAND_IMAGE_BASE}/shop-admin-builder.png`;
export const landShopAdminOrdersUrl = `${LAND_IMAGE_BASE}/shop-admin-orders.png`;

export const landSyncChatUrl = `${LAND_IMAGE_BASE}/sync-chat.png`;

export const landWikiHomeShotUrl = `${LAND_IMAGE_BASE}/wiki-home.png`;
export const landWikiPageShotUrl = `${LAND_IMAGE_BASE}/wiki-page.png`;

export const landWorktrackerBoardUrl = `${LAND_IMAGE_BASE}/worktracker-board.png`;
export const landWorktrackerMyUrl = `${LAND_IMAGE_BASE}/worktracker-my.png`;
