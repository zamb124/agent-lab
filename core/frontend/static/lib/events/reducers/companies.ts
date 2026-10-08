/**
 * Слайс companies.
 *
 * state.companies:
 *   list:        Array - my companies
 *   loading:     boolean
 *   error:       string|null
 *   slugChecks:  { [slug]: { available: boolean } }
 *
 * Активная компания сессии — в state.auth (`activeCompanyId`, `user.company_id`), не здесь.
 */

import type { PlatformEvent } from '../contract.js';

export interface CompanyRecord extends Record<string, unknown> {}

export interface CompaniesState {
    list: CompanyRecord[];
    loading: boolean;
    error: string | null;
    slugChecks: Record<string, { available: boolean }>;
}

export const COMPANIES_EVENTS = Object.freeze({
    LOAD_REQUESTED:   'companies/list/load_requested',
    LOADED:           'companies/list/loaded',
    LOAD_FAILED:      'companies/list/load_failed',
    SLUG_CHECK_REQUESTED: 'companies/slug/check_requested',
    SLUG_CHECKED:         'companies/slug/checked',
    SLUG_CHECK_FAILED:    'companies/slug/check_failed',
    CREATE_REQUESTED: 'companies/company/create_requested',
    CREATED:          'companies/company/created',
    CREATE_FAILED:    'companies/company/create_failed',
});

export const initialCompaniesState: CompaniesState = Object.freeze({
    list: [],
    loading: false,
    error: null,
    slugChecks: {},
});

export function companiesReducer(state: CompaniesState = initialCompaniesState, event: PlatformEvent): CompaniesState {
    switch (event.type) {
        case COMPANIES_EVENTS.LOAD_REQUESTED:
            return { ...state, loading: true, error: null };
        case COMPANIES_EVENTS.LOADED: {
            const items = ((event.payload || {}) as { items?: unknown }).items;
            if (!Array.isArray(items)) {
                throw new Error(`${event.type}: payload.items must be an array`);
            }
            return { ...state, loading: false, list: items as CompanyRecord[] };
        }
        case COMPANIES_EVENTS.LOAD_FAILED:
            const msg = ((event.payload || {}) as { message?: unknown }).message;
            return { ...state, loading: false, error: typeof msg === 'string' ? msg : null };
        case COMPANIES_EVENTS.SLUG_CHECKED: {
            const p = (event.payload || {}) as { slug?: unknown; available?: unknown };
            if (typeof p.slug !== 'string' || !p.slug) return state;
            return { ...state, slugChecks: { ...state.slugChecks, [p.slug]: { available: !!p.available } } };
        }
        case COMPANIES_EVENTS.CREATED: {
            const company = ((event.payload || {}) as { company?: CompanyRecord }).company;
            if (!company) return state;
            return { ...state, list: [...state.list, company] };
        }
        default:
            return state;
    }
}

export const companiesSlice = { reducer: companiesReducer, initial: initialCompaniesState };
