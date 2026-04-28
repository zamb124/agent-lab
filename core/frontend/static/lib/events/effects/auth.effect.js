/**
 * Auth effect.
 *
 * Слушает (полный набор):
 *   auth/user/load_requested              → GET  /api/auth/me                     → AUTH_USER_LOADED|_FAILED
 *   auth/session/logout_requested         → POST /api/auth/logout                 → AUTH_LOGGED_OUT → редирект на корень платформы (apex)
 *   auth/company/switch_requested         → POST /api/auth/switch-company         → AUTH_COMPANY_SWITCHED
 *   auth/oauth/start_requested            → GET  /api/auth/login/<provider>       → AUTH_OAUTH_REDIRECTED
 *   auth/providers/load_requested         → GET  /api/auth/providers              → AUTH_PROVIDERS_LOADED|_FAILED
 *   auth/demo/status_requested            → GET  /api/auth/demo/status            → AUTH_DEMO_STATUS_LOADED
 *   auth/demo/login_requested             → POST /api/auth/login/demo             → AUTH_DEMO_LOGIN_SUCCEEDED|_FAILED
 *   auth/profile/update_requested         → PUT  /api/auth/me                     → AUTH_PROFILE_UPDATED
 *   auth/service_attrs/load_requested     → GET  /api/auth/me/attrs/<service>     → AUTH_SERVICE_ATTRS_LOADED
 *   auth/service_attrs/update_requested   → PUT  /api/auth/me/attrs/<service>     → AUTH_SERVICE_ATTRS_UPDATED
 */

import { CoreEvents } from '../contract.js';
import { httpRequest, HttpError } from '../http.js';
import { getPlatformApexOriginUrl } from '../../utils/tenant-url.js';

export const CoreAuthEvents = Object.freeze({
    USER_LOAD_REQUESTED:           'auth/user/load_requested',
    OAUTH_START_REQUESTED:         'auth/oauth/start_requested',
    OAUTH_REDIRECTED:              'auth/oauth/redirected',
    OAUTH_FAILED:                  'auth/oauth/failed',
    PROVIDERS_LOAD_REQUESTED:      'auth/providers/load_requested',
    PROVIDERS_LOADED:              'auth/providers/loaded',
    PROVIDERS_LOAD_FAILED:         'auth/providers/load_failed',
    DEMO_STATUS_REQUESTED:         'auth/demo/status_requested',
    DEMO_STATUS_LOADED:            'auth/demo/status_loaded',
    DEMO_LOGIN_REQUESTED:          'auth/demo/login_requested',
    DEMO_LOGIN_SUCCEEDED:          'auth/demo/login_succeeded',
    DEMO_LOGIN_FAILED:             'auth/demo/login_failed',
    PROFILE_UPDATE_REQUESTED:      'auth/profile/update_requested',
    PROFILE_UPDATED:               'auth/profile/updated',
    PROFILE_UPDATE_FAILED:         'auth/profile/update_failed',
    SERVICE_ATTRS_LOAD_REQUESTED:  'auth/service_attrs/load_requested',
    SERVICE_ATTRS_LOADED:          'auth/service_attrs/loaded',
    SERVICE_ATTRS_LOAD_FAILED:     'auth/service_attrs/load_failed',
    SERVICE_ATTRS_UPDATE_REQUESTED:'auth/service_attrs/update_requested',
    SERVICE_ATTRS_UPDATED:         'auth/service_attrs/updated',
});

