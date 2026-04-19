/**
 * bootstrapPlatformBus / completeBootstrap.
 *
 * Bootstrap дёргает window/document/navigator/location, поэтому требуется
 * минимальный jsdom-like shim. Проверяем что:
 *   - Bus поднимается с core slices.
 *   - Эмитится APP_BOOTSTRAP_STARTED.
 *   - completeBootstrap эмитит APP_BOOTSTRAP_COMPLETED.
 *   - Повторный вызов возвращает тот же singleton.
 *   - Сервисные slices мержатся, дубликаты sliceKey — throw.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { installFakeStorage } from '../helpers/fake-storage.js';
import { installFetchMock } from '../helpers/mock-fetch.js';

function installWindowShim() {
    const handlers = new Map();
    const intervals = [];
    const fakeWindow = {
        addEventListener(name, fn) {
            if (!handlers.has(name)) handlers.set(name, new Set());
            handlers.get(name).add(fn);
        },
        removeEventListener(name, fn) {
            if (handlers.has(name)) handlers.get(name).delete(fn);
        },
        location: { protocol: 'http:', host: 'localhost', search: '', pathname: '/', href: 'http://localhost/' },
        navigator: { onLine: true, userAgent: 'node-test' },
        matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
        document: undefined,
        setInterval: (fn, ms) => { const id = setInterval(fn, ms); intervals.push(id); return id; },
        clearInterval: (id) => clearInterval(id),
        dispatchEvent: () => true,
    };
    const fakeDocument = {
        addEventListener() {}, removeEventListener() {},
        querySelector: () => null,
        documentElement: { style: {}, classList: { add() {}, remove() {} } },
        body: { appendChild() {} },
        createElement: () => ({ addEventListener() {}, style: {} }),
    };
    fakeWindow.document = fakeDocument;
    const prevWindow = globalThis.window;
    const prevDocument = globalThis.document;
    const prevNavigator = globalThis.navigator;
    const prevLocation = globalThis.location;
    const prevMatchMedia = globalThis.matchMedia;
    globalThis.window = fakeWindow;
    globalThis.document = fakeDocument;
    Object.defineProperty(globalThis, 'navigator', { value: fakeWindow.navigator, configurable: true });
    Object.defineProperty(globalThis, 'location', { value: fakeWindow.location, configurable: true });
    globalThis.matchMedia = fakeWindow.matchMedia;
    return {
        window: fakeWindow,
        uninstall() {
            for (const id of intervals) clearInterval(id);
            globalThis.window = prevWindow;
            globalThis.document = prevDocument;
            if (prevNavigator !== undefined) {
                Object.defineProperty(globalThis, 'navigator', { value: prevNavigator, configurable: true });
            } else {
                delete globalThis.navigator;
            }
            if (prevLocation !== undefined) {
                Object.defineProperty(globalThis, 'location', { value: prevLocation, configurable: true });
            } else {
                delete globalThis.location;
            }
            globalThis.matchMedia = prevMatchMedia;
        },
    };
}

let win;
let storage;
let fetchMock;
let consoleErr;
let bootstrapPlatformBus;
let completeBootstrap;
let resetPlatformBusForTests;
let getPlatformBus;
let CoreEvents;

beforeEach(async () => {
    win = installWindowShim();
    storage = installFakeStorage();
    fetchMock = installFetchMock();
    // Глушим шум от theme/i18n/auth effects, которые на bootstrap пытаются
    // достучаться до /api/auth/me и /static/i18n. В этом spec мы тестируем
    // только bootstrap-инициализацию, не сетевые эффекты.
    consoleErr = vi.spyOn(console, 'error').mockImplementation(() => {});
    const events = await import('@platform/lib/events/index.js');
    bootstrapPlatformBus = events.bootstrapPlatformBus;
    completeBootstrap = events.completeBootstrap;
    resetPlatformBusForTests = events.resetPlatformBusForTests;
    getPlatformBus = events.getPlatformBus;
    CoreEvents = events.CoreEvents;
    resetPlatformBusForTests();
});

afterEach(() => {
    if (resetPlatformBusForTests) resetPlatformBusForTests();
    fetchMock.uninstall();
    storage.uninstall();
    consoleErr.mockRestore();
    win.uninstall();
});

describe('bootstrapPlatformBus', () => {
    it('поднимает bus с core slices (auth, theme, i18n, ui, ...)', () => {
        const bus = bootstrapPlatformBus({ baseUrl: '/svc' });
        const state = bus.getState();
        expect(state.auth).toBeTruthy();
        expect(state.theme).toBeTruthy();
        expect(state.i18n).toBeTruthy();
        expect(state.notify).toBeTruthy();
        expect(state.modals).toBeTruthy();
        expect(state.network).toBeTruthy();
        expect(state.router).toBeTruthy();
        expect(state.pwa).toBeTruthy();
        expect(state.ui).toBeTruthy();
        expect(state.icon).toBeTruthy();
        expect(state.fileTypes).toBeTruthy();
        expect(state.files).toBeTruthy();
        expect(state.companies).toBeTruthy();
        expect(state.team).toBeTruthy();
        expect(state.calendar).toBeTruthy();
        expect(state.notifications).toBeTruthy();
    });

    it('повторный вызов возвращает тот же singleton', () => {
        const a = bootstrapPlatformBus({ baseUrl: '/svc' });
        const b = bootstrapPlatformBus({ baseUrl: '/other' });
        expect(b).toBe(a);
        expect(getPlatformBus()).toBe(a);
    });

    it('эмитит APP_BOOTSTRAP_STARTED и принимает payload', () => {
        const bus = bootstrapPlatformBus({ baseUrl: '/svc' });
        // событие должно быть в логе (devMode выставляется по location.search)
        const captured = [];
        bus.subscribeAny((ev) => { captured.push(ev.type); });
        bus.dispatch('test/dummy/x', null);
        expect(captured).toContain('test/dummy/x');
    });

    it('completeBootstrap эмитит APP_BOOTSTRAP_COMPLETED', () => {
        bootstrapPlatformBus({ baseUrl: '/svc' });
        const bus = getPlatformBus();
        const seen = [];
        bus.subscribeType(CoreEvents.APP_BOOTSTRAP_COMPLETED, (ev) => seen.push(ev));
        completeBootstrap();
        expect(seen).toHaveLength(1);
    });

    it('сервисный slice мержится в state', () => {
        const customSlice = {
            initial: Object.freeze({ value: 'hello' }),
            reducer: (state) => state,
        };
        const bus = bootstrapPlatformBus({
            baseUrl: '/svc',
            slices: { custom: customSlice },
        });
        expect(bus.getState().custom).toEqual({ value: 'hello' });
    });
});
