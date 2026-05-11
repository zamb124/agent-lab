/**
 * URL и fetch credentials для embed на стороннем origin: запросы к `/api/...` и
 * `/static/...` должны идти на origin платформы (из `flowsBaseUrl`), иначе
 * браузер стучится в `location.host` страницы-хоста (404 / нет иконок).
 */

/**
 * @param {string} path — путь с ведущим `/`, например `/api/i18n/ru`
 * @param {string} [apexOrigin] — `https://host` без trailing slash
 * @returns {string}
 */
export function platformAbsoluteUrl(path, apexOrigin) {
    if (typeof path !== 'string' || !path.startsWith('/')) {
        throw new Error('platformAbsoluteUrl: path must be a non-empty string starting with /');
    }
    const a = typeof apexOrigin === 'string' ? apexOrigin.trim().replace(/\/+$/, '') : '';
    if (a === '') {
        return path;
    }
    return `${a}${path}`;
}

/**
 * Публичные GET к платформе с чужого origin — без cookies (CORS + non-credentialed).
 *
 * @param {string} url
 * @returns {'include'|'omit'}
 */
export function embedSafeFetchCredentials(url) {
    if (typeof location === 'undefined') {
        return 'include';
    }
    if (typeof url !== 'string' || !url.startsWith('http')) {
        return 'include';
    }
    try {
        return new URL(url).origin === location.origin ? 'include' : 'omit';
    } catch {
        return 'include';
    }
}
