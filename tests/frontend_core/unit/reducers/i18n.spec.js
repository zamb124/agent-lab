import { describe, it, expect } from 'vitest';
import { i18nReducer, initialI18nState, I18N_NAMESPACE_SET_REQUESTED } from '@platform/lib/events/reducers/i18n.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('i18nReducer', () => {
    it('initial: ru, default ns null', () => {
        expect(initialI18nState.locale).toBe('ru');
        expect(initialI18nState.defaultNamespace).toBeNull();
        expect(initialI18nState.translations).toEqual({});
    });

    it('I18N_LOCALE_REQUESTED → loading=true', () => {
        const next = i18nReducer(initialI18nState, ev(CoreEvents.I18N_LOCALE_REQUESTED, { locale: 'en' }));
        expect(next.loading).toBe(true);
        expect(next.error).toBeNull();
    });

    it('I18N_LOCALE_LOADED кеширует bundle', () => {
        const next = i18nReducer(initialI18nState, ev(CoreEvents.I18N_LOCALE_LOADED, { locale: 'en', bundle: { hello: 'Hello' } }));
        expect(next.translations.en).toEqual({ hello: 'Hello' });
        expect(next.loading).toBe(false);
    });

    it('I18N_LOCALE_LOADED без locale/bundle — no-op', () => {
        expect(i18nReducer(initialI18nState, ev(CoreEvents.I18N_LOCALE_LOADED, { locale: 'en' }))).toBe(initialI18nState);
        expect(i18nReducer(initialI18nState, ev(CoreEvents.I18N_LOCALE_LOADED, { bundle: {} }))).toBe(initialI18nState);
    });

    it('I18N_LOCALE_CHANGED меняет locale + ns', () => {
        const next = i18nReducer(initialI18nState, ev(CoreEvents.I18N_LOCALE_CHANGED, { locale: 'en', default_namespace: 'platform' }));
        expect(next.locale).toBe('en');
        expect(next.defaultNamespace).toBe('platform');
    });

    it('I18N_LOCALE_FAILED фиксирует error', () => {
        const next = i18nReducer(initialI18nState, ev(CoreEvents.I18N_LOCALE_FAILED, { message: 'no bundle' }));
        expect(next.error).toBe('no bundle');
    });

    it('I18N_NAMESPACE_SET_REQUESTED обновляет defaultNamespace', () => {
        const next = i18nReducer(initialI18nState, ev(I18N_NAMESPACE_SET_REQUESTED, { namespace: 'crm' }));
        expect(next.defaultNamespace).toBe('crm');
    });

    it('тот же namespace → no-op', () => {
        const seeded = { ...initialI18nState, defaultNamespace: 'crm' };
        expect(i18nReducer(seeded, ev(I18N_NAMESPACE_SET_REQUESTED, { namespace: 'crm' }))).toBe(seeded);
    });
});
