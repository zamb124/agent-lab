import { describe, it, expect, afterEach, vi } from 'vitest';
import { createAuthCompanyNavigationEffect } from '@platform/lib/events/effects/auth-company-navigation.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'http' } });

describe('authCompanyNavigationEffect', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('с /select-company переходит на /dashboard?post_login=1 того же арендатора', async () => {
        let href = 'https://system.humanitec.ru/select-company';
        const loc = {
            hostname: 'system.humanitec.ru',
            port: '',
            protocol: 'https:',
            pathname: '/select-company',
            search: '',
            hash: '',
        };
        Object.defineProperty(loc, 'href', {
            configurable: true,
            get() {
                return href;
            },
            set(v) {
                href = v;
            },
        });
        const setItem = vi.fn();
        vi.stubGlobal('window', {
            location: loc,
            localStorage: { setItem },
        });

        const getState = () => ({
            companies: {
                list: [{ company_id: 'system', subdomain: 'system', name: 'System' }],
            },
        });
        const dispatched = [];
        await createAuthCompanyNavigationEffect()(
            ev(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: 'system' }),
            buildCtx(getState, dispatched),
        );

        expect(href).toBe('https://system.humanitec.ru/dashboard?post_login=1');
        expect(setItem).toHaveBeenCalled();
    });

    it('при другом поддомене выставляет location.href и localStorage', async () => {
        let href = 'http://a.localhost:8002/crm/tasks';
         const loc = {
            hostname: 'a.localhost',
            port: '8002',
            protocol: 'http:',
            pathname: '/crm/tasks',
            search: '',
            hash: '',
        };
        Object.defineProperty(loc, 'href', {
            configurable: true,
            get() {
                return href;
            },
            set(v) {
                href = v;
            },
        });
        const setItem = vi.fn();
        vi.stubGlobal('window', {
            location: loc,
            localStorage: { setItem },
        });

        const getState = () => ({
            companies: {
                list: [{ company_id: 'c2', subdomain: 'b', name: 'B' }],
            },
        });
        const dispatched = [];
        await createAuthCompanyNavigationEffect()(
            ev(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: 'c2' }),
            buildCtx(getState, dispatched),
        );

        expect(href).toBe('http://b.localhost:8002/crm/tasks');
        expect(setItem).toHaveBeenCalled();
        const successToast = dispatched.find(
            (d) => d.type === CoreEvents.UI_TOAST_SHOW && d.payload.type === 'success',
        );
        expect(successToast).toBeTruthy();
    });

    it('без subdomain → UI_TOAST_SHOW error', async () => {
        let href = 'http://a.localhost:8002/crm/tasks';
        const loc = {
            hostname: 'a.localhost',
            port: '8002',
            protocol: 'http:',
            pathname: '/',
            search: '',
            hash: '',
        };
        Object.defineProperty(loc, 'href', {
            configurable: true,
            get() {
                return href;
            },
            set(v) {
                href = v;
            },
        });
        vi.stubGlobal('window', {
            location: loc,
            localStorage: { setItem: vi.fn() },
        });

        const getState = () => ({ companies: { list: [{ company_id: 'c2', name: 'B' }] } });
        const dispatched = [];
        await createAuthCompanyNavigationEffect()(
            ev(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: 'c2' }),
            buildCtx(getState, dispatched),
        );
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast.payload.type).toBe('error');
        expect(toast.payload.i18n_key).toBe('platform:company.subdomain_missing');
    });
});
