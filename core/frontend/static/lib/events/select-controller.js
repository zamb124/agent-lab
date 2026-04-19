/**
 * SelectController — Reactive Controller для Lit, подписывается на срез state
 * через селектор и вызывает host.requestUpdate() при изменении.
 *
 * Используется PlatformElement.select(selector) и компонентами напрямую,
 * если нужны несколько отдельных подписок.
 */

import { getPlatformBus } from './bus-singleton.js';

function _shallowEqual(a, b) {
    if (a === b) return true;
    if (a === null || b === null || a === undefined || b === undefined) return false;
    if (typeof a !== 'object' || typeof b !== 'object') return false;
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    if (Array.isArray(a)) {
        if (a.length !== b.length) return false;
        for (let i = 0; i < a.length; i += 1) {
            if (a[i] !== b[i]) return false;
        }
        return true;
    }
    const ak = Object.keys(a);
    const bk = Object.keys(b);
    if (ak.length !== bk.length) return false;
    for (const k of ak) {
        if (a[k] !== b[k]) return false;
    }
    return true;
}

export class SelectController {
    constructor(host, selector, opts) {
        if (typeof selector !== 'function') {
            throw new Error('SelectController: selector function required');
        }
        this.host = host;
        this.selector = selector;
        this.equality = (opts && opts.equality) || _shallowEqual;
        this.value = undefined;
        this._unsubscribe = null;
        host.addController(this);
    }

    hostConnected() {
        const bus = getPlatformBus();
        this.value = this.selector(bus.getState());
        this._unsubscribe = bus.subscribeSelector(
            this.selector,
            (next) => {
                this.value = next;
                this.host.requestUpdate();
            },
            { equality: this.equality },
        );
    }

    hostDisconnected() {
        if (this._unsubscribe) {
            this._unsubscribe();
            this._unsubscribe = null;
        }
    }
}
