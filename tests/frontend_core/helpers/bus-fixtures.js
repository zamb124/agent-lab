/**
 * Сборка EventBus + EventLog для unit-тестов.
 *
 * Использование:
 *   import { buildBus } from '../helpers/bus-fixtures.js';
 *   const { bus, log, getState } = buildBus({ slices: { mySlice } });
 *   bus.dispatch('my/scope/verb', { ... });
 *   expect(getState().mySlice.foo).toBe('bar');
 */

import { EventBus } from '@platform/lib/events/bus.js';
import { EventLog } from '@platform/lib/events/log.js';
import { combineReducers } from '@platform/lib/events/reducers/index.js';

export function buildBus(options = {}) {
    const slices = options.slices || {};
    const { reducer, initialState } = combineReducers(slices);
    const log = new EventLog({ devMode: true });
    const bus = new EventBus({ reducer, initialState, log });
    return {
        bus,
        log,
        getState: () => bus.getState(),
        events: () => log.snapshot(),
    };
}

/**
 * Минимальный slice-каркас для тестов: просто сохраняет последнее событие.
 */
export function buildEchoSlice(name = 'echo') {
    const initial = Object.freeze({ lastType: null, lastPayload: null });
    return {
        [name]: {
            initial,
            reducer(state = initial, event) {
                if (event.type.startsWith('test/')) {
                    return Object.freeze({ lastType: event.type, lastPayload: event.payload });
                }
                return state;
            },
        },
    };
}

/**
 * Фейковый ctx, ожидаемый effect-функцией платформы.
 */
export function buildCtx(getStateFn = () => ({}), dispatched = []) {
    return {
        dispatch(type, payload, meta) {
            dispatched.push({ type, payload, meta: meta || null });
            return { id: `mock_${dispatched.length}`, type, payload, meta };
        },
        getState: getStateFn,
    };
}
