import { describe, it, expect } from 'vitest';
import { authReducer, initialAuthState } from '@platform/lib/events/reducers/auth.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { CoreAuthEvents } from '@platform/lib/events/effects/auth.effect.js';

const ev = (type, payload = null, ts = 1000) => ({ id: `id_${type}`, type, payload, meta: { ts, source: 'local' } });

describe('authReducer: initialAuthState', () => {
    it('заморожен и имеет ожидаемые поля', () => {
        expect(Object.isFrozen(initialAuthState)).toBe(true);
        expect(initialAuthState.status).toBe('unknown');
        expect(initialAuthState.user).toBeNull();
        expect(initialAuthState.activeCompanyId).toBeNull();
        expect(initialAuthState.providers).toEqual({ list: [], loading: false, error: null });
        expect(initialAuthState.sessionEndCause).toBeNull();
    });
});

describe('authReducer: events', () => {
    it('AUTH_LOGIN_REQUESTED → status=validating', () => {
        const next = authReducer(initialAuthState, ev(CoreEvents.AUTH_LOGIN_REQUESTED));
        expect(next.status).toBe('validating');
        expect(next.error).toBeNull();
    });

    it('AUTH_USER_LOADED заполняет user + status authenticated', () => {
        const user = { user_id: 'u1', name: 'Alice', company_id: 'c1' };
        const next = authReducer(initialAuthState, ev(CoreEvents.AUTH_USER_LOADED, { user }, 1234));
        expect(next.status).toBe('authenticated');
        expect(next.user).toBe(user);
        expect(next.activeCompanyId).toBe('c1');
        expect(next.lastValidatedAt).toBe(1234);
    });

    it('AUTH_LOGIN_FAILED → status=error + message', () => {
        const next = authReducer(initialAuthState, ev(CoreEvents.AUTH_LOGIN_FAILED, { message: 'nope' }));
        expect(next.status).toBe('error');
        expect(next.error).toBe('nope');
    });

    it('AUTH_UNAUTHORIZED сбрасывает state в unauthenticated с lost_session', () => {
        const seeded = authReducer(initialAuthState, ev(CoreEvents.AUTH_USER_LOADED, { user: { user_id: 'u' } }));
        const next = authReducer(seeded, ev(CoreEvents.AUTH_UNAUTHORIZED));
        expect(next.status).toBe('unauthenticated');
        expect(next.user).toBeNull();
        expect(next.sessionEndCause).toBe('lost_session');
    });

    it('AUTH_ASSUMED_ANONYMOUS → unauthenticated без sessionEndCause', () => {
        const seeded = authReducer(initialAuthState, ev(CoreEvents.AUTH_USER_LOADED, { user: { user_id: 'u' } }));
        const next = authReducer(seeded, ev(CoreEvents.AUTH_ASSUMED_ANONYMOUS));
        expect(next.status).toBe('unauthenticated');
        expect(next.user).toBeNull();
        expect(next.sessionEndCause).toBeNull();
    });

    it('AUTH_LOGGED_OUT сбрасывает state с logout', () => {
        const seeded = authReducer(initialAuthState, ev(CoreEvents.AUTH_USER_LOADED, { user: { user_id: 'u' } }));
        const next = authReducer(seeded, ev(CoreEvents.AUTH_LOGGED_OUT));
        expect(next.status).toBe('unauthenticated');
        expect(next.sessionEndCause).toBe('logout');
    });

    it('AUTH_USER_LOADED сбрасывает sessionEndCause', () => {
        const loggedOut = authReducer(initialAuthState, ev(CoreEvents.AUTH_LOGGED_OUT));
        expect(loggedOut.sessionEndCause).toBe('logout');
        const user = { user_id: 'u1', name: 'Alice', company_id: 'c1' };
        const recovered = authReducer(loggedOut, ev(CoreEvents.AUTH_USER_LOADED, { user }, 999));
        expect(recovered.sessionEndCause).toBeNull();
    });

    it('AUTH_COMPANY_SWITCHED меняет activeCompanyId', () => {
        const next = authReducer(initialAuthState, ev(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: 'c2' }));
        expect(next.activeCompanyId).toBe('c2');
    });

    it('AUTH_COMPANY_SWITCHED без company_id — no-op', () => {
        const next = authReducer(initialAuthState, ev(CoreEvents.AUTH_COMPANY_SWITCHED, {}));
        expect(next).toBe(initialAuthState);
    });

    it('PROVIDERS_LOADED без массива items — throw', () => {
        expect(() => authReducer(initialAuthState, ev(CoreAuthEvents.PROVIDERS_LOADED, { items: 'nope' }))).toThrow(/items/);
    });

    it('PROVIDERS_LOADED заполняет providers.list', () => {
        const next = authReducer(initialAuthState, ev(CoreAuthEvents.PROVIDERS_LOADED, { items: [{ id: 'google' }] }));
        expect(next.providers.list).toEqual([{ id: 'google' }]);
        expect(next.providers.loading).toBe(false);
    });

    it('SERVICE_ATTRS_LOADED мержит атрибуты сервиса', () => {
        const next = authReducer(initialAuthState, ev(CoreAuthEvents.SERVICE_ATTRS_LOADED, { service: 'frontend', attrs: { theme: 'dark' } }));
        expect(next.serviceAttrs.frontend).toEqual({ theme: 'dark' });
    });

    it('неизвестный event → identity', () => {
        const next = authReducer(initialAuthState, ev('unknown/event/x'));
        expect(next).toBe(initialAuthState);
    });
});
