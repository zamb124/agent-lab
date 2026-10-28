/**
 * Слайс i18n.
 *
 * Поля state.i18n:
 *   locale:           string  - активная локаль (ru/en/...)
 *   defaultNamespace: string|null
 *   translations:     { [locale: string]: object } - кеш загруженных бандлов
 *   loading:          boolean
 *   error:            string|null
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent } from '../contract.js';

export interface I18nState {
    locale: string;
    defaultNamespace: string | null;
    translations: Record<string, Record<string, unknown>>;
    loading: boolean;
    error: string | null;
}
import { resolveInitialUiLocale } from '../../utils/i18n-initial-locale.js';
import { isPlainRecord, payloadFields, stringField } from '../payload.js';

// До ответа GET /api/i18n/{locale}: только common.loading.
// Не считать !!translations[locale] признаком полного бандла.
const BOOTSTRAP_COMMON_STUB_RU: Record<string, unknown> = Object.freeze({
    common: Object.freeze({
        loading: 'Загрузка...',
    }),
});

const BOOTSTRAP_COMMON_STUB_EN: Record<string, unknown> = Object.freeze({
    common: Object.freeze({
        loading: 'Loading...',
    }),
});

export const initialI18nState = Object.freeze({
    locale: resolveInitialUiLocale(),
    defaultNamespace: null,
    translations: Object.freeze({
        ru: BOOTSTRAP_COMMON_STUB_RU,
        en: BOOTSTRAP_COMMON_STUB_EN,
    }),
    loading: false,
    error: null,
});

export const I18N_NAMESPACE_SET_REQUESTED = 'i18n/namespace/set_requested';

export function i18nReducer(state: I18nState = initialI18nState, event: PlatformEvent): I18nState {
    switch (event.type) {
        case CoreEvents.I18N_LOCALE_REQUESTED:
            return { ...state, loading: true, error: null };

        case CoreEvents.I18N_LOCALE_LOADED: {
            const p = payloadFields(event);
            if (typeof p.locale !== 'string' || p.locale.length === 0 || !isPlainRecord(p.bundle)) return state;
            return {
                ...state,
                loading: false,
                error: null,
                translations: { ...state.translations, [p.locale]: p.bundle },
            };
        }

        case CoreEvents.I18N_LOCALE_CHANGED: {
            const p = payloadFields(event);
            if (typeof p.locale !== 'string' || !p.locale) return state;
            return {
                ...state,
                locale: p.locale,
                defaultNamespace: typeof p.default_namespace === 'string' ? p.default_namespace : state.defaultNamespace,
            };
        }

        case CoreEvents.I18N_LOCALE_FAILED: {
            const message = stringField(payloadFields(event).message);
            return {
                ...state,
                loading: false,
                error: message === null ? 'i18n_error' : message,
            };
        }

        case I18N_NAMESPACE_SET_REQUESTED: {
            const ns = (payloadFields(event)).namespace;
            if (typeof ns !== 'string' || ns === state.defaultNamespace) return state;
            return { ...state, defaultNamespace: ns };
        }

        default:
            return state;
    }
}
