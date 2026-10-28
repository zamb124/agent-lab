/**
 * Эффект auth.
 *
 * Слушает (полный набор):
 *   auth/user/load_requested              → GET  /api/auth/me                     → AUTH_USER_LOADED|_FAILED
 *   auth/user/silent_probe_requested      → GET  /api/auth/me                     → AUTH_USER_LOADED (сессия валидна) | AUTH_ASSUMED_ANONYMOUS (401/сбой)
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
import { getPlatformApexOriginUrl } from '../../utils/company-url.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { isPlainRecord, payloadFields, stringField } from '../payload.js';
import type { AuthUser } from '../reducers/auth.js';

export const CoreAuthEvents = Object.freeze({
    USER_LOAD_REQUESTED:           'auth/user/load_requested',
    USER_SILENT_PROBE_REQUESTED:   'auth/user/silent_probe_requested',
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

function errorMessage(err: unknown): string {
    if (err instanceof Error && err.message.length > 0) {
        return err.message;
    }
    if (isPlainRecord(err) && typeof err.message === 'string' && err.message.length > 0) {
        return err.message;
    }
    return String(err);
}

function isAuthMeResponse(value: unknown): value is AuthMeResponse {
    if (!isPlainRecord(value) || typeof value.can_admin !== 'boolean') {
        return false;
    }
    for (const key of ['user_id', 'name', 'email', 'avatar_url', 'company_id'] as const) {
        const field = value[key];
        if (field !== undefined && typeof field !== 'string') {
            return false;
        }
    }
    if (value.roles !== undefined && (!Array.isArray(value.roles) || value.roles.some((role) => typeof role !== 'string'))) {
        return false;
    }
    return true;
}

function requireAuthUrl(value: unknown, field: 'auth_url' | 'redirect_url'): string {
    const url = isPlainRecord(value) ? value[field] : undefined;
    if (typeof url !== 'string' || url.length === 0) {
        throw new Error(`no ${field}`);
    }
    return url;
}

function providerItems(value: unknown): { name: string; display_name: string; auth_url: string }[] {
    if (!isPlainRecord(value) || !Array.isArray(value.providers) || value.providers.length === 0) {
        throw new Error('empty providers list');
    }
    return value.providers.map((raw) => {
        if (!isPlainRecord(raw) || typeof raw.name !== 'string' || raw.name.length === 0) {
            throw new Error('provider item.name must be a non-empty string');
        }
        return {
            name: raw.name,
            display_name: typeof raw.display_name === 'string' ? raw.display_name : raw.name,
            auth_url: typeof raw.auth_url === 'string' ? raw.auth_url : '',
        };
    });
}

interface AuthMeResponse extends Record<string, unknown> {
    user_id?: string; name?: string; email?: string; avatar_url?: string;
    company_id?: string; roles?: string[]; can_admin?: boolean;
}

export function createAuthEffect({ baseUrl }: { baseUrl?: string }): (event: PlatformEvent, ctx: EffectCtx) => Promise<void> {
    const base = baseUrl === undefined ? '' : baseUrl;

    async function fetchCurrentUser(): Promise<AuthUser> {
        const data = await httpRequest({ method: 'GET', url: `${base}/api/auth/me` });
        if (!isPlainRecord(data) || typeof data.can_admin !== 'boolean') {
            throw new Error('auth/me: can_admin must be a boolean');
        }
        if (!isAuthMeResponse(data)) {
            throw new Error('auth/me: response fields must be strings');
        }
        return {
            id: data.user_id,
            user_id: data.user_id,
            name: data.name,
            email: data.email,
            avatar_url: data.avatar_url,
            company_id: data.company_id,
            roles: Array.isArray(data.roles) ? data.roles : [],
            canAdmin: data.can_admin,
            raw: data,
        };
    }

    return async function authEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        switch (event.type) {
            case CoreAuthEvents.USER_LOAD_REQUESTED: {
                try {
                    const user = await fetchCurrentUser();
                    ctx.dispatch(CoreEvents.AUTH_USER_LOADED, { user }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    if (err instanceof HttpError && err.status === 401) {
                        ctx.dispatch(CoreEvents.AUTH_UNAUTHORIZED, { reason: 'me_returned_401' }, { causation_id: event.id, source: 'http' });
                        return;
                    }
                    ctx.dispatch(CoreEvents.AUTH_USER_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.USER_SILENT_PROBE_REQUESTED: {
                // Публичная страница уже рендерится анонимом (AUTH_ASSUMED_ANONYMOUS).
                // Фоновая проба апгрейдит auth до authenticated, когда сессия валидна,
                // чтобы залогиненный пользователь видел «Dashboard» в шапке лендинга.
                try {
                    const user = await fetchCurrentUser();
                    ctx.dispatch(CoreEvents.AUTH_USER_LOADED, { user }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    if (err instanceof HttpError && err.status === 401) {
                        ctx.dispatch(CoreEvents.AUTH_ASSUMED_ANONYMOUS, null, { causation_id: event.id, source: 'http' });
                        return;
                    }
                    throw err;
                }
                return;
            }

            case CoreEvents.AUTH_LOGOUT_REQUESTED: {
                await httpRequest({ method: 'POST', url: `${base}/api/auth/logout` });
                ctx.dispatch(CoreEvents.AUTH_LOGGED_OUT, null, { causation_id: event.id, source: 'http' });
                if (typeof globalThis.window !== 'undefined' && globalThis.window.location) {
                    globalThis.window.location.href = getPlatformApexOriginUrl();
                }
                return;
            }

            case CoreEvents.AUTH_COMPANY_SWITCH_REQUESTED: {
                const companyId = stringField(payloadFields(event).company_id);
                if (companyId === null) throw new Error('auth.effect: company_id required');
                await httpRequest({ method: 'POST', url: `${base}/api/auth/switch-company`, body: { company_id: companyId } });
                ctx.dispatch(CoreEvents.AUTH_COMPANY_SWITCHED, { company_id: companyId }, { causation_id: event.id, source: 'http' });
                return;
            }

            case CoreAuthEvents.OAUTH_START_REQUESTED: {
                const fields = payloadFields(event);
                const provider = stringField(fields.provider);
                const returnPath = stringField(fields.return_path);
                if (provider === null) throw new Error('auth.effect: provider required');
                const path = returnPath !== null
                    ? `${base}/api/auth/login/${encodeURIComponent(provider)}?return_path=${encodeURIComponent(returnPath)}`
                    : `${base}/api/auth/login/${encodeURIComponent(provider)}`;
                try {
                    const authUrl = requireAuthUrl(await httpRequest({ method: 'GET', url: path }), 'auth_url');
                    ctx.dispatch(CoreAuthEvents.OAUTH_REDIRECTED, { provider, auth_url: authUrl }, { causation_id: event.id, source: 'http' });
                    window.location.href = authUrl;
                } catch (err) {
                    ctx.dispatch(CoreAuthEvents.OAUTH_FAILED, { provider, message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.PROVIDERS_LOAD_REQUESTED: {
                try {
                    const items = providerItems(await httpRequest({ method: 'GET', url: `${base}/api/auth/providers` }));
                    ctx.dispatch(CoreAuthEvents.PROVIDERS_LOADED, { items }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CoreAuthEvents.PROVIDERS_LOAD_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.DEMO_STATUS_REQUESTED: {
                const r = await httpRequest({ method: 'GET', url: `${base}/api/auth/demo/status` });
                ctx.dispatch(CoreAuthEvents.DEMO_STATUS_LOADED, r, { causation_id: event.id, source: 'http' });
                return;
            }

            case CoreAuthEvents.DEMO_LOGIN_REQUESTED: {
                const fields = payloadFields(event);
                const email = stringField(fields.email);
                const password = stringField(fields.password);
                if (email === null || password === null) throw new Error('auth.effect: email and password required');
                try {
                    const redirectUrl = requireAuthUrl(
                        await httpRequest({ method: 'POST', url: `${base}/api/auth/login/demo`, body: { email, password } }),
                        'redirect_url',
                    );
                    ctx.dispatch(CoreAuthEvents.DEMO_LOGIN_SUCCEEDED, { redirect_url: redirectUrl }, { causation_id: event.id, source: 'http' });
                    window.location.href = redirectUrl;
                } catch (err) {
                    ctx.dispatch(CoreAuthEvents.DEMO_LOGIN_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.PROFILE_UPDATE_REQUESTED: {
                const updates = payloadFields(event).updates;
                if (!isPlainRecord(updates)) throw new Error('auth.effect: updates required');
                try {
                    const r = await httpRequest({ method: 'PUT', url: `${base}/api/auth/me`, body: updates });
                    ctx.dispatch(CoreAuthEvents.PROFILE_UPDATED, { user: r }, { causation_id: event.id, source: 'http' });
                    ctx.dispatch(CoreAuthEvents.USER_LOAD_REQUESTED, null, { causation_id: event.id });
                } catch (err) {
                    ctx.dispatch(CoreAuthEvents.PROFILE_UPDATE_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.SERVICE_ATTRS_LOAD_REQUESTED: {
                const service = stringField(payloadFields(event).service);
                if (service === null) throw new Error('auth.effect: service required');
                try {
                    const attrs = await httpRequest({ method: 'GET', url: `${base}/api/auth/me/attrs/${encodeURIComponent(service)}` });
                    ctx.dispatch(CoreAuthEvents.SERVICE_ATTRS_LOADED, { service, attrs }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(CoreAuthEvents.SERVICE_ATTRS_LOAD_FAILED, { service, message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }

            case CoreAuthEvents.SERVICE_ATTRS_UPDATE_REQUESTED: {
                const fields = payloadFields(event);
                const service = stringField(fields.service);
                const attrs = fields.attrs;
                if (service === null || !isPlainRecord(attrs)) throw new Error('auth.effect: service and attrs required');
                const r = await httpRequest({ method: 'PUT', url: `${base}/api/auth/me/attrs/${encodeURIComponent(service)}`, body: attrs });
                ctx.dispatch(CoreAuthEvents.SERVICE_ATTRS_UPDATED, { service, attrs: r }, { causation_id: event.id, source: 'http' });
                return;
            }

            default:
                return;
        }
    };
}
