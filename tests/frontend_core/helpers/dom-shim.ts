/**
 * Минимальный DOM/window shim для unit-тестов effects, которые трогают
 * window.matchMedia, document.documentElement, document.querySelector и т.п.
 *
 * Не претендует быть полным jsdom: каждый effect-spec выставляет ровно то,
 * что нужно ему. Для совершенно DOM-зависимых компонентов есть Layer 3 (Web
 * Test Runner + Playwright).
 */

class FakeClassList {
    readonly list = new Set<string>();
    add = (c: string): void => { this.list.add(c); };
    remove = (c: string): void => { this.list.delete(c); };
    contains = (c: string): boolean => this.list.has(c);
}

class FakeElement {
    readonly attributes = new Map<string, string>();
    style: Record<string, string> = {};
    readonly classList = new FakeClassList();
    readonly children: FakeElement[] = [];
    tagName = '';

    setAttribute(name: string, value: string): void { this.attributes.set(name, String(value)); }
    getAttribute(name: string): string | null { return this.attributes.has(name) ? this.attributes.get(name) ?? null : null; }
    removeAttribute(name: string): void { this.attributes.delete(name); }
    addEventListener(): void {}
    removeEventListener(): void {}
    appendChild(child: FakeElement): void { this.children.push(child); }
}

class FakeMediaQueryList {
    matches: boolean;
    private _listeners = new Set<(event: { matches: boolean }) => void>();

    constructor(matches = false) {
        this.matches = matches;
    }

    addEventListener(name: string, fn: (event: { matches: boolean }) => void): void { if (name === 'change') this._listeners.add(fn); }
    removeEventListener(name: string, fn: (event: { matches: boolean }) => void): void { if (name === 'change') this._listeners.delete(fn); }
    addListener(fn: (event: { matches: boolean }) => void): void { this._listeners.add(fn); }
    removeListener(fn: (event: { matches: boolean }) => void): void { this._listeners.delete(fn); }
    fire(matches: boolean): void { this.matches = matches; for (const fn of this._listeners) fn({ matches }); }
}

export interface DomShimOptions {
    systemDark?: boolean;
}

export function installDomShim(opts: DomShimOptions = {}) {
    const documentElement = new FakeElement();
    const head = new FakeElement();
    const body = new FakeElement();
    const themeColorMeta = new FakeElement();
    themeColorMeta.setAttribute('name', 'theme-color');
    head.children.push(themeColorMeta);
    const intervals = new Set<ReturnType<typeof setInterval>>();

    const mediaQueries = new Map<string, FakeMediaQueryList>();
    const matchMedia = (q: string): FakeMediaQueryList => {
        if (!mediaQueries.has(q)) mediaQueries.set(q, new FakeMediaQueryList(q.includes('dark') ? Boolean(opts.systemDark) : false));
        const mql = mediaQueries.get(q);
        if (!mql) throw new Error('matchMedia registry failed');
        return mql;
    };

    const document = {
        documentElement,
        head,
        body,
        cookie: '',
        querySelector(sel: string): FakeElement | null {
            if (sel === 'meta[name="theme-color"]') return themeColorMeta;
            if (sel === 'meta[name="viewport"]') {
                const meta = new FakeElement();
                meta.setAttribute('name', 'viewport');
                return meta;
            }
            return null;
        },
        addEventListener(): void {},
        removeEventListener(): void {},
        createElement(tag: string): FakeElement {
            const el = new FakeElement();
            el.tagName = tag.toUpperCase();
            return el;
        },
        querySelectorAll: (): FakeElement[] => [],
    };

    const eventListeners = new Map<string, Set<(event: object) => void>>();
    const storageEntries = new Map<string, string>();
    const localStorage = {
        getItem: (key: string): string | null => (storageEntries.has(key) ? storageEntries.get(key) ?? null : null),
        setItem: (key: string, value: string): void => { storageEntries.set(key, String(value)); },
        removeItem: (key: string): void => { storageEntries.delete(key); },
        clear: (): void => { storageEntries.clear(); },
    };

    const window = {
        document,
        localStorage,
        location: { protocol: 'http:', host: 'localhost', hostname: 'localhost', search: '', pathname: '/', href: 'http://localhost/' },
        navigator: { onLine: true, userAgent: 'node-test', standalone: false, serviceWorker: null },
        matchMedia,
        addEventListener(name: string, fn: (event: object) => void): void {
            if (!eventListeners.has(name)) eventListeners.set(name, new Set());
            eventListeners.get(name)?.add(fn);
        },
        removeEventListener(name: string, fn: (event: object) => void): void { eventListeners.get(name)?.delete(fn); },
        dispatchEvent: (): boolean => true,
        setInterval: (fn: () => void, ms: number): ReturnType<typeof setInterval> => { const id = setInterval(fn, ms); intervals.add(id); return id; },
        clearInterval: (id: ReturnType<typeof setInterval>): void => { clearInterval(id); intervals.delete(id); },
        Notification: class { static permission = 'default'; static requestPermission(): Promise<string> { return Promise.resolve('default'); } },
    };

    const prev: Record<string, unknown> = {};
    for (const k of ['window', 'document', 'navigator', 'location', 'matchMedia', 'Notification', 'localStorage']) {
        prev[k] = Reflect.get(globalThis, k);
    }
    const setGlobal = (key: string, value: unknown): void => {
        Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
    };
    setGlobal('window', window);
    setGlobal('document', document);
    setGlobal('navigator', window.navigator);
    setGlobal('location', window.location);
    setGlobal('matchMedia', matchMedia);
    setGlobal('Notification', window.Notification);
    setGlobal('localStorage', localStorage);

    return {
        window,
        document,
        documentElement,
        themeColorMeta,
        mediaQueries,
        eventListeners,
        fireWindowEvent(name: string): void {
            const handlers = eventListeners.get(name);
            if (!handlers) return;
            for (const h of handlers) h({});
        },
        uninstall(): void {
            for (const id of intervals) clearInterval(id);
            for (const k of ['window', 'document', 'navigator', 'location', 'matchMedia', 'Notification', 'localStorage']) {
                if (prev[k] !== undefined) {
                    Object.defineProperty(globalThis, k, { value: prev[k], configurable: true, writable: true });
                } else {
                    Reflect.deleteProperty(globalThis, k);
                }
            }
        },
    };
}