export function createAuthEffect({ baseUrl }) {
    const base = baseUrl || '';

    return async function authEffect(event, ctx) {
        switch (event.type) {
            case CoreAuthEvents.USER_LOAD_REQUESTED: {
                try {
                    const data = await httpRequest({ method: 'GET', url: `${base}/api/auth/me` });
                    const user = {
                        id: data.user_id,
                        user_id: data.user_id,
                        name: data.name,
                        email: data.email,
                        avatar_url: data.avatar_url,
                        company_id: data.company_id,
                        roles: data.roles || [],
                        raw: data,
                    };
                    ctx.dispatch(CoreEvents.AUTH_USER_LOADED, { user }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    if (err instanceof HttpError && err.status === 401) {
                        ctx.dispatch(CoreEvents.AUTH_UNAUTHORIZED, { reason: 'me_returned_401' }, { causation_id: event.id, source: 'http' });
                        return;
                    }
                    ctx.dispatch(CoreEvents.AUTH_USER_FAILED, { message: String(err.message || err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreEvents.AUTH_LOGOUT_REQUESTED: {
                try {
                    await httpRequest({ method: 'POST', url: `${base}/api/auth/logout` });
                } catch (err) {
                    console.warn('[auth.effect] logout HTTP failed', err);
                }
                ctx.dispatch(CoreEvents.AUTH_LOGGED_OUT, null, { causation_id: event.id, source: 'http' });
                if (typeof globalThis.window !== 'undefined' && globalThis.window.location) {
                    globalThis.window.location.href = getPlatformApexOriginUrl();
                }
                return;
            }

            case CoreEvents.AUTH_COMPANY_SWITCH_REQUESTED: {
                const companyId = event.payload && event.payload.company_id;
                if (!companyId) throw new Error('auth.effect: company_id required');
                await httpRequest({ method: 'POST', url: `${base}/api/auth/switch-company`, body: { company_id: companyId } });
                ctx.dispatch(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: companyId }, { causation_id: event.id, source: 'http' });
                return;
            }

            case CoreAuthEvents.OAUTH_START_REQUESTED: {
                const { provider, return_path: returnPath } = event.payload || {};
                if (!provider) throw new Error('auth.effect: provider required');
                const path = returnPath
                    ? `${base}/api/auth/login/${encodeURIComponent(provider)}?return_path=${encodeURIComponent(returnPath)}`
                    : `${base}/api/auth/login/${encodeURIComponent(provider)}`;
                try {
                    const r = await httpRequest({ method: 'GET', url: path });
                    if (!r.auth_url) throw new Error('no auth_url');
                    ctx.dispatch(CoreAuthEvents.OAUTH_REDIRECTED, { provider, auth_url: r.auth_url }, { causation_id: event.id, source: 'http' });
                    window.location.href = r.auth_url;
                } catch (err) {
                    ctx.dispatch(CoreAuthEvents.OAUTH_FAILED, { provider, message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.PROVIDERS_LOAD_REQUESTED: {
                try {
                    const r = await httpRequest({ method: 'GET', url: `${base}/api/auth/providers` });
                    if (!Array.isArray(r.providers) || r.providers.length === 0) {
                        throw new Error('empty providers list');
                    }
                    ctx.dispatch(CoreAuthEvents.PROVIDERS_LOADED, { items: r.providers }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CoreAuthEvents.PROVIDERS_LOAD_FAILED, { message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.DEMO_STATUS_REQUESTED: {
                const r = await httpRequest({ method: 'GET', url: `${base}/api/auth/demo/status` });
                ctx.dispatch(CoreAuthEvents.DEMO_STATUS_LOADED, r, { causation_id: event.id, source: 'http' });
                return;
            }

            case CoreAuthEvents.DEMO_LOGIN_REQUESTED: {
                const { email, password } = event.payload || {};
                if (!email || !password) throw new Error('auth.effect: email and password required');
                try {
                    const r = await httpRequest({ method: 'POST', url: `${base}/api/auth/login/demo`, body: { email, password } });
                    if (!r.redirect_url) throw new Error('no redirect_url');
                    ctx.dispatch(CoreAuthEvents.DEMO_LOGIN_SUCCEEDED, { redirect_url: r.redirect_url }, { causation_id: event.id, source: 'http' });
                    window.location.href = r.redirect_url;
                } catch (err) {
                    ctx.dispatch(CoreAuthEvents.DEMO_LOGIN_FAILED, { message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.PROFILE_UPDATE_REQUESTED: {
                const updates = event.payload && event.payload.updates;
                if (!updates || typeof updates !== 'object') throw new Error('auth.effect: updates required');
                try {
                    const r = await httpRequest({ method: 'PUT', url: `${base}/api/auth/me`, body: updates });
                    ctx.dispatch(CoreAuthEvents.PROFILE_UPDATED, { user: r }, { causation_id: event.id, source: 'http' });
                    ctx.dispatch(CoreAuthEvents.USER_LOAD_REQUESTED, null, { causation_id: event.id });
                } catch (err) {
                    ctx.dispatch(CoreAuthEvents.PROFILE_UPDATE_FAILED, { message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.SERVICE_ATTRS_LOAD_REQUESTED: {
                const service = event.payload && event.payload.service;
                if (!service) throw new Error('auth.effect: service required');
                try {
                    const attrs = await httpRequest({ method: 'GET', url: `${base}/api/auth/me/attrs/${encodeURIComponent(service)}` });
                    ctx.dispatch(CoreAuthEvents.SERVICE_ATTRS_LOADED, { service, attrs }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CoreAuthEvents.SERVICE_ATTRS_LOAD_FAILED, { service, message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.SERVICE_ATTRS_UPDATE_REQUESTED: {
                const { service, attrs } = event.payload || {};
                if (!service || !attrs || typeof attrs !== 'object') throw new Error('auth.effect: service and attrs required');
                const r = await httpRequest({ method: 'PUT', url: `${base}/api/auth/me/attrs/${encodeURIComponent(service)}`, body: attrs });
                ctx.dispatch(CoreAuthEvents.SERVICE_ATTRS_UPDATED, { service, attrs: r }, { causation_id: event.id, source: 'http' });
                return;
            }

            default:
                return;
        }
    };
}
