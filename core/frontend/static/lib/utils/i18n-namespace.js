/**
 * I18n: дефолтный namespace из baseUrl сервиса.
 *
 * Бандлы хранятся в core/i18n/translations/<locale>/<namespace>.json. Сервис
 * выбирает свой namespace по своему URL-префиксу: '/crm' -> 'crm', '/sync' -> 'sync'.
 *
 * Application-level default namespace задаётся через `static defaultI18nNamespace`
 * на подклассе `PlatformApp`; PlatformApp при boot'е приземляет его в
 * `setDefaultI18nNamespace`, после чего все компоненты сервиса получают его
 * автоматически в `this.t(...)` без объявления `static i18nNamespace =`.
 */

export const I18nNs = Object.freeze({
    BILLING: 'billing',
    LANDING: 'landing',
    PLATFORM: 'platform',
    FRONTEND: 'frontend',
    FRONTEND_PRODUCTS: 'frontend_products',
    PRIVACY: 'privacy',
    TERMS: 'terms',
    COMMON: 'common',
});

let _defaultNamespace = null;

export function setDefaultI18nNamespace(ns) {
    if (ns === null || ns === undefined) {
        _defaultNamespace = null;
        return;
    }
    if (typeof ns !== 'string' || ns.length === 0) {
        throw new Error(`setDefaultI18nNamespace: expected non-empty string, got ${typeof ns}`);
    }
    _defaultNamespace = ns;
}

export function getDefaultI18nNamespace() {
    return _defaultNamespace;
}

/**
 * @param {string} baseUrl
 * @returns {string} имя бандла без расширения, либо '' если landing/корень.
 */
export function i18nDefaultNamespaceForBaseUrl(baseUrl) {
    if (typeof baseUrl !== 'string') {
        throw new Error('i18nDefaultNamespaceForBaseUrl: expected string');
    }
    const trimmed = baseUrl.trim();
    if (trimmed === '') return '';
    let path = trimmed;
    if (path.endsWith('/')) path = path.slice(0, -1);
    if (path === '') return '';
    if (!path.startsWith('/')) {
        throw new Error(`i18nDefaultNamespaceForBaseUrl: expected leading /, got: ${baseUrl}`);
    }
    const seg = path.slice(1);
    if (seg === '') return '';
    if (seg.includes('/')) {
        throw new Error(`i18nDefaultNamespaceForBaseUrl: single segment expected, got: ${baseUrl}`);
    }
    return seg;
}
