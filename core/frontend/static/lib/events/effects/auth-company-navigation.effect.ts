/**
 * После смены активной компании (AUTH_COMPANY_SWITCHED) — редирект на company subdomain.
 *
 * Реакция перенесена из platform-user / service-switcher-sheet: лист bottom-sheet
 * снимается с DOM при закрытии и отписывается от bus до завершения HTTP switch-company,
 * из-за чего навигация не срабатывала.
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { payloadFields, stringField } from '../payload.js';
import type { CompanyRecord } from '../reducers/companies.js';
import { buildCompanySubdomainUrl } from '../../utils/company-url.js';
import { platformStorageKey } from '../../utils/storage-keys.js';
import { storageSet } from '../../utils/platform-storage.js';

export const COMPANY_SWITCH_STORAGE_KEY = platformStorageKey('core', 'company_switch');

export function createAuthCompanyNavigationEffect(): (event: PlatformEvent, ctx: EffectCtx<{ companies?: { list?: CompanyRecord[] } }>) => Promise<void> {
    return async function authCompanyNavigationEffect(event: PlatformEvent, ctx: EffectCtx<{ companies?: { list?: CompanyRecord[] } }>): Promise<void> {
        if (event.type !== CoreEvents.AUTH_COMPANY_SWITCHED) return;

        const companyId = stringField(payloadFields(event).company_id);
        if (companyId === null) return;

        const state = ctx.getState();
        const companies = state.companies && Array.isArray(state.companies.list) ? state.companies.list : [];
        const company = companies.find((c) => c && c.company_id === companyId);

        if (typeof globalThis.window === 'undefined' || !globalThis.window.location) return;

        if (!company || typeof company.subdomain !== 'string' || company.subdomain.trim() === '') {
            ctx.dispatch(
                CoreEvents.UI_TOAST_SHOW,
                {
                    type: 'error',
                    i18n_key: 'platform:company.subdomain_missing',
                    i18n_vars: null,
                    duration: 4000,
                },
                { causation_id: event.id, source: 'local' },
            );
            return;
        }

        ctx.dispatch(
            CoreEvents.UI_TOAST_SHOW,
            {
                type: 'success',
                i18n_key: 'platform:company.switched',
                i18n_vars: null,
                duration: 2000,
            },
            { causation_id: event.id, source: 'local' },
        );

        const subdomain = company.subdomain.trim();
        const payload = `${Date.now()}|${company.company_id}|${subdomain}`;
        storageSet(COMPANY_SWITCH_STORAGE_KEY, payload);

        const pathname =
            typeof window.location.pathname === 'string' ? window.location.pathname : '';
        const search = typeof window.location.search === 'string' ? window.location.search : '';
        const hash = typeof window.location.hash === 'string' ? window.location.hash : '';
        let targetPath: string;
        if (
            pathname === '/select-company'
            || pathname.startsWith('/select-company/')
        ) {
            targetPath = '/dashboard';
        } else {
            targetPath = `${pathname}${search}${hash}`;
        }
        const targetUrl = buildCompanySubdomainUrl(subdomain, targetPath);
        if (targetUrl !== window.location.href) {
            window.location.href = targetUrl;
            return;
        }
        window.location.reload();
    };
}
