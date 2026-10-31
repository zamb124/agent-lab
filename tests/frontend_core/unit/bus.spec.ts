/**
 * EventBus: dispatch flow, frozen state, reducer purity, effects scheduling,
 * подписчики (state/type/any/selector), middleware.
 */

import { describe, it, expect, vi } from 'vitest';
import { EventBus } from '@platform/lib/events/bus.js';
import { EventLog } from '@platform/lib/events/log.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { prop } from '../helpers/prop.js';

interface CounterState {
    n: number;
}

interface NodeLikeProcess {
    listeners(event: string): ((...args: unknown[]) => void)[];
    removeAllListeners(event: string): void;
    on(event: string, handler: (reason: unknown) => void): void;
}

function buildBus<S extends object>(reducer: (state: S, event: PlatformEvent) => S, initialState: S) {
    const log = new EventLog({ devMode: true });
    return { bus: new EventBus<S>({ reducer, initialState, log }), log };
}

const identity = <S extends object>(s: S): S => s;

describe('EventBus: construction', () => {
    it('требует reducer', () => {
        expect(() => Reflect.construct(EventBus, [{ initialState: {}, log: new EventLog() }])).toThrow(/reducer/);
    });

    it('требует log с append()', () => {
        expect(() => Reflect.construct(EventBus, [{ reducer: identity, initialState: {}, log: {} }])).toThrow(/log/);
    });

    it('initialState заморожен сразу', () => {
        const { bus } = buildBus(identity, { foo: 1 });
        expect(Object.isFrozen(bus.getState())).toBe(true);
    });
});

describe('EventBus: dispatch', () => {
    it('нормализует (type, payload, meta) в Event', () => {
        const reducer = vi.fn(identity<object>);
        const { bus } = buildBus(reducer, {});
        const ev = bus.dispatch('ui/toast/show', { type: 'info' });
        expect(ev).toMatchObject({ type: 'ui/toast/show', payload: { type: 'info' } });
        expect(ev?.id).toBeTruthy();
        expect(reducer).toHaveBeenCalledOnce();
    });

    it('принимает готовый event-объект', () => {
        const { bus, log } = buildBus(identity, {});
        bus.dispatch({ type: 'ui/toast/show', payload: { type: 'info' }, id: 'fixed_id', meta: { ts: 1, source: 'ws', causation_id: null, correlation_id: null, trace_id: null } });
        expect(log.snapshot()[0]?.id).toBe('fixed_id');
    });

    it('бросает на невалидном типе', () => {
        const { bus } = buildBus(identity, {});
        expect(() => bus.dispatch('Foo/Bar')).toThrow();
    });

    it('новый state — frozen, при no-op остаётся прежний', () => {
        const reducer = (state: CounterState, ev: PlatformEvent): CounterState => {
            if (ev.type === 'test/counter/inc') return { ...state, n: state.n + 1 };
            return state;
        };
        const { bus } = buildBus(reducer, { n: 0 });
        const before = bus.getState();
        bus.dispatch('test/counter/inc', null);
        const after = bus.getState();
        expect(after).not.toBe(before);
        expect(Object.isFrozen(after)).toBe(true);
        expect(after.n).toBe(1);
        bus.dispatch('test/other/event', null);
        expect(bus.getState()).toBe(after); // no-op preserves identity
    });

    it('append в лог происходит ПЕРЕД reducer', () => {
        const order: string[] = [];
        const reducer = (s: object, ev: PlatformEvent): object => { order.push(`reduce:${ev.type}`); return s; };
        const log = {
            append(ev: PlatformEvent) { order.push(`log:${ev.type}`); },
        };
        const bus = new EventBus({ reducer, initialState: {}, log });
        bus.dispatch('test/foo/bar', null);
        expect(order).toEqual(['log:test/foo/bar', 'reduce:test/foo/bar']);
    });
});

