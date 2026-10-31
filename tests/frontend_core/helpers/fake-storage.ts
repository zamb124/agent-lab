/**
 * In-memory shim для localStorage / sessionStorage в Node.
 *
 * installFakeStorage() ставит globalThis.localStorage и sessionStorage в
 * совместимый Storage-like объект; uninstall() возвращает прежнее значение.
 */

class MemoryStorage implements Storage {
    private _data = new Map<string, string>();
    get length(): number { return this._data.size; }
    key(idx: number): string | null { return [...this._data.keys()][idx] ?? null; }
    getItem(k: string): string | null { return this._data.has(k) ? this._data.get(k) ?? null : null; }
    setItem(k: string, v: string): void { this._data.set(String(k), String(v)); }
    removeItem(k: string): void { this._data.delete(String(k)); }
    clear(): void { this._data.clear(); }
}

export function installFakeStorage() {
    const prevLocal = globalThis.localStorage;
    const prevSession = globalThis.sessionStorage;
    const localStorage = new MemoryStorage();
    const sessionStorage = new MemoryStorage();
    Object.defineProperty(globalThis, 'localStorage', { value: localStorage, configurable: true, writable: true });
    Object.defineProperty(globalThis, 'sessionStorage', { value: sessionStorage, configurable: true, writable: true });
    return {
        localStorage,
        sessionStorage,
        uninstall(): void {
            Object.defineProperty(globalThis, 'localStorage', { value: prevLocal, configurable: true, writable: true });
            Object.defineProperty(globalThis, 'sessionStorage', { value: prevSession, configurable: true, writable: true });
        },
    };
}
