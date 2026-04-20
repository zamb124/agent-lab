/**
 * createSlice — фабрика slice-only сущностей (UI-only state без HTTP/WS).
 * Контракт обязательных полей и pure reducer.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createSlice } from '@platform/lib/events/factories/slice.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildBus } from '../../helpers/bus-fixtures.js';

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

describe('createSlice: contract', () => {
    it('требует options', () => {
        expect(() => createSlice(null)).toThrow(/options/);
        expect(() => createSlice()).toThrow();
    });

    it('требует валидное name', () => {
        expect(() => createSlice({ extraInitial: { a: 1 }, extraReducer: (s) => s })).toThrow(/name/);
        expect(() => createSlice({ name: 'bad', extraInitial: { a: 1 }, extraReducer: (s) => s })).toThrow(/scope\/entity/);
        expect(() => createSlice({ name: 'svc/Bad', extraInitial: { a: 1 }, extraReducer: (s) => s })).toThrow(/scope\/entity/);
    });

    it('запрещает transport / request / restMirror / wsTimeoutMs / effect', () => {
        const base = { name: 'svc/x', extraInitial: { a: 1 }, extraReducer: (s) => s };
        expect(() => createSlice({ ...base, transport: 'ws' })).toThrow(/transport is forbidden/);
        expect(() => createSlice({ ...base, request: async () => ({}) })).toThrow(/request is forbidden/);
        expect(() => createSlice({ ...base, restMirror: { method: 'GET', path: '/x' } })).toThrow(/restMirror is forbidden/);
        expect(() => createSlice({ ...base, wsTimeoutMs: 1000 })).toThrow(/wsTimeoutMs is forbidden/);
        expect(() => createSlice({ ...base, effect: async () => {} })).toThrow(/effect is forbidden/);
    });

    it('требует extraInitial как объект с минимум одним ключом', () => {
        expect(() => createSlice({ name: 'svc/x', extraReducer: (s) => s })).toThrow(/extraInitial/);
        expect(() => createSlice({ name: 'svc/x', extraInitial: [], extraReducer: (s) => s })).toThrow(/plain object/);
        expect(() => createSlice({ name: 'svc/x', extraInitial: {}, extraReducer: (s) => s })).toThrow(/at least one key/);
    });

    it('требует extraReducer-функцию', () => {
        expect(() => createSlice({ name: 'svc/x', extraInitial: { a: 1 } })).toThrow(/extraReducer/);
        expect(() => createSlice({ name: 'svc/x', extraInitial: { a: 1 }, extraReducer: 'not a function' })).toThrow();
    });

    it('extraEvents.<key>: пустой verb — throw', () => {
        expect(() => createSlice({
            name: 'svc/x', extraInitial: { a: 1 }, extraReducer: (s) => s,
            extraEvents: { FOO: '' },
        })).toThrow(/extraEvents/);
    });

    it('actions.<methodName>: пустой verb — throw', () => {
        expect(() => createSlice({
            name: 'svc/x', extraInitial: { a: 1 }, extraReducer: (s) => s,
            actions: { open: '' },
        })).toThrow(/actions/);
    });
});

describe('createSlice: shape', () => {
    it('возвращает factory с kind="slice", events, actions, slice, selectors', () => {
        const factory = createSlice({
            name: 'svc/ui_state',
            extraInitial: { open: false, count: 0 },
            extraReducer: (state) => state,
            extraEvents: { OPENED: 'opened', CLOSED: 'closed' },
            actions: { increment: 'inc' },
        });
        expect(factory.kind).toBe('slice');
        expect(factory.name).toBe('svc/ui_state');
        expect(factory.sliceKey).toBe('svcUiState');
        expect(factory.events.OPENED).toBe('svc/ui_state/opened');
        expect(factory.events.CLOSED).toBe('svc/ui_state/closed');
        expect(factory.events.INC).toBe('svc/ui_state/inc');
        expect(factory.actions.increment).toBe('svc/ui_state/inc');
        expect(factory.slice.initial).toEqual({ open: false, count: 0 });
        expect(typeof factory.slice.reducer).toBe('function');
        expect(typeof factory.selectors.slice).toBe('function');
    });

    it('initialSlice — frozen', () => {
        const factory = createSlice({
            name: 'svc/frz',
            extraInitial: { v: 'x' },
            extraReducer: (s) => s,
        });
        expect(Object.isFrozen(factory.slice.initial)).toBe(true);
    });

    it('selectors.slice бросает если slice не зарегистрирован', () => {
        const factory = createSlice({
            name: 'svc/missing',
            extraInitial: { v: 'x' },
            extraReducer: (s) => s,
        });
        expect(() => factory.selectors.slice({})).toThrow(/not registered in bus/);
    });
});

describe('createSlice: reducer integration через bus', () => {
    it('extraReducer применяется на каждое событие, новый state замораживается', () => {
        const factory = createSlice({
            name: 'svc/cnt',
            extraInitial: { n: 0 },
            extraReducer: (state, event) => {
                if (event.type === 'svc/cnt/inc') {
                    return { ...state, n: state.n + 1 };
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
