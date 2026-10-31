import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createAuthEffect, CoreAuthEvents } from '@platform/lib/events/effects/auth.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import type { PlatformEvent } from '../../../../core/frontend/static/lib/events/contract.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';
import { prop } from '../../helpers/prop.js';

let fetchMock: ReturnType<typeof installFetchMock>;
beforeEach(() => { fetchMock = installFetchMock(); });
afterEach(() => fetchMock.uninstall());

const ev = (type: string, payload: unknown = null): PlatformEvent => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });

describe('authEffect: USER_LOAD_REQUESTED', () => {
    it('200 → AUTH_USER_LOADED с user объектом', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/me', {
            user_id: 'u1',
            name: 'Alice',
            company_id: 'c1',
            roles: ['owner'],
            can_admin: true,
        });
        const dispatched: DispatchedRecord[] = [];
        const effect = createAuthEffect({ baseUrl: '/svc' });
        await effect(ev(CoreAuthEvents.USER_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === CoreEvents.AUTH_USER_LOADED);
        expect(prop(loaded?.payload, 'user')).toMatchObject({
            id: 'u1',
            name: 'Alice',
            company_id: 'c1',
            roles: ['owner'],
            canAdmin: true,
        });
    });

    it('401 → AUTH_UNAUTHORIZED', async () => {
        fetchMock.respondStatus('GET', '/svc/api/auth/me', 401);
        const dispatched: DispatchedRecord[] = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.USER_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const unauth = dispatched.find((d) => d.type === CoreEvents.AUTH_UNAUTHORIZED);
        expect(unauth).toBeTruthy();
    });

    it('500 → AUTH_USER_FAILED', async () => {
        fetchMock.respondStatus('GET', '/svc/api/auth/me', 500);
        const dispatched: DispatchedRecord[] = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.USER_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const failed = dispatched.find((d) => d.type === CoreEvents.AUTH_USER_FAILED);
        expect(prop(failed?.payload, 'message')).toBe('HTTP 500');
    });

    it('nullable-поля null → AUTH_USER_LOADED (str | None на wire)', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/me', {
            user_id: 'u1',
            name: 'Alice',
            email: null,
            avatar_url: null,
            company_id: 'c1',
            roles: ['owner'],
            can_admin: true,
        });
        const dispatched: DispatchedRecord[] = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.USER_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === CoreEvents.AUTH_USER_LOADED);
        expect(loaded).toBeTruthy();
        expect(prop(prop(loaded?.payload, 'user'), 'user_id')).toBe('u1');
    });

    it('без can_admin → AUTH_USER_FAILED (fail-closed)', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/me', {
            user_id: 'u1',
            name: 'Alice',
            company_id: 'c1',
            roles: ['owner'],
        });
        const dispatched: DispatchedRecord[] = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.USER_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const failed = dispatched.find((d) => d.type === CoreEvents.AUTH_USER_FAILED);
        expect(prop(failed?.payload, 'message')).toContain('can_admin');
    });
});

describe('authEffect: USER_SILENT_PROBE_REQUESTED', () => {
    it('200 → AUTH_USER_LOADED (апгрейд до authenticated на публичной странице)', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/me', {
            user_id: 'u1',
            name: 'Alice',
            company_id: 'c1',
            roles: ['owner'],
            can_admin: true,
        });
        const dispatched: DispatchedRecord[] = [];
        const effect = createAuthEffect({ baseUrl: '/svc' });
        await effect(ev(CoreAuthEvents.USER_SILENT_PROBE_REQUESTED), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === CoreEvents.AUTH_USER_LOADED);
        expect(loaded).toBeTruthy();
        expect(prop(loaded?.payload, 'user')).toMatchObject({
            id: 'u1',
            name: 'Alice',
            company_id: 'c1',
            roles: ['owner'],
            canAdmin: true,
        });
    });

    it('401 → AUTH_ASSUMED_ANONYMOUS (не AUTH_UNAUTHORIZED — аноним остаётся анонимом)', async () => {
        fetchMock.respondStatus('GET', '/svc/api/auth/me', 401);
        const dispatched: DispatchedRecord[] = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.USER_SILENT_PROBE_REQUESTED), buildCtx(() => ({}), dispatched));
        const assumed = dispatched.find((d) => d.type === CoreEvents.AUTH_ASSUMED_ANONYMOUS);
        const unauthorized = dispatched.find((d) => d.type === CoreEvents.AUTH_UNAUTHORIZED);
        expect(assumed).toBeTruthy();
        expect(unauthorized).toBeFalsy();
    });

    it('500 → ошибка эффекта без смены auth-состояния', async () => {
        fetchMock.respondStatus('GET', '/svc/api/auth/me', 500);
        const dispatched: DispatchedRecord[] = [];
        await expect(
            createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.USER_SILENT_PROBE_REQUESTED), buildCtx(() => ({}), dispatched)),
        ).rejects.toMatchObject({ status: 500 });
        expect(dispatched).toEqual([]);
    });
});

