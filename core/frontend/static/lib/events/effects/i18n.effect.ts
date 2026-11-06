/**
 * Эффект i18n.
 *
 * Загружает бандл переводов с /api/i18n/<locale>, проставляет cookie и
 * document.documentElement.lang. Эмитит I18N_LOCALE_LOADED и _CHANGED.
 */

import { CoreEvents } from '../contract.js';
import type { EffectCtx, PlatformEvent } from '../contract.js';
import { httpRequest } from '../http.js';
import { isPlainRecord } from '../payload.js';
import { PLATFORM_LOCALE_STORAGE_KEY, resolveInitialUiLocale } from '../../utils/i18n-initial-locale.js';
import { storageSet } from '../../utils/platform-storage.js';
import { i18nDefaultNamespaceForBaseUrl } from '../../utils/i18n-namespace.js';
import { embedSafeFetchCredentials, platformAbsoluteUrl } from './embed-request-helpers.js';

const LOCALE_COOKIE = 'language';

function _writeLocaleCookie(locale: string): void {
    const oneYear = 60 * 60 * 24 * 365;
    document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=${oneYear}; SameSite=Lax`;
    document.documentElement.lang = locale;
}

export function createI18nEffect({ baseUrl, platformApexOrigin }: { baseUrl?: string; platformApexOrigin?: string } = {}) {
    const defaultNamespace = i18nDefaultNamespaceForBaseUrl(baseUrl === undefined ? '' : baseUrl);
    const apex = typeof platformApexOrigin === 'string' ? platformApexOrigin.trim() : '';
    return async function i18nEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        switch (event.type) {
            case CoreEvents.APP_BOOTSTRAP_STARTED: {
                const locale = resolveInitialUiLocale();
                ctx.dispatch(CoreEvents.I18N_LOCALE_REQUESTED, { locale }, { causation_id: event.id });
                return;
            }
            case CoreEvents.I18N_LOCALE_REQUESTED: {
                const payload = event.payload;
                if (!isPlainRecord(payload) || typeof payload.locale !== 'string' || payload.locale.length === 0) {
                    throw new Error('i18n.effect: locale required');
                }
                const locale = payload.locale;
                try {
                    const bundleUrl = platformAbsoluteUrl(
                        `/api/i18n/${encodeURIComponent(locale)}`,
                        apex,
                    );
                    const bundle = await httpRequest({
                        method: 'GET',
                        url: bundleUrl,
                        credentials: embedSafeFetchCredentials(bundleUrl),
                    });
                    ctx.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale, bundle }, { causation_id: event.id, source: 'http' });
                    storageSet(PLATFORM_LOCALE_STORAGE_KEY, locale);
                    _writeLocaleCookie(locale);
                    ctx.dispatch(
                        CoreEvents.I18N_LOCALE_CHANGED,
                        { locale, default_namespace: defaultNamespace.length === 0 ? null : defaultNamespace },
                        { causation_id: event.id },
                    );
                } catch (err) {
                    ctx.dispatch(
                        CoreEvents.I18N_LOCALE_FAILED,
                        { locale, message: String(err instanceof Error ? err.message : err) },
                        { causation_id: event.id, source: 'http' },
                    );
                }
                return;
            }
            default:
                return;
        }
    };
}

/**
 * Утилита t(): чистая функция перевода поверх state.i18n.translations.
 *
 * Поиск (в порядке приоритета):
 *   1. Прямой путь по точкам: bundle[a][b][c].
 *   2. Если задан явный namespace (4-й аргумент) и в bundle есть `bundle[namespace]` —
 *      ищет тот же путь внутри него: bundle[namespace][a][b][c].
 *   3. Если `defaultNamespace` задан в state.i18n и в bundle есть `bundle[defaultNamespace]` —
 *      ищет тот же путь внутри него: bundle[defaultNamespace][a][b][c].
 *      Короткие ключи вроде console_sidebar.dashboard резолвятся внутри defaultNamespace сервиса.
 *
 * Если ничего не найдено — возвращается сам key (видно в UI и в скане i18n).
 */
function _interpolate(str: string, vars: Record<string, unknown> | null | undefined): string {
    if (!vars) return str;
    let out = str.replace(/\{\{(\w+)\}\}/g, (_: string, name: string) =>
        Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : `{{${name}}}`,
    );
    out = out.replace(/\{(\w+)\}/g, (_: string, name: string) =>
        Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : `{${name}}`,
    );
    return out;
}

const _NUMERIC_SEGMENT_RE = /^\d+$/;

function _lookupPath(root: unknown, path: string[]): string | undefined {
    let cur: unknown = root;
    for (const segment of path) {
        if (isPlainRecord(cur)) {
            cur = cur[segment];
        } else if (Array.isArray(cur) && _NUMERIC_SEGMENT_RE.test(segment)) {
            cur = cur[Number(segment)];
        } else {
            return undefined;
        }
    }
    return typeof cur === 'string' ? cur : undefined;
}

/**
 * Полный GET /api/i18n/{locale} уже в state. До этого translations[locale]
 * — bootstrap stub { common.loading }; toast/t() тогда возвращают сырой ключ.
 */
export interface I18nStateLike {
    loading?: boolean;
    locale?: string;
    defaultNamespace?: string | null;
    translations?: Record<string, Record<string, unknown>>;
}

export function isI18nBundleReady(i18nState: I18nStateLike | null | undefined): boolean {
    if (!i18nState || typeof i18nState !== 'object' || Array.isArray(i18nState)) {
        return false;
    }
    if (i18nState.loading) {
        return false;
    }
    const locale = i18nState.locale;
    if (typeof locale !== 'string' || locale.length === 0) {
        return false;
    }
    const translations = i18nState.translations;
    if (!translations || typeof translations !== 'object' || Array.isArray(translations)) {
        return false;
    }
    const bundle = translations[locale];
    if (!bundle || typeof bundle !== 'object' || Array.isArray(bundle)) {
        return false;
    }
    return Object.keys(bundle).some((namespace) => namespace !== 'common');
}

export function translate(i18nState: I18nStateLike, key: string, vars?: Record<string, unknown> | null, namespace?: string): string {
    if (!key || typeof key !== 'string') return '';
    const locale = i18nState.locale;
    const translations = i18nState.translations;
    if (!locale || !translations) return key;
    const bundle = translations[locale];
    if (!bundle) return key;
    const path = key.split('.');

    const direct = _lookupPath(bundle, path);
    if (direct !== undefined) return _interpolate(direct, vars);

    if (typeof namespace === 'string' && namespace && bundle[namespace]) {
        const viaExplicit = _lookupPath(bundle[namespace], path);
        if (viaExplicit !== undefined) return _interpolate(viaExplicit, vars);
    }

    const ns = i18nState.defaultNamespace;
    if (ns && bundle[ns]) {
        const viaNs = _lookupPath(bundle[ns], path);
        if (viaNs !== undefined) return _interpolate(viaNs, vars);
    }

    return key;
}
