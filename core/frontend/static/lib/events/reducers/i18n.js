/**
 * I18n slice.
 *
 * Поля state.i18n:
 *   locale:           string  - активная локаль (ru/en/...)
 *   defaultNamespace: string|null
 *   translations:     { [locale: string]: object } - кеш загруженных бандлов
 *   loading:          boolean
 *   error:            string|null
 */

import { CoreEvents } from '../contract.js';

export const initialI18nState = Object.freeze({
    locale: 'ru',
    defaultNamespace: null,
    translations: {},
    loading: false,
    error: null,
});

export const I18N_NAMESPACE_SET_REQUESTED = 'i18n/namespace/set_requested';

export function i18nReducer(state = initialI18nState, event) {
    switch (event.type) {
        case CoreEvents.I18N_LOCALE_REQUESTED:
            return { ...state, loading: true, error: null };

        case CoreEvents.I18N_LOCALE_LOADED: {
            const locale = event.payload && event.payload.locale;
            const bundle = event.payload && event.payload.bundle;
            if (!locale || !bundle) return state;
            return {
                ...state,
                loading: false,
                error: null,
                translations: { ...state.translations, [locale]: bundle },
            };
        }

        case CoreEvents.I18N_LOCALE_CHANGED: {
            const locale = event.payload && event.payload.locale;
            const ns = event.payload && event.payload.default_namespace;
            if (!locale) return state;
            return {
                ...state,
                locale,
                defaultNamespace: ns !== undefined ? ns : state.defaultNamespace,
            };
        }

        case CoreEvents.I18N_LOCALE_FAILED:
            return {
                ...state,
                loading: false,
                error: event.payload && event.payload.message ? event.payload.message : 'i18n_error',
            };

        case I18N_NAMESPACE_SET_REQUESTED: {
            const ns = event.payload && event.payload.namespace;
            if (typeof ns !== 'string' || ns === state.defaultNamespace) return state;
            return { ...state, defaultNamespace: ns };
        }

        default:
            return state;
    }
}
