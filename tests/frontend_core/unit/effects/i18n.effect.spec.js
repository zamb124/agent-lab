import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createI18nEffect, translate } from '@platform/lib/events/effects/i18n.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installFakeStorage } from '../../helpers/fake-storage.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let dom;
let storage;
let fetchMock;

beforeEach(() => {
    dom = installDomShim();
    storage = installFakeStorage();
    fetchMock = installFetchMock();
    // document.cookie shim
    dom.document.cookie = '';
});
afterEach(() => {
    fetchMock.uninstall();
    storage.uninstall();
    dom.uninstall();
});

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('createI18nEffect: bootstrap', () => {
    it('эмитит I18N_LOCALE_REQUESTED с stored locale', async () => {
        storage.localStorage.setItem('platform_locale', 'en');
        const dispatched = [];
        await createI18nEffect({ baseUrl: '/svc' })(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        const req = dispatched.find((d) => d.type === CoreEvents.I18N_LOCALE_REQUESTED);
        expect(req.payload.locale).toBe('en');
    });

    it('без сохранённого locale — берёт из navigator.language', async () => {
        Object.defineProperty(globalThis.navigator, 'language', { value: 'fr-FR', configurable: true });
        const dispatched = [];
        await createI18nEffect({ baseUrl: '/svc' })(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        const req = dispatched.find((d) => d.type === CoreEvents.I18N_LOCALE_REQUESTED);
        expect(req.payload.locale).toBe('fr');
    });
});

describe('createI18nEffect: LOCALE_REQUESTED', () => {
    it('требует locale', async () => {
        await expect(createI18nEffect({ baseUrl: '/svc' })(ev(CoreEvents.I18N_LOCALE_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/locale/);
    });

    it('успех → LOADED + CHANGED + persists в localStorage', async () => {
        fetchMock.respondJson('GET', '/api/i18n/en', { hello: 'Hello' });
        const dispatched = [];
        await createI18nEffect({ baseUrl: '/svc' })(ev(CoreEvents.I18N_LOCALE_REQUESTED, { locale: 'en' }), buildCtx(() => ({}), dispatched));
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(CoreEvents.I18N_LOCALE_LOADED);
        expect(types).toContain(CoreEvents.I18N_LOCALE_CHANGED);
        expect(storage.localStorage.getItem('platform_locale')).toBe('en');
    });

    it('ошибка → LOCALE_FAILED', async () => {
        fetchMock.respondStatus('GET', '/api/i18n/en', 500);
        const dispatched = [];
        await createI18nEffect({ baseUrl: '/svc' })(ev(CoreEvents.I18N_LOCALE_REQUESTED, { locale: 'en' }), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CoreEvents.I18N_LOCALE_FAILED)).toBeTruthy();
    });
});

describe('translate', () => {
    const bundle = {
        ru: {
            common: { hello: 'Привет' },
            crm: { title: 'CRM' },
            with_var: 'Привет, {{name}}',
            new_brace: 'Old {name}',
        },
    };
    const stateWith = (defaultNamespace) => ({
        translations: bundle,
        locale: 'ru',
        defaultNamespace,
    });

    it('пустой key → ""', () => {
        expect(translate(stateWith(null), '')).toBe('');
    });

    it('нет bundle для locale — возвращает key', () => {
        expect(translate({ translations: {}, locale: 'ru', defaultNamespace: null }, 'common.hello')).toBe('common.hello');
    });

    it('прямой путь', () => {
        expect(translate(stateWith(null), 'common.hello')).toBe('Привет');
    });

    it('явный namespace', () => {
        expect(translate(stateWith(null), 'title', null, 'crm')).toBe('CRM');
    });

    it('default namespace', () => {
        expect(translate(stateWith('crm'), 'title')).toBe('CRM');
    });

    it('подстановка {{var}}', () => {
        expect(translate(stateWith(null), 'with_var', { name: 'Alice' })).toBe('Привет, Alice');
    });

    it('подстановка {var} (single)', () => {
        expect(translate(stateWith(null), 'new_brace', { name: 'Bob' })).toBe('Old Bob');
    });

    it('не найдено → возвращает key', () => {
        expect(translate(stateWith(null), 'missing.key')).toBe('missing.key');
    });
});
