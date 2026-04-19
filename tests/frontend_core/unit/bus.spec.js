/**
 * EventBus: dispatch flow, frozen state, reducer purity, effects scheduling,
 * subscribers (state/type/any/selector), middleware.
 */

import { describe, it, expect, vi } from 'vitest';
import { EventBus } from '@platform/lib/events/bus.js';
import { EventLog } from '@platform/lib/events/log.js';

function buildBus(reducer, initialState = {}) {
    const log = new EventLog({ devMode: true });
    return { bus: new EventBus({ reducer, initialState, log }), log };
}

describe('EventBus: construction', () => {
    it('требует reducer', () => {
        expect(() => new EventBus({ initialState: {}, log: new EventLog() })).toThrow(/reducer/);
    });

    it('требует log с append()', () => {
        expect(() => new EventBus({ reducer: (s) => s, initialState: {}, log: {} })).toThrow(/log/);
    });

    it('initialState заморожен сразу', () => {
        const { bus } = buildBus((s) => s, { foo: 1 });
        expect(Object.isFrozen(bus.getState())).toBe(true);
    });
});

describe('EventBus: dispatch', () => {
    it('нормализует (type, payload, meta) в Event', () => {
        const reducer = vi.fn((s) => s);
        const { bus } = buildBus(reducer);
        const ev = bus.dispatch('ui/toast/show', { type: 'info' });
        expect(ev).toMatchObject({ type: 'ui/toast/show', payload: { type: 'info' } });
        expect(ev.id).toBeTruthy();
        expect(reducer).toHaveBeenCalledOnce();
    });

    it('принимает готовый event-объект', () => {
        const { bus, log } = buildBus((s) => s);
        bus.dispatch({ type: 'ui/toast/show', payload: { type: 'info' }, id: 'fixed_id', meta: { ts: 1, source: 'ws', causation_id: null, correlation_id: null, trace_id: null } });
        expect(log.snapshot()[0].id).toBe('fixed_id');
    });

    it('бросает на невалидном типе', () => {
        const { bus } = buildBus((s) => s);
        expect(() => bus.dispatch('Foo/Bar')).toThrow();
    });

    it('новый state — frozen, при no-op остаётся прежний', () => {
        let counter = 0;
        const reducer = (state, ev) => {
            if (ev.type === 'test/counter/inc') return { ...state, n: (state.n || 0) + 1 };
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
        const order = [];
        const reducer = (s, ev) => { order.push(`reduce:${ev.type}`); return s; };
        const log = {
            append(ev) { order.push(`log:${ev.type}`); },
        };
        const bus = new EventBus({ reducer, initialState: {}, log });
        bus.dispatch('test/foo/bar', null);
        expect(order).toEqual(['log:test/foo/bar', 'reduce:test/foo/bar']);
    });
});

describe('EventBus: subscribers', () => {
    it('subscribeState вызывается при изменении state', () => {
        const reducer = (s, ev) => (ev.type === 'test/n/inc' ? { n: (s.n || 0) + 1 } : s);
        const { bus } = buildBus(reducer, { n: 0 });
        const sub = vi.fn();
        bus.subscribeState(sub);
        bus.dispatch('test/n/inc', null);
        expect(sub).toHaveBeenCalledOnce();
        bus.dispatch('test/other/x', null); // no-op
        expect(sub).toHaveBeenCalledOnce();
    });

    it('subscribeType вызывается на конкретный тип', () => {
        const { bus } = buildBus((s) => s);
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
        const { bus } = buildBus((s) => s);
        const any = vi.fn();
        bus.subscribeAny(any);
        bus.dispatch('test/a/x', null);
        bus.dispatch('test/b/x', null);
        expect(any).toHaveBeenCalledTimes(2);
    });

    it('subscribeSelector выдаёт начальное значение и реагирует на изменения', () => {
        const reducer = (s, ev) => (ev.type === 'test/n/inc' ? { n: (s.n || 0) + 1 } : s);
        const { bus } = buildBus(reducer, { n: 0 });
        const cb = vi.fn();
        bus.subscribeSelector((s) => s.n, cb);
        expect(cb).toHaveBeenCalledWith(0, undefined);
        bus.dispatch('test/n/inc', null);
        expect(cb).toHaveBeenCalledWith(1, 0);
    });
});

describe('EventBus: middleware', () => {
    it('null отменяет dispatch', () => {
        const reducer = vi.fn((s) => s);
        const { bus, log } = buildBus(reducer);
        bus.registerMiddleware(() => null);
        const result = bus.dispatch('test/x/y', null);
        expect(result).toBeNull();
        expect(reducer).not.toHaveBeenCalled();
        expect(log.snapshot()).toHaveLength(0);
    });

    it('возврат event заменяет', () => {
        const reducer = vi.fn((s) => s);
        const { bus, log } = buildBus(reducer);
        bus.registerMiddleware((ev) => ({ ...ev, payload: { tagged: true } }));
        bus.dispatch('test/x/y', { original: true });
        expect(log.snapshot()[0].payload).toEqual({ tagged: true });
    });
});

describe('EventBus: effects', () => {
    it('запускаются асинхронно через microtask', async () => {
        const reducer = (s) => s;
        const { bus } = buildBus(reducer);
        const calls = [];
        bus.registerEffect((ev) => { calls.push(ev.type); });
        bus.dispatch('test/x/y', null);
        expect(calls).toHaveLength(0); // ещё не выполнились
        await Promise.resolve();
        await Promise.resolve();
        expect(calls).toContain('test/x/y');
    });

    it('ошибка эффекта диспатчится как ui/effect/failed', async () => {
        const reducer = (s) => s;
        const { bus, log } = buildBus(reducer);
        // Эффект бросает только на первичном событии; ui/effect/failed
        // он игнорирует — иначе bus уйдёт в бесконечный цикл (это и есть
        // инвариант: effect-handler обязан фильтровать тип события).
        bus.registerEffect((event) => {
            if (event.type === 'test/x/y') throw new Error('boom');
        });
        const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        bus.dispatch('test/x/y', null);
        await new Promise((r) => setTimeout(r, 50));
        const failed = log.snapshot().find((e) => e.type === 'ui/effect/failed');
        expect(failed).toBeTruthy();
        expect(failed.payload.event_type).toBe('test/x/y');
        expect(failed.payload.error).toContain('boom');
        errSpy.mockRestore();
    });
});
