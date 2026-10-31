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
    company_id?: string | undefined;
    name?: string | undefined;
    raw?: Record<string, unknown> | undefined;
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
import { isPlainRecord, payloadFields, stringField } from '../payload.js';

function isAuthUser(value: unknown): value is AuthUser {
    return isPlainRecord(value);
}

function authUser(value: unknown): AuthUser | null {
    if (value === undefined || value === null) return null;
    if (!isAuthUser(value)) throw new Error('auth: user must be an object');
    return value;
}

function providerItems(value: unknown, eventType: string): Record<string, unknown>[] {
    if (!Array.isArray(value)) {
        throw new Error(`${eventType}: payload.items must be an array`);
    }
    const items: Record<string, unknown>[] = [];
    for (const item of value) {
        if (!isPlainRecord(item)) throw new Error(`${eventType}: provider item must be an object`);
        items.push(item);
    }
    return items;
}

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
            const user = authUser(payloadFields(event).user);
            return {
                ...state,
                status: 'authenticated',
                user,
                activeCompanyId: user
                    ? (typeof user.company_id === 'string' && user.company_id.length > 0 ? user.company_id : null)
                    : state.activeCompanyId,
                error: null,
                lastValidatedAt: event.meta.ts,
                sessionEndCause: null,
            };
        }

        case CoreEvents.AUTH_USER_FAILED:
        case CoreEvents.AUTH_LOGIN_FAILED: {
            const message = stringField(payloadFields(event).message);
            return {
                ...state,
                status: 'error',
                user: null,
                activeCompanyId: null,
                error: message === null ? 'auth_error' : message,
                sessionEndCause: null,
            };
        }

        case CoreEvents.AUTH_UNAUTHORIZED:
            return _sessionReset(state, { status: 'unauthenticated', sessionEndCause: 'lost_session' });

        case CoreEvents.AUTH_ASSUMED_ANONYMOUS:
            return _sessionReset(state, { status: 'unauthenticated', sessionEndCause: null });

        case CoreEvents.AUTH_LOGGED_OUT:
            return _sessionReset(state, { status: 'unauthenticated', sessionEndCause: 'logout' });

        case CoreEvents.AUTH_COMPANY_SWITCHED: {
            const companyId = (payloadFields(event)).company_id;
            if (typeof companyId !== 'string' || !companyId) return state;
            return { ...state, activeCompanyId: companyId };
        }

        case CoreAuthEvents.PROVIDERS_LOAD_REQUESTED:
            return { ...state, providers: { ...state.providers, loading: true, error: null } };
        case CoreAuthEvents.PROVIDERS_LOADED: {
            const items = providerItems(payloadFields(event).items, event.type);
            return { ...state, providers: { list: items, loading: false, error: null } };
        }
        case CoreAuthEvents.PROVIDERS_LOAD_FAILED:
            const msg = (payloadFields(event)).message;
            return { ...state, providers: { ...state.providers, loading: false, error: typeof msg === 'string' ? msg : null } };

        case CoreAuthEvents.DEMO_STATUS_LOADED: {
            const p = payloadFields(event);
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
            const p = payloadFields(event);
            const service = p.service;
            if (typeof service !== 'string' || service.length === 0) return state;
            const attrs = p.attrs;
            if (!isPlainRecord(attrs)) {
                throw new Error(`${event.type}: attrs must be an object`);
            }
            return { ...state, serviceAttrs: { ...state.serviceAttrs, [service]: attrs } };
        }

        default:
            return state;
    }
}
