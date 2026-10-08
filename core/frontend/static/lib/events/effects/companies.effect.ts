/**
 * Эффект companies — список компаний пользователя, проверка slug, создание.
 */

import { httpRequest } from '../http.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { COMPANIES_EVENTS } from '../reducers/companies.js';

/** Создание и check-slug — только frontend API; GET /me — на baseUrl сервиса (core router). */
const FRONTEND_COMPANIES_API_PREFIX = '/frontend/api/companies';

export function createCompaniesEffect({ baseUrl }: { baseUrl?: string }): (event: PlatformEvent, ctx: EffectCtx) => Promise<void> {
    const base = baseUrl || '';
    return async function companiesEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        switch (event.type) {
            case COMPANIES_EVENTS.LOAD_REQUESTED: {
                try {
                    const data = await httpRequest({ method: 'GET', url: `${base}/api/companies/me` }) as { items?: unknown } | null;
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('companies.effect: bad response shape');
                    }
                    ctx.dispatch(COMPANIES_EVENTS.LOADED, { items: data.items }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(COMPANIES_EVENTS.LOAD_FAILED, { message: String(err && (err as Error).message ? (err as Error).message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case COMPANIES_EVENTS.SLUG_CHECK_REQUESTED: {
                const slug = ((event.payload ?? {}) as { slug?: unknown }).slug;
                if (typeof slug !== 'string' || !slug) throw new Error('companies.effect: slug required');
                try {
                    const r = await httpRequest({ method: 'POST', url: `${FRONTEND_COMPANIES_API_PREFIX}/check-slug`, body: { slug } }) as { available?: unknown };
                    ctx.dispatch(COMPANIES_EVENTS.SLUG_CHECKED, { slug, available: !!r.available }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(COMPANIES_EVENTS.SLUG_CHECK_FAILED, { slug, message: String(err && (err as Error).message ? (err as Error).message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case COMPANIES_EVENTS.CREATE_REQUESTED: {
                const { name, slug } = (event.payload ?? {}) as { name?: string; slug?: string };
                if (!name || !slug) throw new Error('companies.effect: name and slug required');
                try {
                    const data = await httpRequest({ method: 'POST', url: FRONTEND_COMPANIES_API_PREFIX, body: { name, slug } }) as { redirect_url?: unknown } | null;
                    const redirectUrl = (data && typeof data.redirect_url === 'string') ? data.redirect_url : null;
                    ctx.dispatch(
                        COMPANIES_EVENTS.CREATED,
                        { company: data, redirect_url: redirectUrl },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(COMPANIES_EVENTS.CREATE_FAILED, { message: String(err && (err as Error).message ? (err as Error).message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            default:
                return;
        }
    };
}
