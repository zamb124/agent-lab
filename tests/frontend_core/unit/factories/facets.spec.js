/**
 * createFacets: typeahead-фабрика. Контракт + reducer + debounced effect.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createFacets } from '@platform/lib/events/factories/facets.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';

let fetchMock;
beforeEach(() => { resetFactories(); fetchMock = installFetchMock(); vi.useFakeTimers(); });
afterEach(() => { resetFactories(); fetchMock.uninstall(); vi.useRealTimers(); });

const opts = (overrides = {}) => ({
    name: 'svc/tracing',
    baseUrl: '/api/facets',
    facets: { company: 'companies', user: 'users' },
    debounceMs: 50,
    minQueryLength: 2,
    ...overrides,
});

describe('createFacets: contract', () => {
    it('обязательные поля', () => {
        expect(() => createFacets({ baseUrl: '/x', facets: { a: 'a' }, debounceMs: 0, minQueryLength: 0 })).toThrow(/name/);
        expect(() => createFacets({ name: 'svc/x', facets: { a: 'a' }, debounceMs: 0, minQueryLength: 0 })).toThrow(/baseUrl/);
        expect(() => createFacets({ name: 'svc/x', baseUrl: '/x', debounceMs: 0, minQueryLength: 0 })).toThrow(/facets/);
        expect(() => createFacets({ name: 'svc/x', baseUrl: '/x', facets: { a: 'a' }, minQueryLength: 0 })).toThrow(/debounceMs/);
        expect(() => createFacets({ name: 'svc/x', baseUrl: '/x', facets: { a: 'a' }, debounceMs: 0 })).toThrow(/minQueryLength/);
    });

    it('facets — непустой объект', () => {
        expect(() => createFacets(opts({ facets: {} }))).toThrow(/facets/);
    });

    it('debounceMs/minQueryLength — non-negative number', () => {
        expect(() => createFacets(opts({ debounceMs: -1 }))).toThrow(/debounceMs/);
        expect(() => createFacets(opts({ minQueryLength: -1 }))).toThrow(/minQueryLength/);
    });

    it('restMirror auto-derived per facet key', () => {
        const f = createFacets(opts());
        expect(f.restMirror.company).toEqual({ method: 'GET', path: '/api/facets/companies' });
        expect(f.restMirror.user).toEqual({ method: 'GET', path: '/api/facets/users' });
    });

    it('events: LOAD_REQUESTED, LOADED, FAILED', () => {
        const f = createFacets(opts());
        expect(f.events.LOAD_REQUESTED).toBe('svc/tracing/load_requested');
        expect(f.events.LOADED).toBe('svc/tracing/loaded');
        expect(f.events.FAILED).toBe('svc/tracing/failed');
    });
});

describe('createFacets: reducer', () => {
    it('initial slice пустой по facets', () => {
        const f = createFacets(opts());
        expect(f.slice.initial.items.company).toEqual([]);
        expect(f.slice.initial.loading.company).toBe(false);
    });

    it('LOAD_REQUESTED ставит loading[facet]=true', () => {
        const f = createFacets(opts());
        const next = f.reducer(f.slice.initial, { type: f.events.LOAD_REQUESTED, payload: { facet: 'company', q: 'foo' }, id: 'l1', meta: {} });
        expect(next.loading.company).toBe(true);
        expect(next.lastQuery.company).toBe('foo');
    });

    it('LOAD_REQUESTED unknown facet → throw', () => {
        const f = createFacets(opts());
        expect(() => f.reducer(f.slice.initial, { type: f.events.LOAD_REQUESTED, payload: { facet: 'mystery' }, id: 'l1', meta: {} })).toThrow(/unknown facet/);
    });

    it('LOADED заполняет items[facet]', () => {
        const f = createFacets(opts());
        const next = f.reducer(f.slice.initial, { type: f.events.LOADED, payload: { facet: 'company', items: [{ id: 1 }] }, id: 'lo1', meta: {} });
        expect(next.items.company).toEqual([{ id: 1 }]);
        expect(next.loading.company).toBe(false);
    });

    it('FAILED очищает items[facet]', () => {
        const f = createFacets(opts());
        const seeded = f.reducer(f.slice.initial, { type: f.events.LOADED, payload: { facet: 'company', items: [{ id: 1 }] }, id: 'lo1', meta: {} });
        const next = f.reducer(seeded, { type: f.events.FAILED, payload: { facet: 'company' }, id: 'fa1', meta: {} });
        expect(next.items.company).toEqual([]);
        expect(next.loading.company).toBe(false);
    });
});

describe('createFacets: effect (debounced)', () => {
    it('делает запрос после debounceMs', async () => {
        const f = createFacets(opts());
        fetchMock.respondJson('GET', '/api/facets/companies?q=foo&limit=20', { items: [{ id: 1, name: 'Foo' }] });
        const dispatched = [];
        f.effect({ type: f.events.LOAD_REQUESTED, payload: { facet: 'company', q: 'foo' }, id: 'l1', meta: {} }, buildCtx(() => ({}), dispatched));
        expect(dispatched).toHaveLength(0);
        await vi.advanceTimersByTimeAsync(60);
        // вытолкнем microtasks из http
        await Promise.resolve();
        await Promise.resolve();
        const loaded = dispatched.find((d) => d.type === f.events.LOADED);
        expect(loaded).toBeTruthy();
        expect(loaded.payload.facet).toBe('company');
        expect(loaded.payload.items).toEqual([{ id: 1, name: 'Foo' }]);
    });

    it('минимум-длина не достигнута → не дёргает fetch', async () => {
        const f = createFacets(opts({ minQueryLength: 3 }));
        const dispatched = [];
        f.effect({ type: f.events.LOAD_REQUESTED, payload: { facet: 'company', q: 'fo' }, id: 'l1', meta: {} }, buildCtx(() => ({}), dispatched));
        await vi.advanceTimersByTimeAsync(100);
        expect(fetchMock.calls).toHaveLength(0);
    });

    it('повторный запрос на тот же facet перезапускает таймер (debounce)', async () => {
        const f = createFacets(opts());
        fetchMock.respondJson('GET', '/api/facets/companies?q=bar&limit=20', { items: [] });
        const dispatched = [];
        f.effect({ type: f.events.LOAD_REQUESTED, payload: { facet: 'company', q: 'foo' }, id: 'l1', meta: {} }, buildCtx(() => ({}), dispatched));
        await vi.advanceTimersByTimeAsync(20);
        f.effect({ type: f.events.LOAD_REQUESTED, payload: { facet: 'company', q: 'bar' }, id: 'l2', meta: {} }, buildCtx(() => ({}), dispatched));
        await vi.advanceTimersByTimeAsync(60);
        await Promise.resolve();
        await Promise.resolve();
        // только bar отправился
        expect(fetchMock.calls).toHaveLength(1);
        expect(fetchMock.calls[0].url).toContain('q=bar');
    });
});
