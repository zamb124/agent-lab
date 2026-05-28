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
import { CoreAuthEvents } from '../effects/auth.effect.js';

export const initialAuthState = Object.freeze({
    status: 'unknown',
    user: null,
    activeCompanyId: null,
    error: null,
    lastValidatedAt: null,
    providers: { list: [], loading: false, error: null },
    demo: { enabled: false, email: null },
    serviceAttrs: {},
    sessionEndCause: null,
});

export function authReducer(state = initialAuthState, event) {
    switch (event.type) {
        case CoreEvents.AUTH_LOGIN_REQUESTED:
            return { ...state, status: 'validating', error: null };

        case CoreEvents.AUTH_USER_LOADED:
        case CoreEvents.AUTH_VALIDATED:
        case CoreEvents.AUTH_LOGIN_SUCCEEDED: {
            const user = event.payload && event.payload.user ? event.payload.user : null;
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
                error: event.payload && event.payload.message ? event.payload.message : 'auth_error',
                sessionEndCause: null,
            };

        case CoreEvents.AUTH_UNAUTHORIZED:
            return { ...initialAuthState, status: 'unauthenticated', sessionEndCause: 'lost_session' };

        case CoreEvents.AUTH_ASSUMED_ANONYMOUS:
            return {
                ...initialAuthState,
                status: 'unauthenticated',
                sessionEndCause: null,
            };

        case CoreEvents.AUTH_LOGGED_OUT:
            return { ...initialAuthState, status: 'unauthenticated', sessionEndCause: 'logout' };

        case CoreEvents.AUTH_COMPANY_SWITCHED: {
            const companyId = event.payload && event.payload.company_id ? event.payload.company_id : null;
            if (!companyId) return state;
            return { ...state, activeCompanyId: companyId };
        }

        case CoreAuthEvents.PROVIDERS_LOAD_REQUESTED:
            return { ...state, providers: { ...state.providers, loading: true, error: null } };
        case CoreAuthEvents.PROVIDERS_LOADED: {
            if (!event.payload || !Array.isArray(event.payload.items)) {
                throw new Error(`${event.type}: payload.items must be an array`);
            }
            return { ...state, providers: { list: event.payload.items, loading: false, error: null } };
        }
        case CoreAuthEvents.PROVIDERS_LOAD_FAILED:
            return { ...state, providers: { ...state.providers, loading: false, error: event.payload && event.payload.message } };

        case CoreAuthEvents.DEMO_STATUS_LOADED: {
            const p = event.payload || {};
            return { ...state, demo: { enabled: !!p.enabled, email: p.email || null } };
        }

        case CoreAuthEvents.SERVICE_ATTRS_LOADED:
        case CoreAuthEvents.SERVICE_ATTRS_UPDATED: {
            const service = event.payload && event.payload.service;
            const attrs = event.payload && event.payload.attrs;
            if (!service) return state;
            return { ...state, serviceAttrs: { ...state.serviceAttrs, [service]: attrs || {} } };
        }

        default:
            return state;
    }
}
