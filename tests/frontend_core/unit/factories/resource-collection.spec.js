/**
 * createResourceCollection: контракт + reducer + effect (HTTP).
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createResourceCollection } from '@platform/lib/events/factories/resource-collection.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildBus, buildCtx } from '../../helpers/bus-fixtures.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';

let fetchMock;

beforeEach(() => {
    resetFactories();
    fetchMock = installFetchMock();
});
afterEach(() => {
    resetFactories();
    fetchMock.uninstall();
});

const baseOpts = () => ({
    name: 'svc/items',
    baseUrl: '/api/items',
    idField: 'id',
    operations: ['list', 'create', 'update', 'remove', 'get'],
    toastKeys: {
        create: 'svc:items.created',
        update: 'svc:items.updated',
        remove: 'svc:items.removed',
    },
});

describe('createResourceCollection: contract', () => {
    it('обязательные поля', () => {
        expect(() => createResourceCollection(null)).toThrow(/options/);
        expect(() => createResourceCollection({})).toThrow(/name/);
        expect(() => createResourceCollection({ name: 'svc/items' })).toThrow(/baseUrl/);
        expect(() => createResourceCollection({ name: 'svc/items', baseUrl: '/api' })).toThrow(/idField/);
    });

    it('toastKeys обязательны для всех mutating ops', () => {
        const opts = baseOpts();
        delete opts.toastKeys.create;
        expect(() => createResourceCollection(opts)).toThrow(/toastKeys.create/);
    });

    it('неизвестная operation — throw', () => {
        expect(() => createResourceCollection({
            ...baseOpts(),
            operations: ['list', 'destroy'],
        })).toThrow(/unknown operation/);
    });

    it('генерирует все 15 базовых событий', () => {
        const r = createResourceCollection(baseOpts());
        for (const k of [
            'LIST_REQUESTED', 'LIST_LOADED', 'LIST_FAILED',
            'ITEM_REQUESTED', 'ITEM_LOADED', 'ITEM_FAILED',
            'CREATE_REQUESTED', 'CREATED', 'CREATE_FAILED',
            'UPDATE_REQUESTED', 'UPDATED', 'UPDATE_FAILED',
            'REMOVE_REQUESTED', 'REMOVED', 'REMOVE_FAILED',
        ]) {
            expect(r.events[k]).toMatch(/^svc\/items\//);
        }
    });

    it('restMirror auto-derived из baseUrl + idField', () => {
        const r = createResourceCollection(baseOpts());
        expect(r.restMirror.list).toEqual({ method: 'GET', path: '/api/items' });
        expect(r.restMirror.create).toEqual({ method: 'POST', path: '/api/items' });
        expect(r.restMirror.update).toEqual({ method: 'PATCH', path: '/api/items/:id' });
        expect(r.restMirror.remove).toEqual({ method: 'DELETE', path: '/api/items/:id' });
        expect(r.restMirror.get).toEqual({ method: 'GET', path: '/api/items/:id' });
    });

    it('restMirror можно перекрыть', () => {
        const r = createResourceCollection({
            ...baseOpts(),
            restMirror: { list: { method: 'GET', path: '/custom' } },
        });
        expect(r.restMirror.list.path).toBe('/custom');
        // остальные — auto-derived
        expect(r.restMirror.create.path).toBe('/api/items');
    });

    it('WS-режим: wsTimeoutMs обязателен', () => {
        expect(() => createResourceCollection({
            ...baseOpts(),
            transport: 'ws',
        })).toThrow(/wsTimeoutMs/);
    });
});

describe('createResourceCollection: reducer', () => {
    it('LIST_LOADED заполняет items и byId', () => {
        const r = createResourceCollection(baseOpts());
        const next = r.reducer(r.slice.initial, {
            type: r.events.LIST_LOADED,
            payload: { items: [{ id: 'a', x: 1 }, { id: 'b', x: 2 }] },
            id: 'l1', meta: {},
        });
        expect(next.items).toHaveLength(2);
        expect(next.byId.a).toEqual({ id: 'a', x: 1 });
        expect(Object.isFrozen(next)).toBe(true);
        expect(Object.isFrozen(next.items)).toBe(true);
        expect(Object.isFrozen(next.byId)).toBe(true);
    });

    it('LIST_LOADED без payload.items — throw', () => {
        const r = createResourceCollection(baseOpts());
        expect(() => r.reducer(r.slice.initial, {
            type: r.events.LIST_LOADED, payload: {}, id: 'l1', meta: {},
        })).toThrow(/items/);
    });

    it('CREATED добавляет item', () => {
        const r = createResourceCollection(baseOpts());
        const next = r.reducer(r.slice.initial, {
            type: r.events.CREATED, payload: { item: { id: 'c', name: 'New' } }, id: 'c1', meta: {},
        });
        expect(next.items).toEqual([{ id: 'c', name: 'New' }]);
        expect(next.byId.c).toEqual({ id: 'c', name: 'New' });
    });

    it('UPDATE_REQUESTED помечает busyIds', () => {
        const r = createResourceCollection(baseOpts());
        const next = r.reducer(r.slice.initial, {
            type: r.events.UPDATE_REQUESTED, payload: { id: 'a' }, id: 'u1', meta: {},
        });
        expect(next.busyIds.a).toBe(true);
    });

    it('REMOVED удаляет item', () => {
        const r = createResourceCollection(baseOpts());
        const seeded = r.reducer(r.slice.initial, {
            type: r.events.LIST_LOADED, payload: { items: [{ id: 'a' }, { id: 'b' }] }, id: 'l1', meta: {},
        });
        const next = r.reducer(seeded, {
            type: r.events.REMOVED, payload: { id: 'a' }, id: 'r1', meta: {},
        });
        expect(next.items).toEqual([{ id: 'b' }]);
        expect(next.byId).toEqual({ b: { id: 'b' } });
    });

    it('CREATE_FAILED сохраняет lastError', () => {
        const r = createResourceCollection(baseOpts());
        const next = r.reducer(r.slice.initial, {
            type: r.events.CREATE_FAILED, payload: { message: 'unique' }, id: 'cf1', meta: {},
        });
        expect(next.lastError.create).toBe('unique');
        expect(next.createInFlight).toBe(false);
        expect(next.createLockEventId).toBeNull();
    });

    it('CREATE_REQUESTED ставит createInFlight и createLockEventId', () => {
        const r = createResourceCollection(baseOpts());
        const next = r.reducer(r.slice.initial, {
            type: r.events.CREATE_REQUESTED, payload: { name: 'x' }, id: 'e1', meta: {},
        });
        expect(next.createInFlight).toBe(true);
        expect(next.createLockEventId).toBe('e1');
    });

    it('второй CREATE_REQUESTED при уже идущем create не сменяет lock', () => {
        const r = createResourceCollection(baseOpts());
        const afterFirst = r.reducer(r.slice.initial, {
            type: r.events.CREATE_REQUESTED, payload: { name: 'a' }, id: 'e1', meta: {},
        });
        const afterSecond = r.reducer(afterFirst, {
            type: r.events.CREATE_REQUESTED, payload: { name: 'b' }, id: 'e2', meta: {},
        });
        expect(afterSecond.createInFlight).toBe(true);
        expect(afterSecond.createLockEventId).toBe('e1');
    });

    it('CREATED сбрасывает createInFlight', () => {
        const r = createResourceCollection(baseOpts());
        const withLock = r.reducer(r.slice.initial, {
            type: r.events.CREATE_REQUESTED, payload: {}, id: 'e1', meta: {},
        });
        const afterCreated = r.reducer(withLock, {
            type: r.events.CREATED, payload: { item: { id: 'n', name: 'N' } }, id: 'c1', meta: {},
        });
        expect(afterCreated.createInFlight).toBe(false);
        expect(afterCreated.createLockEventId).toBeNull();
    });

    it('после CREATE_FAILED снова разрешён новый lock от другого event.id', () => {
        const r = createResourceCollection(baseOpts());
        const locked = r.reducer(r.slice.initial, {
            type: r.events.CREATE_REQUESTED, payload: { name: 'a' }, id: 'e1', meta: {},
        });
        const afterFail = r.reducer(locked, {
            type: r.events.CREATE_FAILED, payload: { message: 'nope' }, id: 'f1', meta: {},
        });
        expect(afterFail.createInFlight).toBe(false);
        expect(afterFail.createLockEventId).toBeNull();
        const again = r.reducer(afterFail, {
            type: r.events.CREATE_REQUESTED, payload: { name: 'b' }, id: 'e2', meta: {},
        });
        expect(again.createInFlight).toBe(true);
        expect(again.createLockEventId).toBe('e2');
    });

    it('без operation create: CREATE_REQUESTED не выставляет createInFlight', () => {
        const r = createResourceCollection({
            name: 'svc/readonly',
            baseUrl: '/api/ro',
            idField: 'id',
            operations: ['list', 'get'],
            toastKeys: {},
        });
        const next = r.reducer(r.slice.initial, {
            type: r.events.CREATE_REQUESTED, payload: { name: 'x' }, id: 'e0', meta: {},
        });
        expect(next.createInFlight).toBe(false);
        expect(next.createLockEventId).toBeNull();
    });

    it('LIST_LOADED не сбрасывает createInFlight при идущем create', () => {
        const r = createResourceCollection(baseOpts());
        const locked = r.reducer(r.slice.initial, {
            type: r.events.CREATE_REQUESTED, payload: {}, id: 'e1', meta: {},
        });
        const withList = r.reducer(locked, {
            type: r.events.LIST_LOADED, payload: { items: [{ id: 'a' }] }, id: 'l1', meta: {},
        });
        expect(withList.createInFlight).toBe(true);
        expect(withList.createLockEventId).toBe('e1');
        expect(withList.items).toEqual([{ id: 'a' }]);
    });

    it('selectors.createInFlight согласован с reducer', () => {
        const r = createResourceCollection(baseOpts());
        const sk = r.sliceKey;
        const s0 = { [sk]: r.slice.initial };
        expect(r.selectors.createInFlight(s0)).toBe(false);
        const s1 = { [sk]: r.reducer(r.slice.initial, {
            type: r.events.CREATE_REQUESTED, payload: {}, id: 'e1', meta: {},
        }) };
        expect(r.selectors.createInFlight(s1)).toBe(true);
    });

    it('UPDATE_FAILED сбрасывает busyIds для id', () => {
        const r = createResourceCollection(baseOpts());
        const seeded = r.reducer(r.slice.initial, {
            type: r.events.UPDATE_REQUESTED, payload: { id: 'a' }, id: 'u1', meta: {},
        });
        expect(seeded.busyIds.a).toBe(true);
        const next = r.reducer(seeded, {
            type: r.events.UPDATE_FAILED, payload: { id: 'a', message: 'oops' }, id: 'uf1', meta: {},
        });
        expect(next.busyIds.a).toBeUndefined();
        expect(next.lastError.update).toBe('oops');
    });
});

describe('createResourceCollection: effect (HTTP)', () => {
    it('LIST_REQUESTED → fetch GET → LIST_LOADED', async () => {
        const r = createResourceCollection(baseOpts());
        fetchMock.respondJson('GET', '/api/items?limit=200', { items: [{ id: 'a' }] });
        const dispatched = [];
        await r.effect({ type: r.events.LIST_REQUESTED, payload: null, id: 'l1', meta: {} }, buildCtx(() => ({}), dispatched));
        const loaded = dispatched.find((d) => d.type === r.events.LIST_LOADED);
        expect(loaded).toBeTruthy();
        expect(loaded.payload.items).toEqual([{ id: 'a' }]);
    });

    it('CREATE_REQUESTED → fetch POST → CREATED + UI_TOAST_SHOW', async () => {
        const r = createResourceCollection(baseOpts());
        fetchMock.respondJson('POST', '/api/items', { id: 'new', name: 'Hi' });
        const dispatched = [];
        await r.effect({ type: r.events.CREATE_REQUESTED, payload: { name: 'Hi' }, id: 'c1', meta: {} }, buildCtx(() => ({}), dispatched));
        const created = dispatched.find((d) => d.type === r.events.CREATED);
        expect(created.payload.item).toEqual({ id: 'new', name: 'Hi' });
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast.payload).toMatchObject({ type: 'success', i18n_key: 'svc:items.created' });
    });

    it('второй CREATE_REQUESTED с другим event.id не делает повторный POST', async () => {
        const r = createResourceCollection(baseOpts());
        fetchMock.respondJson('POST', '/api/items', { id: 'new', name: 'Hi' });
        const sk = r.sliceKey;
        const s1 = r.reducer(r.slice.initial, {
            type: r.events.CREATE_REQUESTED, payload: { name: 'Hi' }, id: 'c1', meta: {},
        });
        const getState = () => ({ [sk]: s1 });
        const dispatched = [];
        const ctx = buildCtx(getState, dispatched);
        await r.effect({ type: r.events.CREATE_REQUESTED, payload: { name: 'Hi' }, id: 'c1', meta: {} }, ctx);
        await r.effect({ type: r.events.CREATE_REQUESTED, payload: { name: 'Hi' }, id: 'c2', meta: {} }, ctx);
        const postCalls = fetchMock.calls.filter((c) => c.method === 'POST' && c.url === '/api/items');
        expect(postCalls).toHaveLength(1);
    });

    it('три CREATE_REQUESTED c разными id при одном lock — один POST', async () => {
        const r = createResourceCollection(baseOpts());
        fetchMock.respondJson('POST', '/api/items', { id: 'one', name: 'x' });
        const sk = r.sliceKey;
        const sLocked = r.reducer(r.slice.initial, {
            type: r.events.CREATE_REQUESTED, payload: { name: 'a' }, id: 'a1', meta: {},
        });
        const getState = () => ({ [sk]: sLocked });
        const ctx = buildCtx(getState, []);
        await r.effect({ type: r.events.CREATE_REQUESTED, payload: { name: 'a' }, id: 'a1', meta: {} }, ctx);
        await r.effect({ type: r.events.CREATE_REQUESTED, payload: { name: 'b' }, id: 'a2', meta: {} }, ctx);
        await r.effect({ type: r.events.CREATE_REQUESTED, payload: { name: 'c' }, id: 'a3', meta: {} }, ctx);
        const postCalls = fetchMock.calls.filter((c) => c.method === 'POST' && c.url === '/api/items');
        expect(postCalls).toHaveLength(1);
    });

    it('дубликат effect не диспатчит CREATED (только владелец lock завершает create)', async () => {
        const r = createResourceCollection(baseOpts());
        fetchMock.respondJson('POST', '/api/items', { id: 'n', name: 'one' });
        const sk = r.sliceKey;
        const sLocked = r.reducer(r.slice.initial, {
            type: r.events.CREATE_REQUESTED, payload: { name: 'a' }, id: 'c1', meta: {},
        });
        const dispatched = [];
        const ctx = buildCtx(() => ({ [sk]: sLocked }), dispatched);
        await r.effect({ type: r.events.CREATE_REQUESTED, payload: { name: 'a' }, id: 'c1', meta: {} }, ctx);
        await r.effect({ type: r.events.CREATE_REQUESTED, payload: { name: 'a' }, id: 'c2', meta: {} }, ctx);
        const createdCount = dispatched.filter((d) => d.type === r.events.CREATED).length;
        expect(createdCount).toBe(1);
    });

    it('CREATE 4xx → CREATE_FAILED + error toast (если задан create_error)', async () => {
        const r = createResourceCollection({
            ...baseOpts(),
            toastKeys: {
                ...baseOpts().toastKeys,
                create_error: 'svc:items.create_error',
            },
        });
        fetchMock.respondStatus('POST', '/api/items', 400, { detail: 'invalid' });
        const dispatched = [];
        await r.effect({ type: r.events.CREATE_REQUESTED, payload: { name: 'x' }, id: 'c1', meta: {} }, buildCtx(() => ({}), dispatched));
        const failed = dispatched.find((d) => d.type === r.events.CREATE_FAILED);
        expect(failed.payload.message).toBe('invalid');
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast.payload).toMatchObject({ type: 'error', i18n_key: 'svc:items.create_error' });
    });

    it('UPDATE_REQUESTED → fetch PATCH → UPDATED + reload list', async () => {
        const r = createResourceCollection(baseOpts());
        fetchMock.respondJson('PATCH', '/api/items/a', { id: 'a', name: 'Updated' });
        fetchMock.respondJson('GET', '/api/items?limit=200', { items: [{ id: 'a', name: 'Updated' }] });
        const dispatched = [];
        await r.effect({
            type: r.events.UPDATE_REQUESTED, payload: { id: 'a', name: 'Updated' }, id: 'u1', meta: {},
        }, buildCtx(() => ({}), dispatched));
        const updated = dispatched.find((d) => d.type === r.events.UPDATED);
        expect(updated.payload.item.id).toBe('a');
        // reloadAfterMutation default true → диспатчится LIST_REQUESTED
        const reload = dispatched.find((d) => d.type === r.events.LIST_REQUESTED);
        expect(reload).toBeTruthy();
    });

    it('REMOVE 204 → REMOVED + remove toast', async () => {
        const r = createResourceCollection(baseOpts());
        fetchMock.respondStatus('DELETE', '/api/items/a', 204);
        fetchMock.respondJson('GET', '/api/items?limit=200', { items: [] });
        const dispatched = [];
        await r.effect({ type: r.events.REMOVE_REQUESTED, payload: { id: 'a' }, id: 'r1', meta: {} }, buildCtx(() => ({}), dispatched));
        const removed = dispatched.find((d) => d.type === r.events.REMOVED);
        expect(removed.payload.id).toBe('a');
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast.payload.i18n_key).toBe('svc:items.removed');
    });
});

describe('createResourceCollection: integration через bus', () => {
    it('LIST_LOADED через bus заполняет state', () => {
        const r = createResourceCollection(baseOpts());
        const { bus, getState } = buildBus({ slices: { [r.sliceKey]: r.slice } });
        bus.dispatch(r.events.LIST_LOADED, { items: [{ id: 'a' }, { id: 'b' }] });
        expect(getState()[r.sliceKey].items).toHaveLength(2);
    });
});
