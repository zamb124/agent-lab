/**
 * Эффект i18n.
 *
 * Загружает бандл переводов с /api/i18n/<locale>, проставляет cookie и
 * document.documentElement.lang. Эмитит I18N_LOCALE_LOADED и _CHANGED.
 */

import { CoreEvents } from '../contract.js';
import { httpRequest } from '../http.js';
import { PLATFORM_LOCALE_STORAGE_KEY, resolveInitialUiLocale } from '../../utils/i18n-initial-locale.js';
import { i18nDefaultNamespaceForBaseUrl } from '../../utils/i18n-namespace.js';
import { embedSafeFetchCredentials, platformAbsoluteUrl } from './embed-request-helpers.js';

const LOCALE_COOKIE = 'language';

function _writeLocaleCookie(locale) {
    const oneYear = 60 * 60 * 24 * 365;
    document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=${oneYear}; SameSite=Lax`;
    document.documentElement.lang = locale;
}

export function createI18nEffect({ baseUrl, platformApexOrigin } = {}) {
    const defaultNamespace = i18nDefaultNamespaceForBaseUrl(baseUrl || '');
    const apex = typeof platformApexOrigin === 'string' ? platformApexOrigin.trim() : '';
    return async function i18nEffect(event, ctx) {
        switch (event.type) {
            case CoreEvents.APP_BOOTSTRAP_STARTED: {
                const locale = resolveInitialUiLocale();
                ctx.dispatch(CoreEvents.I18N_LOCALE_REQUESTED, { locale }, { causation_id: event.id });
                return;
            }
            case CoreEvents.I18N_LOCALE_REQUESTED: {
                const locale = event.payload && event.payload.locale;
                if (!locale) {
                    throw new Error('i18n.effect: locale required');
                }
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
                    localStorage.setItem(PLATFORM_LOCALE_STORAGE_KEY, locale);
                    _writeLocaleCookie(locale);
                    ctx.dispatch(
                        CoreEvents.I18N_LOCALE_CHANGED,
                        { locale, default_namespace: defaultNamespace || null },
                        { causation_id: event.id },
                    );
                } catch (err) {
                    ctx.dispatch(
                        CoreEvents.I18N_LOCALE_FAILED,
                        { locale, message: String(err && err.message ? err.message : err) },
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
function _interpolate(str, vars) {
    if (!vars) return str;
    let out = str.replace(/\{\{(\w+)\}\}/g, (_, name) =>
        Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : `{{${name}}}`,
    );
    out = out.replace(/\{(\w+)\}/g, (_, name) =>
        Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : `{${name}}`,
    );
    return out;
}

function _lookupPath(root, path) {
    let cur = root;
    for (const segment of path) {
        if (cur === null || cur === undefined || typeof cur !== 'object') return undefined;
        cur = cur[segment];
    }
    return typeof cur === 'string' ? cur : undefined;
}

export function translate(i18nState, key, vars, namespace) {
    if (!key || typeof key !== 'string') return '';
    const bundle = i18nState.translations[i18nState.locale];
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
