/**
 * SelectController — Reactive Controller для Lit, подписывается на срез state
 * через селектор и вызывает host.requestUpdate() при изменении.
 *
 * Используется PlatformElement.select(selector) и компонентами напрямую,
 * если нужны несколько отдельных подписок.
 */

import { getPlatformBus } from './bus-singleton.js';
import type { PlatformBusState } from './bus-state.js';
import { isPlainRecord } from './payload.js';

function unknownItems(value: unknown): unknown[] | null {
    if (!Array.isArray(value)) return null;
    const items: unknown[] = [];
    for (const item of value) items.push(item);
    return items;
}

function _shallowEqual(a: unknown, b: unknown): boolean {
    if (a === b) return true;
    if (a === null || b === null || a === undefined || b === undefined) return false;
    if (typeof a !== 'object' || typeof b !== 'object') return false;
    const leftItems = unknownItems(a);
    const rightItems = unknownItems(b);
    if (leftItems !== null || rightItems !== null) {
        if (leftItems === null || rightItems === null) return false;
        if (leftItems.length !== rightItems.length) return false;
        for (let index = 0; index < leftItems.length; index += 1) {
            if (leftItems[index] !== rightItems[index]) return false;
        }
        return true;
    }
    if (!isPlainRecord(a) || !isPlainRecord(b)) return false;
    const leftKeys = Object.keys(a);
    const rightKeys = Object.keys(b);
    if (leftKeys.length !== rightKeys.length) return false;
    for (const key of leftKeys) {
        if (a[key] !== b[key]) return false;
    }
    return true;
}

interface ReactiveHost {
    addController(c: { hostConnected(): void; hostDisconnected(): void }): void;
    requestUpdate(): void;
}


export class SelectController<V = unknown> {
    host: ReactiveHost;
    selector: (state: Readonly<PlatformBusState>) => V;
    private _read: () => V;
    private _equal: (a: unknown, b: unknown) => boolean;
    private _unsubscribe: (() => void) | null;

    constructor(host: ReactiveHost, selector: (state: Readonly<PlatformBusState>) => V, opts?: { equality?: (a: unknown, b: unknown) => boolean }) {
        if (typeof selector !== 'function') {
            throw new Error('SelectController: selector function required');
        }
        this.host = host;
        this.selector = selector;
        this._equal = opts?.equality === undefined ? _shallowEqual : opts.equality;
        this._read = () => {
            throw new Error('SelectController.value read before hostConnected');
        };
        this._unsubscribe = null;
        host.addController(this);
    }

    /** Значение селектора. До `hostConnected` шина ещё не прочитана — это ошибка вызова, а не пустой слайс. */
    get value(): V {
        return this._read();
    }

    hostConnected(): void {
        const bus = getPlatformBus();
        let current = this.selector(bus.getState());
        this._read = () => current;
        this._unsubscribe = bus.subscribeSelector(
            this.selector,
            (next: V) => {
                current = next;
                this.host.requestUpdate();
            },
            { equality: (left, right) => this._equal(left, right) },
        );
    }

    hostDisconnected(): void {
        if (this._unsubscribe) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
    }
}
