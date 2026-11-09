/**
 * Локаль UI до первого ответа GET /api/i18n/{locale} (экран загрузки, первый paint).
 * Порядок: URL-префикс /en → localStorage → cookie language → navigator → ru.
 * URL-префикс — канонический сигнал (публичные /en/* страницы индексируются отдельно).
 * Допустимые значения для запроса бандла: ru | en.
 */

import { platformStorageKey } from './storage-keys.js';

export const PLATFORM_LOCALE_STORAGE_KEY = platformStorageKey('core', 'locale');
const LANGUAGE_COOKIE = 'language';

function normalizeToSupportedLocale(raw: unknown): string {
    const base = String(raw).toLowerCase().split('-')[0] ?? 'ru';
    return base === 'en' ? 'en' : 'ru';
}

function resolvePathLocale(): string | null {
    const loc = typeof globalThis.location === 'object' ? globalThis.location : null;
    if (loc === null || typeof loc.pathname !== 'string') {
        return null;
    }
    const path = loc.pathname.replace(/\/+$/, '') || '/';
    if (path === '/en' || path.startsWith('/en/')) {
        return 'en';
    }
    return null;
}

export function resolveInitialUiLocale(): string {
    const pathLocale = resolvePathLocale();
    if (pathLocale !== null) {
        return pathLocale;
    }
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
            const cookieValue = cookie.split('=')[1];
            if (cookieValue === undefined) {
                throw new Error('resolveInitialUiLocale: language cookie value missing');
            }
            return normalizeToSupportedLocale(cookieValue);
        }
    }
    const rawLang =
        globalThis.navigator && typeof globalThis.navigator.language === 'string'
            ? globalThis.navigator.language
            : 'ru';
    const nav = (rawLang.split('-')[0] ?? 'ru').toLowerCase();
    return normalizeToSupportedLocale(nav);
}
