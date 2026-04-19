import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createCompaniesEffect } from '@platform/lib/events/effects/companies.effect.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let fetchMock;
beforeEach(() => { fetchMock = installFetchMock(); });
afterEach(() => fetchMock.uninstall());

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('companiesEffect', () => {
    it('LOAD_REQUESTED → LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/api/companies/me', { items: [{ id: 'c1' }] });
        const dispatched = [];
        await createCompaniesEffect({ baseUrl: '/svc' })(ev(COMPANIES_EVENTS.LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === COMPANIES_EVENTS.LOADED);
        expect(loaded.payload.items).toEqual([{ id: 'c1' }]);
    });

    it('LOAD при ошибке → LOAD_FAILED', async () => {
        fetchMock.respondStatus('GET', '/svc/api/companies/me', 500);
        const dispatched = [];
        await createCompaniesEffect({ baseUrl: '/svc' })(ev(COMPANIES_EVENTS.LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === COMPANIES_EVENTS.LOAD_FAILED)).toBeTruthy();
    });

    it('SLUG_CHECK_REQUESTED требует slug', async () => {
        await expect(createCompaniesEffect({ baseUrl: '/svc' })(ev(COMPANIES_EVENTS.SLUG_CHECK_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/slug/);
    });

    it('SLUG_CHECKED dispatch с available', async () => {
        fetchMock.respondJson('POST', '/svc/api/companies/check-slug', { available: true });
        const dispatched = [];
        await createCompaniesEffect({ baseUrl: '/svc' })(ev(COMPANIES_EVENTS.SLUG_CHECK_REQUESTED, { slug: 'foo' }), buildCtx(() => ({}), dispatched));
        const checked = dispatched.find((d) => d.type === COMPANIES_EVENTS.SLUG_CHECKED);
        expect(checked.payload).toEqual({ slug: 'foo', available: true });
    });

    it('CREATE_REQUESTED требует name+slug', async () => {
        await expect(createCompaniesEffect({ baseUrl: '/svc' })(ev(COMPANIES_EVENTS.CREATE_REQUESTED, { name: 'x' }), buildCtx(() => ({}), []))).rejects.toThrow(/name and slug/);
    });

    it('CREATED содержит redirect_url', async () => {
        fetchMock.respondJson('POST', '/svc/api/companies', { id: 'c2', redirect_url: '/dash' });
        const dispatched = [];
        await createCompaniesEffect({ baseUrl: '/svc' })(ev(COMPANIES_EVENTS.CREATE_REQUESTED, { name: 'X', slug: 'x' }), buildCtx(() => ({}), dispatched));
        const created = dispatched.find((d) => d.type === COMPANIES_EVENTS.CREATED);
        expect(created.payload.redirect_url).toBe('/dash');
    });
});
