import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createPwaEffect, PWA_EVENTS } from '@platform/lib/events/effects/pwa.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import type { PlatformEvent } from '../../../../core/frontend/static/lib/events/contract.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';
import { prop } from '../../helpers/prop.js';

let dom: ReturnType<typeof installDomShim>;
let fetchMock: ReturnType<typeof installFetchMock>;
const DEPLOYMENT_VERSION_STORAGE_KEY = 'platform:core:deployment_version';

beforeEach(() => {
    dom = installDomShim();
    fetchMock = installFetchMock();
    vi.useFakeTimers();
});
afterEach(() => {
    vi.useRealTimers();
    fetchMock.uninstall();
    Reflect.deleteProperty(globalThis, 'caches');
    Reflect.deleteProperty(globalThis, 'localStorage');
    dom.uninstall();
});

const ev = (type: string, payload = null): PlatformEvent => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'system', causation_id: null, correlation_id: null, trace_id: null } });

function installLocalStorage(initial: Record<string, string> = {}) {
    const values = new Map(Object.entries(initial));
    const storage = {
        getItem(key: string) {
            return values.has(key) ? values.get(key) : null;
        },
        setItem(key: string, value: unknown) {
            values.set(key, String(value));
        },
        removeItem(key: string) {
            values.delete(key);
        },
    };
    Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true, writable: true });
    Object.defineProperty(dom.window, 'localStorage', { value: storage, configurable: true, writable: true });
    return storage;
}

describe('pwaEffect: bootstrap', () => {
    it('эмитит permission и крутит проверку версии', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v1' });
        const dispatched: DispatchedRecord[] = [];
        const effect = createPwaEffect({ baseUrl: '/svc' });
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched));
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(CoreEvents.PWA_PUSH_PERMISSION_REQUESTED);
        expect(types).toContain(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED);
    });

    it('повторный bootstrap не привязывает дважды', async () => {
        const dispatched: DispatchedRecord[] = [];
        const effect = createPwaEffect({ baseUrl: '/svc' });
        const ctx = buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched);
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v1' });
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), ctx);
        const beforeCount = dispatched.filter((d) => d.type === CoreEvents.PWA_PUSH_PERMISSION_REQUESTED).length;
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), ctx);
        const afterCount = dispatched.filter((d) => d.type === CoreEvents.PWA_PUSH_PERMISSION_REQUESTED).length;
        expect(afterCount).toBe(beforeCount);
    });

    it('первый bootstrap вызывает serviceWorker.register', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v1' });
        const register = vi.fn(() => Promise.resolve({}));
        Object.assign(dom.window.navigator, { serviceWorker: { register } });
        const dispatched: DispatchedRecord[] = [];
        await createPwaEffect({ baseUrl: '/svc' })(
            ev(CoreEvents.APP_BOOTSTRAP_STARTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );
        expect(register).toHaveBeenCalledWith('/sw.js', { scope: '/' });
    });
});

