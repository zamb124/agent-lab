/**
 * Слайс auth.
 *
 * Поля state.auth:
 *   status:        'unknown' | 'validating' | 'authenticated' | 'unauthenticated' | 'error'
 *   user:          object|null
 *   activeCompanyId: string|null
 *   error:         string|null
 *   lastValidatedAt: number|null
 *   providers:     { list, loading, error }
 *   demo:          { enabled, email }
 *   serviceAttrs:  { [service]: object }
 *   sessionEndCause: null | 'logout' | 'lost_session' — последняя причина unauthenticated (для UX редиректа)
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent } from '../contract.js';

export type AuthStatus = 'unknown' | 'validating' | 'authenticated' | 'unauthenticated' | 'error';

export interface AuthUser extends Record<string, unknown> {
    company_id?: string;
}

export interface AuthProvidersState {
    list: Record<string, unknown>[];
    loading: boolean;
    error: string | null;
}

export interface AuthState {
    status: AuthStatus;
    user: AuthUser | null;
    activeCompanyId: string | null;
    error: string | null;
    lastValidatedAt: number | null;
    providers: AuthProvidersState;
    demo: { enabled: boolean; email: string | null; loaded: boolean };
    serviceAttrs: Record<string, Record<string, unknown>>;
    sessionEndCause: string | null;
}
import { CoreAuthEvents } from '../effects/auth.effect.js';

export const initialAuthState: AuthState = Object.freeze({
    status: 'unknown',
    user: null,
    activeCompanyId: null,
    error: null,
    lastValidatedAt: null,
    providers: { list: [], loading: false, error: null },
    demo: { enabled: false, email: null, loaded: false },
    serviceAttrs: {},
    sessionEndCause: null,
});

/** Публичный OAuth/demo-конфиг не зависит от сессии — сохраняем при logout/anonymous. */
function _sessionReset(state: AuthState, { status, sessionEndCause }: { status: AuthStatus; sessionEndCause: string | null }): AuthState {
    return {
        ...initialAuthState,
        status,
        sessionEndCause,
        providers: state.providers,
        demo: state.demo,
    };
}

export function authReducer(state: AuthState = initialAuthState, event: PlatformEvent): AuthState {
    switch (event.type) {
        case CoreEvents.AUTH_LOGIN_REQUESTED:
            return { ...state, status: 'validating', error: null };

        case CoreEvents.AUTH_USER_LOADED:
        case CoreEvents.AUTH_VALIDATED:
        case CoreEvents.AUTH_LOGIN_SUCCEEDED: {
            const rawUser = ((event.payload || {}) as { user?: unknown }).user;
            const user = rawUser && typeof rawUser === 'object' ? rawUser as AuthUser : null;
            return {
                ...state,
                status: 'authenticated',
                user,
                activeCompanyId: user ? (user.company_id || null) : state.activeCompanyId,
                error: null,
                lastValidatedAt: event.meta.ts,
                sessionEndCause: null,
            };
        }

        case CoreEvents.AUTH_USER_FAILED:
        case CoreEvents.AUTH_LOGIN_FAILED:
            return {
                ...state,
                status: 'error',
                user: null,
                activeCompanyId: null,
                error: typeof ((event.payload || {}) as { message?: unknown }).message === 'string'
                    ? ((event.payload || {}) as { message: string }).message
                    : 'auth_error',
                sessionEndCause: null,
            };

        case CoreEvents.AUTH_UNAUTHORIZED:
            return _sessionReset(state, { status: 'unauthenticated', sessionEndCause: 'lost_session' });

        case CoreEvents.AUTH_ASSUMED_ANONYMOUS:
            return _sessionReset(state, { status: 'unauthenticated', sessionEndCause: null });

        case CoreEvents.AUTH_LOGGED_OUT:
            return _sessionReset(state, { status: 'unauthenticated', sessionEndCause: 'logout' });

        case CoreEvents.AUTH_COMPANY_SWITCHED: {
            const companyId = ((event.payload || {}) as { company_id?: unknown }).company_id;
            if (typeof companyId !== 'string' || !companyId) return state;
            return { ...state, activeCompanyId: companyId };
        }

        case CoreAuthEvents.PROVIDERS_LOAD_REQUESTED:
            return { ...state, providers: { ...state.providers, loading: true, error: null } };
        case CoreAuthEvents.PROVIDERS_LOADED: {
            const items = ((event.payload || {}) as { items?: unknown }).items;
            if (!Array.isArray(items)) {
                throw new Error(`${event.type}: payload.items must be an array`);
            }
            return { ...state, providers: { list: items as Record<string, unknown>[], loading: false, error: null } };
        }
        case CoreAuthEvents.PROVIDERS_LOAD_FAILED:
            const msg = ((event.payload || {}) as { message?: unknown }).message;
            return { ...state, providers: { ...state.providers, loading: false, error: typeof msg === 'string' ? msg : null } };

        case CoreAuthEvents.DEMO_STATUS_LOADED: {
            const p = (event.payload || {}) as { enabled?: unknown; email?: unknown };
            return {
                ...state,
                demo: {
                    enabled: !!p.enabled,
                    email: typeof p.email === 'string' ? p.email : null,
                    loaded: true,
                },
            };
        }

        case CoreAuthEvents.SERVICE_ATTRS_LOADED:
        case CoreAuthEvents.SERVICE_ATTRS_UPDATED: {
            const p = (event.payload || {}) as { service?: unknown; attrs?: unknown };
            if (typeof p.service !== 'string' || !p.service) return state;
            const attrs = p.attrs && typeof p.attrs === 'object' ? p.attrs as Record<string, unknown> : {};
            return { ...state, serviceAttrs: { ...state.serviceAttrs, [p.service]: attrs } };
        }

        default:
            return state;
    }
}
