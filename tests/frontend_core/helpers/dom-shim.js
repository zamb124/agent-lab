/**
 * Минимальный DOM/window shim для unit-тестов effects, которые трогают
 * window.matchMedia, document.documentElement, document.querySelector и т.п.
 *
 * Не претендует быть полным jsdom: каждый effect-spec выставляет ровно то,
 * что нужно ему. Для совершенно DOM-зависимых компонентов есть Layer 3 (Web
 * Test Runner + Playwright).
 */

class FakeElement {
    constructor() {
        this.attributes = new Map();
        this.style = {};
        this.classList = {
            list: new Set(),
            add: (c) => { this.classList.list.add(c); },
            remove: (c) => { this.classList.list.delete(c); },
            contains: (c) => this.classList.list.has(c),
        };
        this.children = [];
    }
    setAttribute(name, value) { this.attributes.set(name, String(value)); }
    getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
    removeAttribute(name) { this.attributes.delete(name); }
    addEventListener() {}
    removeEventListener() {}
    appendChild(child) { this.children.push(child); }
}

class FakeMediaQueryList {
    constructor(matches = false) {
        this.matches = matches;
        this._listeners = new Set();
    }
    addEventListener(name, fn) { if (name === 'change') this._listeners.add(fn); }
    removeEventListener(name, fn) { if (name === 'change') this._listeners.delete(fn); }
    addListener(fn) { this._listeners.add(fn); }
    removeListener(fn) { this._listeners.delete(fn); }
    fire(matches) { this.matches = matches; for (const fn of this._listeners) fn({ matches }); }
}

export function installDomShim(opts = {}) {
    const documentElement = new FakeElement();
    const head = new FakeElement();
    const body = new FakeElement();
    const themeColorMeta = new FakeElement();
    themeColorMeta.setAttribute('name', 'theme-color');
    head.children.push(themeColorMeta);
    const intervals = new Set();

    const mediaQueries = new Map();
    const matchMedia = (q) => {
        if (!mediaQueries.has(q)) mediaQueries.set(q, new FakeMediaQueryList(q.includes('dark') ? Boolean(opts.systemDark) : false));
        return mediaQueries.get(q);
    };

    const document = {
        documentElement,
        head,
        body,
        querySelector(sel) {
            if (sel === 'meta[name="theme-color"]') return themeColorMeta;
            if (sel === 'meta[name="viewport"]') {
                const meta = new FakeElement();
                meta.setAttribute('name', 'viewport');
                return meta;
            }
            return null;
        },
        addEventListener() {},
        removeEventListener() {},
        createElement(tag) {
            const el = new FakeElement();
            el.tagName = tag.toUpperCase();
            return el;
        },
        querySelectorAll: () => [],
    };

    const eventListeners = new Map();
    const window = {
        document,
        location: { protocol: 'http:', host: 'localhost', search: '', pathname: '/', href: 'http://localhost/' },
        navigator: { onLine: true, userAgent: 'node-test', standalone: false, serviceWorker: null },
        matchMedia,
        addEventListener(name, fn) {
            if (!eventListeners.has(name)) eventListeners.set(name, new Set());
            eventListeners.get(name).add(fn);
        },
        removeEventListener(name, fn) { if (eventListeners.has(name)) eventListeners.get(name).delete(fn); },
        dispatchEvent: () => true,
        setInterval: (fn, ms) => { const id = setInterval(fn, ms); intervals.add(id); return id; },
        clearInterval: (id) => { clearInterval(id); intervals.delete(id); },
        Notification: class { static permission = 'default'; static requestPermission() { return Promise.resolve('default'); } },
    };

    const prev = {};
    for (const k of ['window', 'document', 'navigator', 'location', 'matchMedia', 'Notification']) {
        prev[k] = globalThis[k];
    }
    globalThis.window = window;
    globalThis.document = document;
    Object.defineProperty(globalThis, 'navigator', { value: window.navigator, configurable: true });
    Object.defineProperty(globalThis, 'location', { value: window.location, configurable: true });
    globalThis.matchMedia = matchMedia;
    globalThis.Notification = window.Notification;

    return {
        window,
        document,
        documentElement,
        themeColorMeta,
        mediaQueries,
        eventListeners,
        fireWindowEvent(name) {
            const handlers = eventListeners.get(name);
            if (!handlers) return;
            for (const h of handlers) h({});
        },
        uninstall() {
            for (const id of intervals) clearInterval(id);
            for (const k of ['window', 'document', 'navigator', 'location', 'matchMedia', 'Notification']) {
                if (prev[k] !== undefined) {
                    if (k === 'navigator' || k === 'location') {
                        Object.defineProperty(globalThis, k, { value: prev[k], configurable: true });
                    } else {
                        globalThis[k] = prev[k];
                    }
                } else {
                    delete globalThis[k];
                }
            }
        },
    };
}
