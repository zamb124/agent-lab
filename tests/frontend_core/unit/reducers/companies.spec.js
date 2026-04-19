import { describe, it, expect } from 'vitest';
import { companiesReducer, initialCompaniesState, COMPANIES_EVENTS, companiesSlice } from '@platform/lib/events/reducers/companies.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('companiesReducer', () => {
    it('initial', () => {
        expect(initialCompaniesState.list).toEqual([]);
        expect(companiesSlice.initial).toBe(initialCompaniesState);
    });

    it('LOAD_REQUESTED → loading=true, error=null', () => {
        const seeded = { ...initialCompaniesState, error: 'old' };
        const next = companiesReducer(seeded, ev(COMPANIES_EVENTS.LOAD_REQUESTED));
        expect(next.loading).toBe(true);
        expect(next.error).toBeNull();
    });

    it('LOADED заполняет list', () => {
        const next = companiesReducer(initialCompaniesState, ev(COMPANIES_EVENTS.LOADED, { items: [{ id: 'c1' }] }));
        expect(next.list).toEqual([{ id: 'c1' }]);
        expect(next.loading).toBe(false);
    });

    it('LOADED без массива — throw', () => {
        expect(() => companiesReducer(initialCompaniesState, ev(COMPANIES_EVENTS.LOADED, {}))).toThrow(/items/);
    });

    it('LOAD_FAILED фиксирует error', () => {
        const next = companiesReducer(initialCompaniesState, ev(COMPANIES_EVENTS.LOAD_FAILED, { message: 'no auth' }));
        expect(next.error).toBe('no auth');
        expect(next.loading).toBe(false);
    });

    it('SLUG_CHECKED заполняет slugChecks', () => {
        const next = companiesReducer(initialCompaniesState, ev(COMPANIES_EVENTS.SLUG_CHECKED, { slug: 'foo', available: true }));
        expect(next.slugChecks.foo).toEqual({ available: true });
    });

    it('CREATED добавляет в list', () => {
        const next = companiesReducer(initialCompaniesState, ev(COMPANIES_EVENTS.CREATED, { company: { id: 'c2' } }));
        expect(next.list).toEqual([{ id: 'c2' }]);
    });
});
