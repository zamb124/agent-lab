/**
 * Сжатые скриншоты для лендинга и продуктовых страниц (sips -Z 1200 от исходников в land/).
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

export const landDocumentsHeroUrl = `${LAND_IMAGE_BASE}/documents_1.png`;
export const landDocumentsShot2Url = `${LAND_IMAGE_BASE}/documents_2.png`;
export const landDocumentsShot3Url = `${LAND_IMAGE_BASE}/documents_3.png`;

export const landGeoMapUrl = `${LAND_IMAGE_BASE}/geo_map.png`;
export const landGeoMapLabUrl = `${LAND_IMAGE_BASE}/geo_map_lab.png`;
export const landGeoSourcesUrl = `${LAND_IMAGE_BASE}/geo_sources.png`;

export const landWikiHomeUrl = `${LAND_IMAGE_BASE}/wiki_home.png`;
export const landWikiPageUrl = `${LAND_IMAGE_BASE}/wiki_page.png`;

export const landShopStorefrontUrl = `${LAND_IMAGE_BASE}/shop_storefront.png`;
export const landShopGridUrl = `${LAND_IMAGE_BASE}/shop_grid.png`;
export const landShopCartUrl = `${LAND_IMAGE_BASE}/shop_cart.png`;
export const landShopAdminMenuUrl = `${LAND_IMAGE_BASE}/shop_admin_menu.png`;
export const landShopBuilderUrl = `${LAND_IMAGE_BASE}/shop_builder.png`;
export const landShopMobileUrl = `${LAND_IMAGE_BASE}/shop_mobile.png`;
