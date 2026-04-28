/**
 * Локаль UI до первого ответа GET /api/i18n/{locale} (экран загрузки, первый paint).
 * Порядок: localStorage → cookie language → navigator → ru.
 * Допустимые значения для запроса бандла: ru | en.
 */

export const PLATFORM_LOCALE_STORAGE_KEY = 'platform_locale';
const LANGUAGE_COOKIE = 'language';

function normalizeToSupportedLocale(raw) {
    const base = String(raw).toLowerCase().split('-')[0];
    return base === 'en' ? 'en' : 'ru';
}

export function resolveInitialUiLocale() {
    const ls =
        typeof globalThis.localStorage !== 'undefined' && typeof globalThis.localStorage.getItem === 'function'
            ? globalThis.localStorage
            : null;
    if (ls) {
        const stored = ls.getItem(PLATFORM_LOCALE_STORAGE_KEY);
        if (stored) {
            return normalizeToSupportedLocale(stored);
        }
    }
    const doc = typeof globalThis.document !== 'undefined' ? globalThis.document : null;
    if (doc && typeof doc.cookie === 'string' && doc.cookie.length > 0) {
        const cookie = doc.cookie
            .split(';')
            .map((c) => c.trim())
            .find((c) => c.startsWith(`${LANGUAGE_COOKIE}=`));
        if (cookie) {
            return normalizeToSupportedLocale(cookie.split('=')[1]);
        }
    }
    const rawLang =
        globalThis.navigator && typeof globalThis.navigator.language === 'string'
            ? globalThis.navigator.language
            : 'ru';
    const nav = rawLang.split('-')[0].toLowerCase();
    return normalizeToSupportedLocale(nav);
}
