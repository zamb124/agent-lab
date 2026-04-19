/**
 * createCursorList: контракт + reducer + effect + statusMap (terminal events).
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createCursorList } from '@platform/lib/events/factories/cursor-list.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';

let fetchMock;
beforeEach(() => { resetFactories(); fetchMock = installFetchMock(); });
afterEach(() => { resetFactories(); fetchMock.uninstall(); });

const opts = (overrides = {}) => ({
    name: 'svc/spans',
    baseUrl: '/api/spans',
    buildQuery: (filters) => ({ q: filters.q || '' }),
    pageSize: 50,
    ...overrides,
});

describe('createCursorList: contract', () => {
    it('обязательные: name, baseUrl, buildQuery, pageSize', () => {
        expect(() => createCursorList({ baseUrl: '/x', buildQuery: () => ({}), pageSize: 10 })).toThrow(/name/);
        expect(() => createCursorList({ name: 'svc/x', buildQuery: () => ({}), pageSize: 10 })).toThrow(/baseUrl/);
        expect(() => createCursorList({ name: 'svc/x', baseUrl: '/x', pageSize: 10 })).toThrow(/buildQuery/);
        expect(() => createCursorList({ name: 'svc/x', baseUrl: '/x', buildQuery: () => ({}) })).toThrow(/pageSize/);
        expect(() => createCursorList({ name: 'svc/x', baseUrl: '/x', buildQuery: 'not fn', pageSize: 10 })).toThrow(/function/);
    });

    it('pageSize должен быть положительным числом', () => {
        expect(() => createCursorList(opts({ pageSize: 0 }))).toThrow(/positive/);
        expect(() => createCursorList(opts({ pageSize: -1 }))).toThrow(/positive/);
        expect(() => createCursorList(opts({ pageSize: 'big' }))).toThrow(/positive/);
    });

    it('restMirror.method обязан быть GET или POST', () => {
        expect(() => createCursorList(opts({ restMirror: { method: 'PUT', path: '/api/spans' } }))).toThrow(/GET or POST/);
        expect(() => createCursorList(opts({ restMirror: { method: 'POST', path: '/api/spans' } }))).not.toThrow();
    });

    it('httpMethod=POST поддерживается (DSL-эндпоинты с body)', () => {
        const c = createCursorList(opts({ httpMethod: 'POST', restMirror: { method: 'POST', path: '/api/spans' } }));
        expect(c.restMirror).toEqual({ method: 'POST', path: '/api/spans' });
    });

    it('default restMirror = { method: GET, path: baseUrl }', () => {
        const c = createCursorList(opts());
        expect(c.restMirror).toEqual({ method: 'GET', path: '/api/spans' });
    });

    it('генерирует базовые события и terminal events из statusMap', () => {
        const c = createCursorList(opts({ statusMap: { 403: 'forbidden', 503: 'unavailable' } }));
        expect(c.events.LOAD_REQUESTED).toBe('svc/spans/load_requested');
        expect(c.events.LOADED).toBe('svc/spans/loaded');
        expect(c.events.PAGE_LOADED).toBe('svc/spans/page_loaded');
        expect(c.events.FAILED).toBe('svc/spans/failed');
        expect(c.events.FORBIDDEN).toBe('svc/spans/forbidden');
        expect(c.events.UNAVAILABLE).toBe('svc/spans/unavailable');
    });

    it('errorToastKey должен быть валидным i18n', () => {
        expect(() => createCursorList(opts({ errorToastKey: 'no_colon' }))).toThrow(/i18n key/);
    });
});

describe('createCursorList: reducer', () => {
    it('LOAD_REQUESTED (append=false) ставит loading=true', () => {
        const c = createCursorList(opts());
        const next = c.reducer(c.slice.initial, { type: c.events.LOAD_REQUESTED, payload: {}, id: 'r1', meta: {} });
        expect(next.loading).toBe(true);
        expect(next.loadingMore).toBe(false);
    });

    it('LOAD_REQUESTED append=true → loadingMore', () => {
        const c = createCursorList(opts());
        const next = c.reducer(c.slice.initial, { type: c.events.LOAD_REQUESTED, payload: { append: true }, id: 'r1', meta: {} });
        expect(next.loading).toBe(false);
        expect(next.loadingMore).toBe(true);
    });

    it('LOADED заменяет items, hasMore, nextCursor', () => {
        const c = createCursorList(opts());
        const next = c.reducer(c.slice.initial, {
            type: c.events.LOADED,
            payload: { items: [1, 2, 3], next_cursor: 'cur', has_more: true },
            id: 'l1', meta: {},
        });
        expect(next.items).toEqual([1, 2, 3]);
        expect(next.nextCursor).toBe('cur');
        expect(next.hasMore).toBe(true);
        expect(Object.isFrozen(next)).toBe(true);
    });

    it('PAGE_LOADED конкатенирует к существующим items', () => {
        const c = createCursorList(opts());
        const seeded = c.reducer(c.slice.initial, {
            type: c.events.LOADED, payload: { items: [1, 2], next_cursor: 'cur', has_more: true }, id: 'l1', meta: {},
        });
        const next = c.reducer(seeded, {
            type: c.events.PAGE_LOADED, payload: { items: [3, 4], next_cursor: null, has_more: false }, id: 'p1', meta: {},
        });
        expect(next.items).toEqual([1, 2, 3, 4]);
        expect(next.hasMore).toBe(false);
    });

    it('FAILED ставит error', () => {
        const c = createCursorList(opts());
        const next = c.reducer(c.slice.initial, { type: c.events.FAILED, payload: { message: 'bad' }, id: 'f1', meta: {} });
        expect(next.error).toBe('bad');
    });

    it('FAILED без message — throw', () => {
        const c = createCursorList(opts());
        expect(() => c.reducer(c.slice.initial, { type: c.events.FAILED, payload: {}, id: 'f1', meta: {} })).toThrow(/message/);
    });

    it('FILTERS_CHANGED мержит фильтры', () => {
        const c = createCursorList(opts({ initialFilters: { q: '', status: 'all' } }));
        const next = c.reducer(c.slice.initial, { type: c.events.FILTERS_CHANGED, payload: { filters: { q: 'hello' } }, id: 'fc1', meta: {} });
        expect(next.filters).toEqual({ q: 'hello', status: 'all' });
    });

    it('FILTERS_RESET возвращает initialFilters', () => {
        const c = createCursorList(opts({ initialFilters: { q: 'init' } }));
        const seeded = c.reducer(c.slice.initial, { type: c.events.FILTERS_CHANGED, payload: { filters: { q: 'changed' } }, id: 'fc1', meta: {} });
        const next = c.reducer(seeded, { type: c.events.FILTERS_RESET, payload: null, id: 'fr1', meta: {} });
        expect(next.filters).toEqual({ q: 'init' });
    });

    it('terminal event сбрасывает items + ставит terminal', () => {
        const c = createCursorList(opts({ statusMap: { 403: 'forbidden' } }));
        const seeded = c.reducer(c.slice.initial, {
            type: c.events.LOADED, payload: { items: [1], next_cursor: null, has_more: false }, id: 'l1', meta: {},
        });
        const next = c.reducer(seeded, { type: c.events.FORBIDDEN, payload: null, id: 't1', meta: {} });
        expect(next.terminal).toBe('forbidden');
        expect(next.items).toEqual([]);
    });
});

describe('createCursorList: effect', () => {
    it('LOAD_REQUESTED → fetch GET → LOADED', async () => {
        const c = createCursorList(opts());
        fetchMock.respondJson('GET', '/api/spans?q=hello&limit=50', { items: [{ id: 1 }], next_cursor: null, has_more: false });
        const dispatched = [];
        await c.effect({
            type: c.events.LOAD_REQUESTED, payload: { filters: { q: 'hello' } }, id: 'l1', meta: {},
        }, buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === c.events.LOADED);
        expect(loaded.payload.items).toEqual([{ id: 1 }]);
        expect(loaded.payload.has_more).toBe(false);
    });

    it('cursor добавляется в query, append → PAGE_LOADED', async () => {
        const c = createCursorList(opts());
        fetchMock.respondJson('GET', '/api/spans?q=&limit=50&cursor=abc', { items: [{ id: 2 }], next_cursor: null, has_more: false });
        const dispatched = [];
        await c.effect({
            type: c.events.LOAD_REQUESTED, payload: { filters: {}, cursor: 'abc', append: true }, id: 'l1', meta: {},
        }, buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === c.events.PAGE_LOADED);
        expect(loaded).toBeTruthy();
    });

    it('HTTP 403 + statusMap → terminal event (без FAILED)', async () => {
        const c = createCursorList(opts({ statusMap: { 403: 'forbidden' } }));
        fetchMock.respondStatus('GET', '/api/spans?q=&limit=50', 403, { detail: 'no access' });
        const dispatched = [];
        await c.effect({ type: c.events.LOAD_REQUESTED, payload: { filters: {} }, id: 'l1', meta: {} }, buildCtx(() => ({}), dispatched));
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(c.events.FORBIDDEN);
        expect(types).not.toContain(c.events.FAILED);
    });

    it('HTTP 500 без statusMap → FAILED + (если errorToastKey) toast', async () => {
        const c = createCursorList(opts({ errorToastKey: 'svc:spans.error' }));
        fetchMock.respondStatus('GET', '/api/spans?q=&limit=50', 500);
        const dispatched = [];
        await c.effect({ type: c.events.LOAD_REQUESTED, payload: { filters: {} }, id: 'l1', meta: {} }, buildCtx(() => ({}), dispatched));
        const failed = dispatched.find((d) => d.type === c.events.FAILED);
        expect(failed).toBeTruthy();
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast.payload).toMatchObject({ type: 'error', i18n_key: 'svc:spans.error' });
    });

    it('некорректный response (без items) → throw (не глотаем)', async () => {
        const c = createCursorList(opts());
        fetchMock.respondJson('GET', '/api/spans?q=&limit=50', { wrong: true });
        await expect(c.effect({ type: c.events.LOAD_REQUESTED, payload: { filters: {} }, id: 'l1', meta: {} }, buildCtx(() => ({}), []))).rejects.toThrow(/items/);
    });
});
