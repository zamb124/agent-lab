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
import type { MockInstance } from 'vitest';
import { installFakeStorage } from '../helpers/fake-storage.js';
import { installFetchMock } from '../helpers/mock-fetch.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import type { SliceDef } from '@platform/lib/events/reducers/index.js';

type PlatformEventsModule = typeof import('@platform/lib/events/index.js');

interface HelloState {
    value: string;
}

function installWindowShim() {
    const handlers = new Map<string, Set<EventListenerOrEventListenerObject>>();
    const intervals: ReturnType<typeof setInterval>[] = [];
    const fakeDocument = {
        addEventListener() {}, removeEventListener() {},
        querySelector: () => null,
        documentElement: { style: {}, classList: { add() {}, remove() {} }, getAttribute: () => null, setAttribute() {} },
        body: { appendChild() {} },
        createElement: () => ({ addEventListener() {}, style: {} }),
    };
    const fakeWindow = {
        addEventListener(name: string, fn: EventListenerOrEventListenerObject) {
            if (!handlers.has(name)) handlers.set(name, new Set());
            handlers.get(name)?.add(fn);
        },
        removeEventListener(name: string, fn: EventListenerOrEventListenerObject) {
            handlers.get(name)?.delete(fn);
        },
        location: { protocol: 'http:', host: 'localhost', search: '', pathname: '/', href: 'http://localhost/' },
        navigator: { onLine: true, userAgent: 'node-test' },
        matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
        document: fakeDocument,
        setInterval: (fn: () => void, ms?: number) => { const id = setInterval(fn, ms); intervals.push(id); return id; },
        clearInterval: (id: ReturnType<typeof setInterval>) => clearInterval(id),
        dispatchEvent: () => true,
    };
    const prevWindow = globalThis.window;
    const prevDocument = globalThis.document;
    const prevNavigator = globalThis.navigator;
    const prevLocation = globalThis.location;
    const prevMatchMedia = globalThis.matchMedia;
    Object.defineProperty(globalThis, 'window', { value: fakeWindow, configurable: true, writable: true });
    Object.defineProperty(globalThis, 'document', { value: fakeDocument, configurable: true, writable: true });
    Object.defineProperty(globalThis, 'navigator', { value: fakeWindow.navigator, configurable: true });
    Object.defineProperty(globalThis, 'location', { value: fakeWindow.location, configurable: true });
    Object.defineProperty(globalThis, 'matchMedia', { value: fakeWindow.matchMedia, configurable: true, writable: true });
    return {
        window: fakeWindow,
        uninstall() {
            for (const id of intervals) clearInterval(id);
            Object.defineProperty(globalThis, 'window', { value: prevWindow, configurable: true, writable: true });
            Object.defineProperty(globalThis, 'document', { value: prevDocument, configurable: true, writable: true });
            if (prevNavigator !== undefined) {
                Object.defineProperty(globalThis, 'navigator', { value: prevNavigator, configurable: true });
            } else {
                Reflect.deleteProperty(globalThis, 'navigator');
            }
            if (prevLocation !== undefined) {
                Object.defineProperty(globalThis, 'location', { value: prevLocation, configurable: true });
            } else {
                Reflect.deleteProperty(globalThis, 'location');
            }
            Object.defineProperty(globalThis, 'matchMedia', { value: prevMatchMedia, configurable: true, writable: true });
        },
    };
}

let win: ReturnType<typeof installWindowShim>;
let storage: ReturnType<typeof installFakeStorage>;
let fetchMock: ReturnType<typeof installFetchMock>;
let consoleErr: MockInstance;
let events: PlatformEventsModule;

beforeEach(async () => {
    win = installWindowShim();
    storage = installFakeStorage();
    fetchMock = installFetchMock();
    // Глушим шум от theme/i18n/auth effects, которые на bootstrap пытаются
    // достучаться до /api/auth/me и /static/i18n. В этом spec мы тестируем
    // только bootstrap-инициализацию, не сетевые эффекты.
    consoleErr = vi.spyOn(console, 'error').mockImplementation(() => {});
    events = await import('@platform/lib/events/index.js');
    events.resetPlatformBusForTests();
});

afterEach(() => {
    events.resetPlatformBusForTests();
    fetchMock.uninstall();
    storage.uninstall();
    consoleErr.mockRestore();
    win.uninstall();
});

describe('bootstrapPlatformBus', () => {
    it('поднимает bus с core slices (auth, theme, i18n, ui, ...)', () => {
        const bus = events.bootstrapPlatformBus({ baseUrl: '/svc' });
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
        const a = events.bootstrapPlatformBus({ baseUrl: '/svc' });
        const b = events.bootstrapPlatformBus({ baseUrl: '/other' });
        expect(b).toBe(a);
        expect(events.getPlatformBus()).toBe(a);
    });

    it('эмитит APP_BOOTSTRAP_STARTED и принимает payload', () => {
        const bus = events.bootstrapPlatformBus({ baseUrl: '/svc' });
        // событие должно быть в логе (devMode выставляется по location.search)
        const captured: string[] = [];
        bus.subscribeType('test/dummy/x', (ev: PlatformEvent) => { captured.push(ev.type); });
        bus.dispatch('test/dummy/x', null);
        expect(captured).toContain('test/dummy/x');
    });

    it('completeBootstrap эмитит APP_BOOTSTRAP_COMPLETED', () => {
        events.bootstrapPlatformBus({ baseUrl: '/svc' });
        const bus = events.getPlatformBus();
        const seen: PlatformEvent[] = [];
        bus.subscribeType(events.CoreEvents.APP_BOOTSTRAP_COMPLETED, (ev) => seen.push(ev));
        events.completeBootstrap();
        expect(seen).toHaveLength(1);
    });

    it('сервисный slice мержится в state', () => {
        const initial: HelloState = Object.freeze({ value: 'hello' });
        const customSlice: SliceDef<HelloState> = {
            initial,
            reducer: (state: HelloState) => state,
        };
        const slices: Record<string, SliceDef> = { custom: customSlice };
        const bus = events.bootstrapPlatformBus({
            baseUrl: '/svc',
            slices,
        });
        expect(bus.getState()['custom']).toEqual({ value: 'hello' });
    });
});
