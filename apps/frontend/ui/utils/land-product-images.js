/**
 * Сжатые скриншоты для лендинга и продуктовых страниц (sips -Z 1200 от исходников в land/).
 */
export const LAND_IMAGE_BASE = '/static/frontend/assets/images/land/optimized';

/** @param {string} locale */
export function landFlowsAbilityUrl(locale) {
    return locale === 'ru'
        ? `${LAND_IMAGE_BASE}/flows_ability-image_ru.png`
        : `${LAND_IMAGE_BASE}/flows_ability-image_en.png`;
}

export const landRagAbilityUrl = `${LAND_IMAGE_BASE}/rag.png`;
export const landNetworkleAbilityUrl = `${LAND_IMAGE_BASE}/networkle_ability-image_ru.png`;
export const landSyncAbilityUrl = `${LAND_IMAGE_BASE}/sync_ability-image_ru.png`;