describe('EventBus: subscribers', () => {
    it('subscribeState вызывается при изменении state', () => {
        const reducer = (s: CounterState, ev: PlatformEvent): CounterState => (ev.type === 'test/n/inc' ? { n: s.n + 1 } : s);
        const { bus } = buildBus(reducer, { n: 0 });
        const sub = vi.fn();
        bus.subscribeState(sub);
        bus.dispatch('test/n/inc', null);
        expect(sub).toHaveBeenCalledOnce();
        bus.dispatch('test/other/x', null); // no-op
        expect(sub).toHaveBeenCalledOnce();
    });

    it('subscribeType вызывается на конкретный тип', () => {
        const { bus } = buildBus(identity, {});
        const a = vi.fn();
        const b = vi.fn();
        const unsub = bus.subscribeType('test/a/x', a);
        bus.subscribeType('test/b/x', b);
        bus.dispatch('test/a/x', null);
        bus.dispatch('test/b/x', null);
        expect(a).toHaveBeenCalledOnce();
        expect(b).toHaveBeenCalledOnce();
        unsub();
        bus.dispatch('test/a/x', null);
        expect(a).toHaveBeenCalledOnce();
    });

    it('subscribeAny вызывается на каждое событие', () => {
        const { bus } = buildBus(identity, {});
        const any = vi.fn();
        bus.subscribeAny(any);
        bus.dispatch('test/a/x', null);
        bus.dispatch('test/b/x', null);
        expect(any).toHaveBeenCalledTimes(2);
    });

    it('subscribeSelector выдаёт начальное значение и реагирует на изменения', () => {
        const reducer = (s: CounterState, ev: PlatformEvent): CounterState => (ev.type === 'test/n/inc' ? { n: s.n + 1 } : s);
        const { bus } = buildBus(reducer, { n: 0 });
        const cb = vi.fn();
        bus.subscribeSelector((s: CounterState) => s.n, cb);
        expect(cb).toHaveBeenCalledWith(0, undefined);
        bus.dispatch('test/n/inc', null);
        expect(cb).toHaveBeenCalledWith(1, 0);
    });
});

describe('EventBus: middleware', () => {
    it('null отменяет dispatch', () => {
        const reducer = vi.fn(identity<object>);
        const { bus, log } = buildBus(reducer, {});
        bus.registerMiddleware(() => null);
        const result = bus.dispatch('test/x/y', null);
        expect(result).toBeNull();
        expect(reducer).not.toHaveBeenCalled();
        expect(log.snapshot()).toHaveLength(0);
    });

    it('возврат event заменяет', () => {
        const reducer = vi.fn(identity<object>);
        const { bus, log } = buildBus(reducer, {});
        bus.registerMiddleware((ev) => ({ ...ev, payload: { tagged: true } }));
        bus.dispatch('test/x/y', { original: true });
        expect(log.snapshot()[0]?.payload).toEqual({ tagged: true });
    });
});

describe('EventBus: effects', () => {
    it('запускаются асинхронно через microtask', async () => {
        const { bus } = buildBus(identity, {});
        const calls: string[] = [];
        bus.registerEffect((ev) => { calls.push(ev.type); });
        bus.dispatch('test/x/y', null);
        expect(calls).toHaveLength(0); // ещё не выполнились
        await Promise.resolve();
        await Promise.resolve();
        expect(calls).toContain('test/x/y');
    });

    it('ошибка эффекта диспатчится как ui/effect/failed', async () => {
        const { bus, log } = buildBus(identity, {});
        // Эффект бросает только на первичном событии; ui/effect/failed
        // он игнорирует — иначе bus уйдёт в бесконечный цикл (это и есть
        // инвариант: effect-handler обязан фильтровать тип события).
        bus.registerEffect((event) => {
            if (event.type === 'test/x/y') throw new Error('boom');
        });
        const proc: NodeLikeProcess | undefined = Reflect.get(globalThis, 'process');
        const previous = proc?.listeners('unhandledRejection') ?? [];
        proc?.removeAllListeners('unhandledRejection');
        const unhandled: string[] = [];
        proc?.on('unhandledRejection', (reason: unknown) => unhandled.push(reason instanceof Error ? reason.message : String(reason)));
        bus.dispatch('test/x/y', null);
        await new Promise((r) => setTimeout(r, 50));
        proc?.removeAllListeners('unhandledRejection');
        for (const listener of previous) {
            proc?.on('unhandledRejection', listener);
        }
        expect(unhandled).toEqual(['boom']);
        const failed = log.snapshot().find((e) => e.type === 'ui/effect/failed');
        expect(failed).toBeTruthy();
        expect(prop(failed?.payload, 'event_type')).toBe('test/x/y');
        expect(String(prop(failed?.payload, 'error'))).toContain('boom');
    });
});
