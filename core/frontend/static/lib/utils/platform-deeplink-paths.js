/**
 * Префиксы путей продукта для Universal Links / App Links и документации.
 * Новый сервис: одна строка здесь + согласованные записи в AASA и assetlinks.
 */
export const DEEPLINK_PATH_PREFIXES = [
    '/',
    '/join',
    '/frontend',
    '/sync',
    '/crm',
    '/rag',
    '/flows',
    '/documentation',
    '/scheduler',
];

/**
 * Шаблоны path для apple-app-site-association (суффикс * по правилам Apple).
 */
export function getAasaPathPatterns() {
    return DEEPLINK_PATH_PREFIXES.map((p) => (p === '/' ? '/' : `${p}/*`));
}

/**
 * Целевой href при открытии ссылки продукта из нативной оболочки (тот же origin — только path).
 */
export function hrefForDeepLinkNavigation(openedUrl, currentOrigin) {
    if (openedUrl.origin === currentOrigin) {
        return openedUrl.pathname + openedUrl.search + openedUrl.hash;
    }
    return openedUrl.href;
}
