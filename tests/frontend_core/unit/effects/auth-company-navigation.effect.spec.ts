import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { createAuthCompanyNavigationEffect } from '@platform/lib/events/effects/auth-company-navigation.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { setPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

import { testEvent as ev } from '../../helpers/bus-fixtures.js';
import { prop } from '../../helpers/prop.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';

/** @type {import('@platform/lib/utils/platform-brand.js').PlatformBrandBootstrap} */
const LINNEX_BRAND = {
    baseDomain: 'linnex.io',
    isProduction: true,
    portSuffix: '',
    protocol: 'https',
    platformName: 'Linnex',
    supportEmail: 'support@linnex.io',
    logoPath: '/static/core/assets/service_logos/frontend_logo.svg',
    apexOrigin: 'https://linnex.io/',
    supportedDomains: ['linnex.io', 'linnex.io'],
    modelsProductName: 'Linnex Models',
    voiceProductName: 'Linnex Voice',
    llmsDisplayLabel: 'Linnex LLMs',
    flowsProductLabel: 'Linnex Flows',
};

describe('authCompanyNavigationEffect', () => {
    beforeEach(() => {
        setPlatformBrandBootstrap(LINNEX_BRAND);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('с /select-company переходит на /dashboard того же subdomain', async () => {
        let href = 'https://system.linnex.io/select-company';
        const loc = {
            hostname: 'system.linnex.io',
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
        vi.stubGlobal('window', { location: loc });
        vi.stubGlobal('localStorage', { setItem });

        const getState = () => ({
            companies: {
                list: [{ company_id: 'system', subdomain: 'system', name: 'System' }],
            },
        });
        const dispatched: DispatchedRecord[] = [];
        await createAuthCompanyNavigationEffect()(
            ev(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: 'system' }),
            buildCtx(getState, dispatched),
        );

        expect(href).toBe('https://system.linnex.io/dashboard');
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
        vi.stubGlobal('window', { location: loc });
        vi.stubGlobal('localStorage', { setItem });

        const getState = () => ({
            companies: {
                list: [{ company_id: 'c2', subdomain: 'b', name: 'B' }],
            },
        });
        const dispatched: DispatchedRecord[] = [];
        await createAuthCompanyNavigationEffect()(
            ev(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: 'c2' }),
            buildCtx(getState, dispatched),
        );

        expect(href).toBe('http://b.localhost:8002/crm/tasks');
        expect(setItem).toHaveBeenCalled();
        const successToast = dispatched.find(
            (d) => d.type === CoreEvents.UI_TOAST_SHOW && prop(d.payload, 'type') === 'success',
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
        vi.stubGlobal('window', { location: loc });
        vi.stubGlobal('localStorage', { setItem: vi.fn() });

        const getState = () => ({ companies: { list: [{ company_id: 'c2', name: 'B' }] } });
        const dispatched: DispatchedRecord[] = [];
        await createAuthCompanyNavigationEffect()(
            ev(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: 'c2' }),
            buildCtx(getState, dispatched),
        );
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(prop(toast?.payload, 'type')).toBe('error');
        expect(prop(toast?.payload, 'i18n_key')).toBe('platform:company.subdomain_missing');
    });
});
