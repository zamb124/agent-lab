/**
 * createAsyncOp: контракт силён — каждый missing field/value = throw на старте.
 * Также проверяем reducer (REQUESTED/SUCCEEDED/FAILED) и effect (HTTP success +
 * HttpError → FAILED + toast).
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createAsyncOp } from '@platform/lib/events/factories/async-op.js';
import { HttpError } from '@platform/lib/events/http.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildBus, buildCtx } from '../../helpers/bus-fixtures.js';
import { prop } from '../../helpers/prop.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';
import type { AsyncOpSlice } from '@platform/lib/events/factories/async-op.js';
import type { PlatformEvent } from '../../../../core/frontend/static/lib/events/contract.js';

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

describe('createAsyncOp: contract', () => {
    it('options object обязателен', () => {
        expect(() => Reflect.apply(createAsyncOp, null, [null])).toThrow(/options/);
        expect(() => Reflect.apply(createAsyncOp, null, [])).toThrow();
    });

    it('name обязателен и валиден', () => {
        expect(() => Reflect.apply(createAsyncOp, null, [{ silent: true, request: async () => {} }])).toThrow(/name/);
        expect(() => Reflect.apply(createAsyncOp, null, [{ name: 'foo', silent: true, request: async () => {} }])).toThrow(/scope\/entity/);
        expect(() => Reflect.apply(createAsyncOp, null, [{ name: 'foo/Bar', silent: true, request: async () => {} }])).toThrow(/scope\/entity/);
    });

    it('silent или (successToastKey + errorToastKey) — взаимоисключающие', () => {
        const base = { name: 'svc/op_a', request: async () => ({}) };
        expect(() => Reflect.apply(createAsyncOp, null, [{ ...base }])).toThrow(/successToastKey|errorToastKey/);
        expect(() => Reflect.apply(createAsyncOp, null, [{ ...base, successToastKey: 'svc:ok' }])).toThrow(/errorToastKey/);
        expect(() => Reflect.apply(createAsyncOp, null, [{ ...base, successToastKey: 'svc:ok', errorToastKey: 'svc:err', silent: true }])).toThrow(/mutually exclusive/);
        expect(() => Reflect.apply(createAsyncOp, null, [{ ...base, silent: true, successToastKey: 'svc:ok' }])).toThrow(/mutually exclusive/);
    });

    it('i18n key должен содержать ":"', () => {
        expect(() => Reflect.apply(createAsyncOp, null, [{ name: 'svc/op_a', request: async () => ({}), successToastKey: 'no_colon', errorToastKey: 'svc:err' }])).toThrow(/i18n key/);
    });

    it('HTTP-режим без request — throw', () => {
        expect(() => Reflect.apply(createAsyncOp, null, [{ name: 'svc/op_a', silent: true }])).toThrow(/request/);
    });

    it('WS-режим: wsTimeoutMs обязателен', () => {
        expect(() => createAsyncOp({
            name: 'svc/op_a', silent: true, transport: 'ws',
            restMirror: { method: 'POST', path: '/api/op' },
        })).toThrow(/wsTimeoutMs/);
    });

    it('WS-режим: restMirror обязателен', () => {
        expect(() => createAsyncOp({
            name: 'svc/op_a', silent: true, transport: 'ws', wsTimeoutMs: 1000,
        })).toThrow(/restMirror/);
    });

    it('restMirror.method из { GET, POST, PUT, PATCH, DELETE }', () => {
        expect(() => createAsyncOp({
            name: 'svc/op_a', silent: true, transport: 'ws', wsTimeoutMs: 1000,
            restMirror: { method: 'OPTIONS', path: '/api' },
        })).toThrow(/restMirror.method/);
    });

    it('restMirror.path должен начинаться с "/"', () => {
        expect(() => createAsyncOp({
            name: 'svc/op_a', silent: true, transport: 'ws', wsTimeoutMs: 1000,
            restMirror: { method: 'POST', path: 'api/op' },
        })).toThrow(/restMirror.path/);
    });

    it('transport валиден: http|ws', () => {
        expect(() => Reflect.apply(createAsyncOp, null, [{
            name: 'svc/op_a', silent: true, transport: 'grpc', request: async () => {},
        }])).toThrow(/transport/);
    });

    it('повторная регистрация с тем же name — throw', () => {
        createAsyncOp({ name: 'svc/op_a', silent: true, request: async () => ({}) });
        expect(() => Reflect.apply(createAsyncOp, null, [{ name: 'svc/op_a', silent: true, request: async () => ({}) }])).toThrow(/already registered/);
    });
});

describe('createAsyncOp: events / reducer', () => {
    it('генерирует REQUESTED/SUCCEEDED/FAILED', () => {
        const op = createAsyncOp({ name: 'svc/load_thing', silent: true, request: async () => ({}) });
        expect(op.events.REQUESTED).toBe('svc/load_thing/requested');
        expect(op.events.SUCCEEDED).toBe('svc/load_thing/succeeded');
        expect(op.events.FAILED).toBe('svc/load_thing/failed');
    });

    it('reducer: REQUESTED → busy=true, error=null', () => {
        const op = createAsyncOp({ name: 'svc/op_a', silent: true, request: async () => ({}) });
        const initial = op.slice.initial;
        const next = op.reducer(initial, { type: op.events.REQUESTED, payload: null, id: 'r1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(next).toMatchObject({ busy: true, error: null, lastRequestId: 'r1' });
        expect(Object.isFrozen(next)).toBe(true);
    });

    it('reducer: SUCCEEDED → busy=false, lastResult из payload.result', () => {
        const op = createAsyncOp({ name: 'svc/op_a', silent: true, request: async () => ({}) });
        const next = op.reducer(op.slice.initial, { type: op.events.SUCCEEDED, payload: { result: { foo: 'bar' } }, id: 's1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(next).toMatchObject({ busy: false, error: null, lastResult: { foo: 'bar' } });
    });

    it('reducer: SUCCEEDED без payload.result — throw', () => {
        const op = createAsyncOp({ name: 'svc/op_a', silent: true, request: async () => ({}) });
        expect(() => op.reducer(op.slice.initial, { type: op.events.SUCCEEDED, payload: {}, id: 's1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } })).toThrow(/result/);
    });

    it('reducer: FAILED → error из payload.message', () => {
        const op = createAsyncOp({ name: 'svc/op_a', silent: true, request: async () => ({}) });
        const next = op.reducer(op.slice.initial, { type: op.events.FAILED, payload: { message: 'oops' }, id: 'f1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(next.error).toBe('oops');
        expect(next.busy).toBe(false);
    });

    it('reducer: FAILED без payload.message — throw', () => {
        const op = createAsyncOp({ name: 'svc/op_a', silent: true, request: async () => ({}) });
        expect(() => op.reducer(op.slice.initial, { type: op.events.FAILED, payload: {}, id: 'f1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } })).toThrow(/message/);
    });

    it('extraEvents: добавляются в events словарь', () => {
        const op = createAsyncOp({
            name: 'svc/op_a',
            silent: true,
            request: async () => ({}),
            extraEvents: { CANCELLED: 'cancelled' },
        });
        expect(op.events.CANCELLED).toBe('svc/op_a/cancelled');
    });

    it('actions: добавляют именованное действие', () => {
        const op = createAsyncOp({
            name: 'svc/op_a',
            silent: true,
            request: async () => ({}),
            actions: { cancel: 'cancel_requested' },
        });
        expect(op.actions.cancel).toBe('svc/op_a/cancel_requested');
        expect(op.events.CANCEL_REQUESTED).toBe('svc/op_a/cancel_requested');
    });

    it('extraInitial мержится в initial slice', () => {
        const op = createAsyncOp({
            name: 'svc/op_a',
            silent: true,
            request: async () => ({}),
            extraInitial: { lastSecret: null },
        });
        expect(op.slice.initial.lastSecret).toBeNull();
        expect(op.slice.initial.busy).toBe(false);
    });

    it('extraReducer обрабатывает кастомные события', () => {
        const op = createAsyncOp({
            name: 'svc/op_a',
            silent: true,
            request: async () => ({}),
            extraInitial: { custom: 0 },
            extraEvents: { TICK: 'tick' },
            extraReducer: (state: AsyncOpSlice, ev: PlatformEvent, events: Readonly<Record<string, string>>) => {
                if (ev.type === events.TICK) return { ...state, custom: Number(prop(state, 'custom')) + 1 };
                return state;
            },
        });
        const next = op.reducer(op.slice.initial, { type: op.events.TICK ?? 'tick', payload: null, id: 't1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(prop(next, 'custom')).toBe(1);
        expect(Object.isFrozen(next)).toBe(true);
    });
});

describe('createAsyncOp: effect', () => {
    it('успех: dispatch SUCCEEDED + (если не silent) UI_TOAST_SHOW success', async () => {
        const op = createAsyncOp({
            name: 'svc/op_a',
            successToastKey: 'svc:ok',
            errorToastKey: 'svc:err',
            request: async ({ payload }) => ({ id: prop(payload, 'id') }),
        });
        const dispatched: DispatchedRecord[] = [];
        const ctx = buildCtx(() => ({}), dispatched);
        await op.effect({ type: op.events.REQUESTED, payload: { id: 7 }, id: 'r1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } }, ctx);
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(op.events.SUCCEEDED);
        expect(types).toContain(CoreEvents.UI_TOAST_SHOW);
        const succeeded = dispatched.find((d) => d.type === op.events.SUCCEEDED);
        expect(succeeded?.payload).toEqual({ result: { id: 7 }, request: { id: 7 } });
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast?.payload).toMatchObject({ type: 'success', i18n_key: 'svc:ok' });
    });

    it('silent режим — toast не диспатчится', async () => {
        const op = createAsyncOp({
            name: 'svc/op_a',
            silent: true,
            request: async () => ({ ok: true }),
        });
        const dispatched: DispatchedRecord[] = [];
        await op.effect({ type: op.events.REQUESTED, payload: null, id: 'r1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } }, buildCtx(() => ({}), dispatched));
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(op.events.SUCCEEDED);
        expect(types).not.toContain(CoreEvents.UI_TOAST_SHOW);
    });

    it('HttpError → FAILED + error toast', async () => {
        const op = createAsyncOp({
            name: 'svc/op_a',
            successToastKey: 'svc:ok',
            errorToastKey: 'svc:err',
            request: async () => { throw new HttpError('not found', 404, { detail: 'gone' }); },
        });
        const dispatched: DispatchedRecord[] = [];
        await op.effect({ type: op.events.REQUESTED, payload: null, id: 'r1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } }, buildCtx(() => ({}), dispatched));
        const failed = dispatched.find((d) => d.type === op.events.FAILED);
        expect(failed).toBeTruthy();
        expect(failed?.payload).toMatchObject({ message: 'not found', status: 404 });
        const toast = dispatched.find((d) => d.type === CoreEvents.UI_TOAST_SHOW);
        expect(toast?.payload).toMatchObject({ type: 'error', i18n_key: 'svc:err' });
    });

    it('не-transport ошибка пробрасывается выше', async () => {
        const op = createAsyncOp({
            name: 'svc/op_a',
            silent: true,
            request: async () => { throw new Error('logic bug'); },
        });
        const dispatched: DispatchedRecord[] = [];
        await expect(op.effect(
            { type: op.events.REQUESTED, payload: null, id: 'r1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } },
            buildCtx(() => ({}), dispatched),
        )).rejects.toThrow(/logic bug/);
        expect(dispatched).toHaveLength(0);
    });

    it('onSuccess вызывается с (ctx, result, event)', async () => {
        let received = null;
        const op = createAsyncOp({
            name: 'svc/op_a',
            silent: true,
            request: async () => ({ ok: true }),
            onSuccess: (ctx, result, event) => { received = { result, eventType: event.type }; },
        });
        await op.effect({ type: op.events.REQUESTED, payload: null, id: 'r1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } }, buildCtx(() => ({}), []));
        expect(received).toEqual({ result: { ok: true }, eventType: op.events.REQUESTED });
    });
});

describe('createAsyncOp: integration через bus', () => {
    it('REQUESTED через bus меняет slice', () => {
        const op = createAsyncOp({ name: 'svc/op_a', silent: true, request: async () => ({}) });
        const { bus, getState } = buildBus({ slices: { [op.sliceKey]: op.slice } });
        if (op.events.REQUESTED) bus.dispatch(op.events.REQUESTED, null);
        expect(prop(prop(getState(), op.sliceKey), 'busy')).toBe(true);
        if (op.events.SUCCEEDED) bus.dispatch(op.events.SUCCEEDED, { result: { ok: 1 } });
        expect(prop(prop(getState(), op.sliceKey), 'busy')).toBe(false);
        expect(prop(prop(getState(), op.sliceKey), 'lastResult')).toEqual({ ok: 1 });
    });

    it('selectors читают slice из state', () => {
        const op = createAsyncOp({ name: 'svc/op_a', silent: true, request: async () => ({}) });
        const state = { [op.sliceKey]: op.slice.initial };
        expect(op.selectors.busy(state)).toBe(false);
        expect(op.selectors.error(state)).toBeNull();
    });

    it('selectors: missing slice — throw', () => {
        const op = createAsyncOp({ name: 'svc/op_a', silent: true, request: async () => ({}) });
        expect(() => op.selectors.busy({})).toThrow(/not registered/);
    });
});