describe('authEffect: AUTH_LOGOUT_REQUESTED', () => {
    it('отказ сервера не выводит пользователя из сессии на клиенте', async () => {
        fetchMock.respondStatus('POST', '/svc/api/auth/logout', 500);
        const dispatched: DispatchedRecord[] = [];
        await expect(
            createAuthEffect({ baseUrl: '/svc' })(ev(CoreEvents.AUTH_LOGOUT_REQUESTED), buildCtx(() => ({}), dispatched)),
        ).rejects.toMatchObject({ status: 500 });
        expect(dispatched.find((d) => d.type === CoreEvents.AUTH_LOGGED_OUT)).toBeUndefined();
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
        const dispatched: DispatchedRecord[] = [];
        await createAuthEffect({ baseUrl: '/svc' })(
            ev(CoreEvents.AUTH_COMPANY_SWITCH_REQUESTED, { company_id: 'c2' }),
            buildCtx(() => ({}), dispatched),
        );
        const switched = dispatched.find((d) => d.type === CoreEvents.AUTH_COMPANY_SWITCHED);
        expect(switched?.payload).toEqual({ company_id: 'c2' });
    });
});

describe('authEffect: PROVIDERS_LOAD_REQUESTED', () => {
    it('успех → PROVIDERS_LOADED с items', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/providers', {
            providers: [{ name: 'google', display_name: 'Google', auth_url: '/api/v1/auth/login/google' }],
        });
        const dispatched: DispatchedRecord[] = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.PROVIDERS_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === CoreAuthEvents.PROVIDERS_LOADED);
        expect(prop(loaded?.payload, 'items')).toEqual([
            { name: 'google', display_name: 'Google', auth_url: '/api/v1/auth/login/google' },
        ]);
    });

    it('пустой список → PROVIDERS_LOAD_FAILED', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/providers', { providers: [] });
        const dispatched: DispatchedRecord[] = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.PROVIDERS_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const failed = dispatched.find((d) => d.type === CoreAuthEvents.PROVIDERS_LOAD_FAILED);
        expect(failed).toBeTruthy();
    });

    it('provider без name → PROVIDERS_LOAD_FAILED', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/providers', { providers: [{ id: 'google' }] });
        const dispatched: DispatchedRecord[] = [];
        await createAuthEffect({ baseUrl: '/svc' })(ev(CoreAuthEvents.PROVIDERS_LOAD_REQUESTED), buildCtx(() => ({}), dispatched));
        const failed = dispatched.find((d) => d.type === CoreAuthEvents.PROVIDERS_LOAD_FAILED);
        expect(failed).toBeTruthy();
        expect(prop(failed?.payload, 'message')).toMatch(/name/);
    });
});

describe('authEffect: SERVICE_ATTRS', () => {
    it('LOAD_REQUESTED → LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/api/auth/me/attrs/frontend', { theme: 'dark' });
        const dispatched: DispatchedRecord[] = [];
        await createAuthEffect({ baseUrl: '/svc' })(
            ev(CoreAuthEvents.SERVICE_ATTRS_LOAD_REQUESTED, { service: 'frontend' }),
            buildCtx(() => ({}), dispatched),
        );
        const loaded = dispatched.find((d) => d.type === CoreAuthEvents.SERVICE_ATTRS_LOADED);
        expect(loaded?.payload).toEqual({ service: 'frontend', attrs: { theme: 'dark' } });
    });

    it('UPDATE_REQUESTED требует service + attrs object', async () => {
        await expect(createAuthEffect({ baseUrl: '/svc' })(
            ev(CoreAuthEvents.SERVICE_ATTRS_UPDATE_REQUESTED, { service: 'x' }),
            buildCtx(() => ({}), []),
        )).rejects.toThrow(/attrs/);
    });
});
