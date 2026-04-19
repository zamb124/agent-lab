import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createAuthEffect, CoreAuthEvents } from '@platform/lib/events/effects/auth.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let fetchMock;
beforeEach(() => { fetchMock = installFetchMock(); });
afterEach(() => fetchMock.uninstall());

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('authEffect: USER_LOAD_REQUESTED', () => {
    it('200 → AUTH_USER_LOADED с user объектом', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/me', { user_id: 'u1', name: 'Alice', company_id: 'c1', roles: ['owner'] });
        const dispatched = [];
        const effect = createAuthEffect({ baseUrl: '/svc' });
        await effect(ev(CoreAuthEvents.USER_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === CoreEvents.AUTH_USER_LOADED);
        expect(loaded.payload.user).toMatchObject({ id: 'u1', name: 'Alice', company_id: 'c1', roles: ['owner'] });
    });

    it('401 → AUTH_UNAUTHORIZED', async () => {
        fetchMock.respondStatus('GET', '/svc/api/auth/me', 401);
        const dispatched = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.USER_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const unauth = dispatched.find((d) => d.type === CoreEvents.AUTH_UNAUTHORIZED);
        expect(unauth).toBeTruthy();
    });

    it('500 → AUTH_USER_FAILED', async () => {
        fetchMock.respondStatus('GET', '/svc/api/auth/me', 500);
        const dispatched = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.USER_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const failed = dispatched.find((d) => d.type === CoreEvents.AUTH_USER_FAILED);
        expect(failed.payload.message).toBe('HTTP 500');
    });
});

describe('authEffect: AUTH_LOGOUT_REQUESTED', () => {
    it('всегда диспатчит AUTH_LOGGED_OUT (даже если HTTP падает)', async () => {
        fetchMock.respondStatus('POST', '/svc/api/auth/logout', 500);
        const dispatched = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreEvents.AUTH_LOGOUT_REQUESTED), buildCtx(() => ({}), dispatched));
        const out = dispatched.find((d) => d.type === CoreEvents.AUTH_LOGGED_OUT);
        expect(out).toBeTruthy();
    });
});

describe('authEffect: AUTH_COMPANY_SWITCH_REQUESTED', () => {
    it('требует company_id', async () => {
        await expect(createAuthEffect({ baseUrl: '/svc' })(
            ev(CoreEvents.AUTH_COMPANY_SWITCH_REQUESTED, {}),
            buildCtx(() => ({}), []),
        )).rejects.toThrow(/company_id/);
    });

    it('успех → AUTH_COMPANY_SWITCHED', async () => {
        fetchMock.respondJson('POST', '/svc/api/auth/switch-company', { ok: true });
        const dispatched = [];
        await createAuthEffect({ baseUrl: '/svc' })(
            ev(CoreEvents.AUTH_COMPANY_SWITCH_REQUESTED, { company_id: 'c2' }),
            buildCtx(() => ({}), dispatched),
        );
        const switched = dispatched.find((d) => d.type === CoreEvents.AUTH_COMPANY_SWITCHED);
        expect(switched.payload).toEqual({ company_id: 'c2' });
    });
});

describe('authEffect: PROVIDERS_LOAD_REQUESTED', () => {
    it('успех → PROVIDERS_LOADED с items', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/providers', { providers: [{ id: 'google' }] });
        const dispatched = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.PROVIDERS_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === CoreAuthEvents.PROVIDERS_LOADED);
        expect(loaded.payload.items).toEqual([{ id: 'google' }]);
    });

    it('пустой список → PROVIDERS_LOAD_FAILED', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/providers', { providers: [] });
        const dispatched = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.PROVIDERS_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const failed = dispatched.find((d) => d.type === CoreAuthEvents.PROVIDERS_LOAD_FAILED);
        expect(failed).toBeTruthy();
    });
});

describe('authEffect: SERVICE_ATTRS', () => {
    it('LOAD_REQUESTED → LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/me/attrs/frontend', { theme: 'dark' });
        const dispatched = [];
        await createAuthEffect({ baseUrl: '/svc' })(
            ev(CoreAuthEvents.SERVICE_ATTRS_LOAD_REQUESTED, { service: 'frontend' }),
            buildCtx(() => ({}), dispatched),
        );
        const loaded = dispatched.find((d) => d.type === CoreAuthEvents.SERVICE_ATTRS_LOADED);
        expect(loaded.payload).toEqual({ service: 'frontend', attrs: { theme: 'dark' } });
    });

    it('UPDATE_REQUESTED требует service + attrs object', async () => {
        await expect(createAuthEffect({ baseUrl: '/svc' })(
            ev(CoreAuthEvents.SERVICE_ATTRS_UPDATE_REQUESTED, { service: 'x' }),
            buildCtx(() => ({}), []),
        )).rejects.toThrow(/attrs/);
    });
});
