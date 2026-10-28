/**
 * Эффект companies — список компаний пользователя, проверка slug, создание.
 */

import { httpRequest } from '../http.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import { COMPANIES_EVENTS } from '../reducers/companies.js';
import { isPlainRecord, payloadFields, stringField } from '../payload.js';

function errorMessage(err: unknown): string {
    if (err instanceof Error && err.message.length > 0) return err.message;
    if (isPlainRecord(err) && typeof err.message === 'string' && err.message.length > 0) return err.message;
    return String(err);
}

/** Создание и check-slug — только frontend API; GET /me — на baseUrl сервиса (core router). */
const FRONTEND_COMPANIES_API_PREFIX = '/frontend/api/companies';

export function createCompaniesEffect({ baseUrl }: { baseUrl?: string }): (event: PlatformEvent, ctx: EffectCtx) => Promise<void> {
    const base = typeof baseUrl === 'string' ? baseUrl : '';
    return async function companiesEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        switch (event.type) {
            case COMPANIES_EVENTS.LOAD_REQUESTED: {
                try {
                    const data = await httpRequest({ method: 'GET', url: `${base}/api/companies/me` });
                    if (!isPlainRecord(data) || !Array.isArray(data.items)) {
                        throw new Error('companies.effect: bad response shape');
                    }
                    ctx.dispatch(COMPANIES_EVENTS.LOADED, { items: data.items }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(COMPANIES_EVENTS.LOAD_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case COMPANIES_EVENTS.SLUG_CHECK_REQUESTED: {
                const slug = stringField(payloadFields(event).slug);
                if (slug === null) throw new Error('companies.effect: slug required');
                try {
                    const response = await httpRequest({ method: 'POST', url: `${FRONTEND_COMPANIES_API_PREFIX}/check-slug`, body: { slug } });
                    if (!isPlainRecord(response)) {
                        throw new Error('companies.effect: slug check response must be an object');
                    }
                    ctx.dispatch(COMPANIES_EVENTS.SLUG_CHECKED, { slug, available: response.available === true }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(COMPANIES_EVENTS.SLUG_CHECK_FAILED, { slug, message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case COMPANIES_EVENTS.CREATE_REQUESTED: {
                const fields = payloadFields(event);
                const name = stringField(fields.name);
                const slug = stringField(fields.slug);
                if (name === null || slug === null) throw new Error('companies.effect: name and slug required');
                try {
                    const data = await httpRequest({ method: 'POST', url: FRONTEND_COMPANIES_API_PREFIX, body: { name, slug } });
                    if (!isPlainRecord(data)) {
                        throw new Error('companies.effect: create response must be an object');
                    }
                    const redirectUrl = typeof data.redirect_url === 'string' ? data.redirect_url : null;
                    ctx.dispatch(
                        COMPANIES_EVENTS.CREATED,
                        { company: data, redirect_url: redirectUrl },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(COMPANIES_EVENTS.CREATE_FAILED, { message: errorMessage(err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            default:
                return;
        }
    };
}
