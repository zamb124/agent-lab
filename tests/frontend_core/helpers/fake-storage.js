/**
 * In-memory shim для localStorage / sessionStorage в Node.
 *
 * installFakeStorage() ставит globalThis.localStorage и sessionStorage в
 * совместимый Storage-like объект; uninstall() возвращает прежнее значение.
 */

class MemoryStorage {
    constructor() { this._data = new Map(); }
    get length() { return this._data.size; }
    key(idx) { return [...this._data.keys()][idx] ?? null; }
    getItem(k) { return this._data.has(k) ? this._data.get(k) : null; }
    setItem(k, v) { this._data.set(String(k), String(v)); }
    removeItem(k) { this._data.delete(String(k)); }
    clear() { this._data.clear(); }
}

export function installFakeStorage() {
    const prevLocal = globalThis.localStorage;
    const prevSession = globalThis.sessionStorage;
    const localStorage = new MemoryStorage();
    const sessionStorage = new MemoryStorage();
    globalThis.localStorage = localStorage;
    globalThis.sessionStorage = sessionStorage;
    return {
        localStorage,
        sessionStorage,
        uninstall() {
            globalThis.localStorage = prevLocal;
            globalThis.sessionStorage = prevSession;
        },
    };
}
