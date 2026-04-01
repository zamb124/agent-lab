/**
 * Дефолтный namespace i18n = сегмент пути PlatformApp.getBaseUrl() (имя JSON без .json).
 * Пример: /crm → crm, /sync → sync. Пустая база → не менять стартовый дефолт сервиса (landing).
 */

/** Дополнительные бандлы (не slug сервиса): третий аргумент this.i18n.t(key, params, I18nNs.…). */
export const I18nNs = Object.freeze({
    BILLING: 'billing',
    LANDING: 'landing',
    PLATFORM: 'platform',
    FRONTEND_PRODUCTS: 'frontend_products',
});

/**
 * @param {string} baseUrl например '/sync' или ''
 * @returns {string} имя бандла без .json или '' — не менять дефолт I18nService (landing)
 */
export function i18nDefaultNamespaceForBaseUrl(baseUrl) {
    if (typeof baseUrl !== 'string') {
        throw new Error('i18nDefaultNamespaceForBaseUrl: ожидается строка');
    }
    const trimmed = baseUrl.trim();
    if (trimmed === '') {
        return '';
    }
    let path = trimmed;
    if (path.endsWith('/')) {
        path = path.slice(0, -1);
    }
    if (path === '') {
        return '';
    }
    if (!path.startsWith('/')) {
        throw new Error(`i18nDefaultNamespaceForBaseUrl: ожидается путь с ведущим /, получено: ${baseUrl}`);
    }
    const seg = path.slice(1);
    if (seg === '') {
        return '';
    }
    if (seg.includes('/')) {
        throw new Error(`i18nDefaultNamespaceForBaseUrl: один сегмент пути, получено: ${baseUrl}`);
    }
    return seg;
}
