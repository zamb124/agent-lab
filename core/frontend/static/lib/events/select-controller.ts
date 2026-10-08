/**
 * SelectController — Reactive Controller для Lit, подписывается на срез state
 * через селектор и вызывает host.requestUpdate() при изменении.
 *
 * Используется PlatformElement.select(selector) и компонентами напрямую,
 * если нужны несколько отдельных подписок.
 */

import { getPlatformBus } from './bus-singleton.js';

function _shallowEqual(a: unknown, b: unknown): boolean {
    if (a === b) return true;
    if (a === null || b === null || a === undefined || b === undefined) return false;
    if (typeof a !== 'object' || typeof b !== 'object') return false;
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    const arr = b as unknown[];
    if (Array.isArray(a)) {
        if (a.length !== arr.length) return false;
        for (let i = 0; i < a.length; i += 1) {
            if (a[i] !== arr[i]) return false;
        }
        return true;
    }
    const ra = a as Record<string, unknown>;
    const rb = b as Record<string, unknown>;
    const ak = Object.keys(ra);
    const bk = Object.keys(rb);
    if (ak.length !== bk.length) return false;
    for (const k of ak) {
        if (ra[k] !== rb[k]) return false;
    }
    return true;
}

import type { PlatformBusLike } from './bus-singleton.js';

interface ReactiveHost {
    addController(c: { hostConnected(): void; hostDisconnected(): void }): void;
    requestUpdate(): void;
}

interface SelectorBus extends PlatformBusLike {
    getState: () => Record<string, unknown>;
    subscribeSelector: <V>(sel: (s: Record<string, unknown>) => V, cb: (v: V, prev: V | undefined) => void, opts?: { equality?: (a: V, b: V) => boolean }) => () => void;
}

export class SelectController<V = unknown> {
    host: ReactiveHost;
    selector: (state: Record<string, unknown>) => V;
    equality: (a: V, b: V) => boolean;
    value: V | undefined;
    private _unsubscribe: (() => void) | null;

    constructor(host: ReactiveHost, selector: (state: Record<string, unknown>) => V, opts?: { equality?: (a: V, b: V) => boolean }) {
        if (typeof selector !== 'function') {
            throw new Error('SelectController: selector function required');
        }
        this.host = host;
        this.selector = selector;
        this.equality = (opts && opts.equality) || (_shallowEqual as (a: V, b: V) => boolean);
        this.value = undefined;
        this._unsubscribe = null;
        host.addController(this);
    }

    hostConnected(): void {
        const bus = getPlatformBus() as SelectorBus;
        this.value = this.selector(bus.getState());
        this._unsubscribe = bus.subscribeSelector(
            this.selector,
            (next: V) => {
                this.value = next;
                this.host.requestUpdate();
            },
            { equality: this.equality },
        );
    }

    hostDisconnected(): void {
        if (this._unsubscribe) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
    }
}
