/**
 * Companies effect — список компаний пользователя, проверка slug, создание.
 */

import { httpRequest } from '../http.js';
import { COMPANIES_EVENTS } from '../reducers/companies.js';

export function createCompaniesEffect({ baseUrl }) {
    const base = baseUrl || '';
    return async function companiesEffect(event, ctx) {
        switch (event.type) {
            case COMPANIES_EVENTS.LOAD_REQUESTED: {
                try {
                    const data = await httpRequest({ method: 'GET', url: `${base}/api/companies/me` });
                    if (!data || !Array.isArray(data.items)) {
                        throw new Error('companies.effect: bad response shape');
                    }
                    ctx.dispatch(COMPANIES_EVENTS.LOADED, { items: data.items }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(COMPANIES_EVENTS.LOAD_FAILED, { message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case COMPANIES_EVENTS.SLUG_CHECK_REQUESTED: {
                const slug = event.payload && event.payload.slug;
                if (!slug) throw new Error('companies.effect: slug required');
                try {
                    const r = await httpRequest({ method: 'POST', url: `${base}/api/companies/check-slug`, body: { slug } });
                    ctx.dispatch(COMPANIES_EVENTS.SLUG_CHECKED, { slug, available: !!r.available }, { causation_id: event.id, source: 'http' });
                } catch (err) {
                    ctx.dispatch(COMPANIES_EVENTS.SLUG_CHECK_FAILED, { slug, message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            case COMPANIES_EVENTS.CREATE_REQUESTED: {
                const { name, slug } = event.payload || {};
                if (!name || !slug) throw new Error('companies.effect: name and slug required');
                try {
                    const data = await httpRequest({ method: 'POST', url: `${base}/api/companies`, body: { name, slug } });
                    const redirectUrl = (data && typeof data.redirect_url === 'string') ? data.redirect_url : null;
                    ctx.dispatch(
                        COMPANIES_EVENTS.CREATED,
                        { company: data, redirect_url: redirectUrl },
                        { causation_id: event.id, source: 'http' },
                    );
                } catch (err) {
                    ctx.dispatch(COMPANIES_EVENTS.CREATE_FAILED, { message: String(err && err.message ? err.message : err) }, { causation_id: event.id, source: 'http' });
                }
                return;
            }
            default:
                return;
        }
    };
}
