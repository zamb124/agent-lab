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
import type { PlatformEvent, EventMetaInput } from '@platform/lib/events/contract.js';
import { EventLog } from '@platform/lib/events/log.js';
import { buildPlatformReducer, combineReducers } from '@platform/lib/events/reducers/index.js';
import type { SliceDef } from '@platform/lib/events/reducers/index.js';

type SliceStates<S extends Record<string, SliceDef>> = { [K in keyof S]: ReturnType<S[K]['reducer']> };

export interface BuildBusOptions<S extends Record<string, SliceDef> = Record<string, SliceDef>> {
    slices?: S;
}

export function buildBus<S extends Record<string, SliceDef> = Record<string, SliceDef>>(options: BuildBusOptions<S> = {}) {
    const slices = (options.slices ?? {}) as S;
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

interface EchoSliceState {
    lastType: string | null;
    lastPayload: unknown;
}

/**
 * Минимальный slice-каркас для тестов: просто сохраняет последнее событие.
 */
export function buildEchoSlice(name = 'echo'): Record<string, SliceDef<EchoSliceState>> {
    const initial: EchoSliceState = Object.freeze({ lastType: null, lastPayload: null });
    return {
        [name]: {
            initial,
            reducer(state: EchoSliceState = initial, event: PlatformEvent) {
                if (event.type.startsWith('test/')) {
                    return Object.freeze({ lastType: event.type, lastPayload: event.payload });
                }
                return state;
            },
        },
    };
}

/**
 * Полноценный platform bus (PlatformBusState) для тестов контрактов,
 * требующих PlatformBusLike (setPlatformBus, ControllerHost).
 */
export function buildPlatformBus(slices: Record<string, SliceDef> = {}) {
    const { reducer, initialState } = buildPlatformReducer(slices);
    return new EventBus({ reducer, initialState, log: new EventLog({ devMode: true }) });
}

export function testEvent(type: string | undefined, payload: unknown = null): PlatformEvent {
    if (type === undefined) {
        throw new Error('testEvent: event type required');
    }
    return {
        id: `id_${type}`,
        type,
        payload,
        meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null },
    };
}

export interface DispatchedRecord {
    type: string;
    payload: unknown;
    meta: EventMetaInput | null;
}

/**
 * Фейковый ctx, ожидаемый effect-функцией платформы.
 */
interface BuildCtxResult<S> {
    dispatch(type: string | PlatformEvent, payload?: unknown, meta?: EventMetaInput): PlatformEvent | { id: string; type: string; payload: unknown; meta: EventMetaInput | undefined };
    getState(): S;
}

export function buildCtx(): BuildCtxResult<Record<string, never>>;
export function buildCtx<S>(getStateFn: () => S, dispatched?: DispatchedRecord[]): BuildCtxResult<S>;
export function buildCtx<S>(
    getStateFn: (() => S) | undefined = undefined,
    dispatched: DispatchedRecord[] = [],
): BuildCtxResult<S | Record<string, never>> {
    const fn: () => S | Record<string, never> = getStateFn ?? (() => ({}));
    return {
        dispatch(type: string | PlatformEvent, payload?: unknown, meta?: EventMetaInput) {
            const eventType = typeof type === 'string' ? type : type.type;
            dispatched.push({ type: eventType, payload, meta: meta || null });
            return { id: `mock_${dispatched.length}`, type: eventType, payload, meta };
        },
        getState: fn,
    };
}
