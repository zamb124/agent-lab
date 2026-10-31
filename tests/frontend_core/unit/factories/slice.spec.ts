/**
 * createSlice — фабрика slice-only сущностей (UI-only state без HTTP/WS).
 * Контракт обязательных полей и pure reducer.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createSlice } from '@platform/lib/events/factories/slice.js';
import { buildEventType } from '@platform/lib/events/factories/_internal.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildBus } from '../../helpers/bus-fixtures.js';

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

describe('createSlice: contract', () => {
    it('требует options', () => {
        expect(() => Reflect.apply(createSlice, null, [null])).toThrow(/options/);
        expect(() => Reflect.apply(createSlice, null, [])).toThrow();
    });

    it('требует валидное name', () => {
        expect(() => Reflect.apply(createSlice, null, [{ extraInitial: { a: 1 }, extraReducer: (state: Record<string, unknown>) => state }])).toThrow(/name/);
        expect(() => Reflect.apply(createSlice, null, [{ name: 'bad', extraInitial: { a: 1 }, extraReducer: (state: Record<string, unknown>) => state }])).toThrow(/scope\/entity/);
        expect(() => Reflect.apply(createSlice, null, [{ name: 'svc/Bad', extraInitial: { a: 1 }, extraReducer: (state: Record<string, unknown>) => state }])).toThrow(/scope\/entity/);
    });

    it('запрещает transport / request / restMirror / wsTimeoutMs / effect', () => {
        const base = { name: 'svc/x', extraInitial: { a: 1 }, extraReducer: (state: Record<string, unknown>) => state };
        expect(() => Reflect.apply(createSlice, null, [{ ...base, transport: 'ws' }])).toThrow(/transport is forbidden/);
        expect(() => Reflect.apply(createSlice, null, [{ ...base, request: async () => ({}) }])).toThrow(/request is forbidden/);
        expect(() => Reflect.apply(createSlice, null, [{ ...base, restMirror: { method: 'GET', path: '/x' } }])).toThrow(/restMirror is forbidden/);
        expect(() => Reflect.apply(createSlice, null, [{ ...base, wsTimeoutMs: 1000 }])).toThrow(/wsTimeoutMs is forbidden/);
        expect(() => Reflect.apply(createSlice, null, [{ ...base, effect: async () => {} }])).toThrow(/effect is forbidden/);
    });

    it('требует extraInitial как объект с минимум одним ключом', () => {
        expect(() => Reflect.apply(createSlice, null, [{ name: 'svc/x', extraReducer: (state: Record<string, unknown>) => state }])).toThrow(/extraInitial/);
        expect(() => Reflect.apply(createSlice, null, [{ name: 'svc/x', extraInitial: [], extraReducer: (state: Record<string, unknown>) => state }])).toThrow(/plain object/);
        expect(() => Reflect.apply(createSlice, null, [{ name: 'svc/x', extraInitial: {}, extraReducer: (state: Record<string, unknown>) => state }])).toThrow(/at least one key/);
    });

    it('требует extraReducer-функцию', () => {
        expect(() => Reflect.apply(createSlice, null, [{ name: 'svc/x', extraInitial: { a: 1 } }])).toThrow(/extraReducer/);
        expect(() => Reflect.apply(createSlice, null, [{ name: 'svc/x', extraInitial: { a: 1 }, extraReducer: 'not a function' }])).toThrow();
    });

    it('extraEvents.<key>: пустой verb — throw', () => {
        expect(() => createSlice({
            name: 'svc/x', extraInitial: { a: 1 }, extraReducer: (state: Record<string, unknown>) => state,
            extraEvents: { FOO: '' },
        })).toThrow(/extraEvents/);
    });

    it('actions.<methodName>: пустой verb — throw', () => {
        expect(() => createSlice({
            name: 'svc/x', extraInitial: { a: 1 }, extraReducer: (state: Record<string, unknown>) => state,
            actions: { open: '' },
        })).toThrow(/actions/);
    });

    it('actions: пустой methodName — throw', () => {
        expect(() => createSlice({
            name: 'svc/x', extraInitial: { a: 1 }, extraReducer: (state: Record<string, unknown>) => state,
            actions: { '': 'open' },
        })).toThrow(/method name/);
    });

    it('buildEventType: пустой verb — throw', () => {
        expect(() => buildEventType('svc/x', '')).toThrow(/verb/);
    });
});

describe('createSlice: shape', () => {
    it('возвращает factory с kind="slice", events, actions, slice, selectors', () => {
        const factory = createSlice({
            name: 'svc/panel_state',
            extraInitial: { open: false, count: 0 },
            extraReducer: (state) => state,
            extraEvents: { OPENED: 'opened', CLOSED: 'closed' },
            actions: { increment: 'inc' },
        });
        expect(factory.kind).toBe('slice');
        expect(factory.name).toBe('svc/panel_state');
        expect(factory.sliceKey).toBe('svcPanelState');
        expect(factory.events.OPENED).toBe('svc/panel_state/opened');
        expect(factory.events.CLOSED).toBe('svc/panel_state/closed');
        expect(factory.events.INC).toBe('svc/panel_state/inc');
        expect(factory.actions.increment).toBe('svc/panel_state/inc');
        expect(factory.slice.initial).toEqual({ open: false, count: 0 });
        expect(typeof factory.slice.reducer).toBe('function');
        expect(typeof factory.selectors.slice).toBe('function');
    });

    it('initialSlice — frozen', () => {
        const factory = createSlice({
            name: 'svc/frz',
            extraInitial: { v: 'x' },
            extraReducer: (state: Record<string, unknown>) => state,
        });
        expect(Object.isFrozen(factory.slice.initial)).toBe(true);
    });

    it('selectors.slice бросает если slice не зарегистрирован', () => {
        const factory = createSlice({
            name: 'svc/missing',
            extraInitial: { v: 'x' },
            extraReducer: (state: Record<string, unknown>) => state,
        });
        expect(() => factory.selectors.slice({})).toThrow(/not registered in bus/);
    });
});

describe('createSlice: reducer integration через bus', () => {
    it('extraReducer применяется на каждое событие, новый state замораживается', () => {
        const factory = createSlice({
            name: 'svc/cnt',
            extraInitial: { n: 0 },
            extraReducer: (state: Record<string, unknown>, event: { type: string }) => {
                if (event.type === 'svc/cnt/inc') {
                    return { ...state, n: Number(state['n'] ?? 0) + 1 };
                }
                return state;
            },
            extraEvents: { INC: 'inc' },
        });
        const { bus, getState } = buildBus({ slices: { [factory.sliceKey]: factory.slice } });
        bus.dispatch('svc/cnt/inc', null, { source: 'local' });
        bus.dispatch('svc/cnt/inc', null, { source: 'local' });
        bus.dispatch('svc/cnt/other', null, { source: 'local' });
        const slice = factory.selectors.slice(getState());
        expect(slice.n).toBe(2);
        expect(Object.isFrozen(slice)).toBe(true);
    });

    it('reducer оставляет тот же state-объект если extraReducer вернул state без изменений', () => {
        const factory = createSlice({
            name: 'svc/noop',
            extraInitial: { v: 1 },
            extraReducer: (state) => state,
        });
        const { bus, getState } = buildBus({ slices: { [factory.sliceKey]: factory.slice } });
        const before = factory.selectors.slice(getState());
        bus.dispatch('svc/noop/whatever', { x: 1 }, { source: 'local' });
        const after = factory.selectors.slice(getState());
        expect(after).toBe(before);
    });
});