describe('pwaEffect: DEPLOYMENT_VERSION_CHECK_REQUESTED', () => {
    it('успех → DEPLOYMENT_VERSION_LOADED', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v2' });
        const dispatched: DispatchedRecord[] = [];
        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );
        expect(prop(dispatched.find((d) => d.type === PWA_EVENTS.DEPLOYMENT_VERSION_LOADED)?.payload, 'version')).toBe('v2');
    });

    it('успех сохраняет deployment version между запусками', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v2' });
        const storage = installLocalStorage();
        const dispatched: DispatchedRecord[] = [];
        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );
        expect(storage.getItem(DEPLOYMENT_VERSION_STORAGE_KEY)).toBe('v2');
        expect(dispatched.find((d) => d.type === CoreEvents.PWA_UPDATE_AVAILABLE)).toBeFalsy();
    });

    it('холодный запуск со старой stored version → UPDATE_AVAILABLE, очистка кэшей и reload', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v2' });
        const storage = installLocalStorage({ [DEPLOYMENT_VERSION_STORAGE_KEY]: 'v1' });
        const dispatched: DispatchedRecord[] = [];
        const deleted: string[] = [];
        Object.defineProperty(globalThis, 'caches', { configurable: true, writable: true, value: {
            keys: async () => ['linnex-static-v6', 'linnex-dynamic-v6', 'other-cache'],
            delete: async (name: string) => {
                deleted.push(name);
                return true;
            },
        } });
        const update = vi.fn(async () => {});
        Object.assign(dom.window.navigator, { serviceWorker: {
            getRegistration: async () => ({ update, waiting: null }),
        } });
        const reload = vi.fn();
        Object.assign(dom.window.location, { reload });

        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );
        const upd = dispatched.find((d) => d.type === CoreEvents.PWA_UPDATE_AVAILABLE);
        expect(upd?.payload).toEqual({ from: 'v1', to: 'v2' });
        expect(deleted).toEqual(['linnex-static-v6', 'linnex-dynamic-v6']);
        expect(update).toHaveBeenCalledTimes(1);
        expect(reload).toHaveBeenCalledTimes(1);
        expect(storage.getItem(DEPLOYMENT_VERSION_STORAGE_KEY)).toBe('v2');
    });

    it('новая версия → UPDATE_AVAILABLE, очистка linnex-кэшей, update SW и reload', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v2' });
        const dispatched: DispatchedRecord[] = [];
        const deleted: string[] = [];
        Object.defineProperty(globalThis, 'caches', { configurable: true, writable: true, value: {
            keys: async () => ['linnex-static-v5', 'other-cache'],
            delete: async (name: string) => {
                deleted.push(name);
                return true;
            },
        } });
        const postMessage = vi.fn();
        const update = vi.fn(async () => {});
        Object.assign(dom.window.navigator, { serviceWorker: {
            register: vi.fn(() => Promise.resolve({})),
            getRegistration: async () => ({
                update,
                waiting: { postMessage },
            }),
        } });
        const reload = vi.fn();
        Object.assign(dom.window.location, { reload });

        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: 'v1' } }), dispatched),
        );
        const upd = dispatched.find((d) => d.type === CoreEvents.PWA_UPDATE_AVAILABLE);
        expect(upd?.payload).toEqual({ from: 'v1', to: 'v2' });
        expect(deleted).toEqual(['linnex-static-v5']);
        expect(update).toHaveBeenCalledTimes(1);
        expect(postMessage).toHaveBeenCalledWith({ type: 'skipWaiting' });
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it('новая версия без waiting worker — только update и reload', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v2' });
        const dispatched: DispatchedRecord[] = [];
        Object.defineProperty(globalThis, 'caches', { configurable: true, writable: true, value: {
            keys: async () => [],
            delete: async () => true,
        } });
        const update = vi.fn(async () => {});
        Object.assign(dom.window.navigator, { serviceWorker: {
            register: vi.fn(() => Promise.resolve({})),
            getRegistration: async () => ({ update, waiting: null }),
        } });
        const reload = vi.fn();
        Object.assign(dom.window.location, { reload });

        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: 'v1' } }), dispatched),
        );
        expect(update).toHaveBeenCalledTimes(1);
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it('ошибка → DEPLOYMENT_VERSION_LOAD_FAILED', async () => {
        fetchMock.respondStatus('GET', '/svc/health', 500);
        const dispatched: DispatchedRecord[] = [];
        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );
        expect(dispatched.find((d) => d.type === PWA_EVENTS.DEPLOYMENT_VERSION_LOAD_FAILED)).toBeTruthy();
    });
});

describe('pwaEffect: PUSH_PERMISSION_REQUEST_REQUESTED', () => {
    it('эмитит PUSH_PERMISSION_REQUESTED с результатом запроса', async () => {
        const dispatched: DispatchedRecord[] = [];
        const original = globalThis.Notification.requestPermission;
        globalThis.Notification.requestPermission = async () => 'granted';
        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.PUSH_PERMISSION_REQUEST_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );
        const perm = dispatched.find((d) => d.type === CoreEvents.PWA_PUSH_PERMISSION_REQUESTED);
        expect(prop(perm?.payload, 'permission')).toBe('granted');
        globalThis.Notification.requestPermission = original;
    });
});
