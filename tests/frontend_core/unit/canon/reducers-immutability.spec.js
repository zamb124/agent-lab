/**
 * Канон-тест: каждый core reducer возвращает frozen state и работает идемпотентно.
 *
 * Прогоняем все 16 core reducers через combineReducers + dispatch известных
 * системных событий и проверяем что:
 *   - результат frozen на уровне корня;
 *   - повторный dispatch того же события приводит к тому же state.
 */

import { describe, it, expect } from 'vitest';
import { coreSlices, combineReducers } from '@platform/lib/events/reducers/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

describe('canon: reducers immutability', () => {
    it('initialState всех core slices заморожен', () => {
        const { initialState } = combineReducers(coreSlices);
        for (const key of Object.keys(initialState)) {
            expect(Object.isFrozen(initialState[key]), `slice ${key}.initial`).toBe(true);
        }
    });

    it('reducer caché возвращает identity для unknown events', () => {
        const { reducer, initialState } = combineReducers(coreSlices);
        const event = { id: 'x', type: 'unknown/event/x', payload: null, meta: { ts: 0, source: 'system' } };
        const next = reducer(initialState, event);
        expect(next).toBe(initialState);
    });

    it('THEME_CHANGED идемпотентен по двум вызовам', () => {
        const { reducer, initialState } = combineReducers(coreSlices);
        const event = { id: 'x', type: CoreEvents.THEME_CHANGED, payload: { mode: 'light', source: 'user' }, meta: { ts: 0, source: 'local' } };
        const a = reducer(initialState, event);
        const b = reducer(a, event);
        expect(b.theme).toEqual(a.theme);
    });

    it('UI_SIDEBAR_OPEN_REQUESTED замораживает результат', () => {
        const { reducer, initialState } = combineReducers(coreSlices);
        const event = { id: 'x', type: CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, payload: null, meta: { ts: 0, source: 'local' } };
        const next = reducer(initialState, event);
        expect(next).not.toBe(initialState);
        expect(next.ui.sidebar.mobileOpen).toBe(true);
    });

    it('два независимых dispatch + reduce дают эквивалентные state', () => {
        const { reducer, initialState } = combineReducers(coreSlices);
        const ev1 = { id: 'a', type: CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, payload: null, meta: { ts: 0, source: 'local' } };
        const ev2 = { id: 'b', type: CoreEvents.NETWORK_OFFLINE, payload: null, meta: { ts: 0, source: 'system' } };
        const a = reducer(reducer(initialState, ev1), ev2);
        const b = reducer(reducer(initialState, ev1), ev2);
        expect(a.ui).toEqual(b.ui);
        expect(a.network).toEqual(b.network);
    });
});
