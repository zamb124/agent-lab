import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createPwaEffect, PWA_EVENTS } from '@platform/lib/events/effects/pwa.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { installFetchMock } from '../../helpers/mock-fetch.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let dom;
let fetchMock;

beforeEach(() => {
    dom = installDomShim();
    fetchMock = installFetchMock();
    vi.useFakeTimers();
});
afterEach(() => {
    vi.useRealTimers();
    fetchMock.uninstall();
    dom.uninstall();
});

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'system' } });

describe('pwaEffect: bootstrap', () => {
    it('эмитит permission и крутит проверку версии', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v1' });
        const dispatched = [];
        const effect = createPwaEffect({ baseUrl: '/svc' });
        await effect(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched));
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(CoreEvents.PWA_PUSH_PERMISSION_REQUESTED);
        expect(types).toContain(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED);
    });

    it('повторный bootstrap не привязывает дважды', async () => {
        const dispatched = [];
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
        dom.window.navigator.serviceWorker = { register };
        const dispatched = [];
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
        const dispatched = [];
        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );
        expect(dispatched.find((d) => d.type === PWA_EVENTS.DEPLOYMENT_VERSION_LOADED).payload.version).toBe('v2');
    });

    it('новая версия → UPDATE_AVAILABLE, очистка humanitec-кэшей, update SW и reload', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v2' });
        const dispatched = [];
        const deleted = [];
        globalThis.caches = {
            keys: async () => ['humanitec-static-v5', 'other-cache'],
            delete: async (name) => {
                deleted.push(name);
                return true;
            },
        };
        const postMessage = vi.fn();
        const update = vi.fn(async () => {});
        dom.window.navigator.serviceWorker = {
            register: vi.fn(() => Promise.resolve({})),
            getRegistration: async () => ({
                update,
                waiting: { postMessage },
            }),
        };
        const reload = vi.fn();
        dom.window.location.reload = reload;

        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: 'v1' } }), dispatched),
        );
        const upd = dispatched.find((d) => d.type === CoreEvents.PWA_UPDATE_AVAILABLE);
        expect(upd.payload).toEqual({ from: 'v1', to: 'v2' });
        expect(deleted).toEqual(['humanitec-static-v5']);
        expect(update).toHaveBeenCalledTimes(1);
        expect(postMessage).toHaveBeenCalledWith({ type: 'skipWaiting' });
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it('новая версия без waiting worker — только update и reload', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v2' });
        const dispatched = [];
        globalThis.caches = {
            keys: async () => [],
            delete: async () => true,
        };
        const update = vi.fn(async () => {});
        dom.window.navigator.serviceWorker = {
            register: vi.fn(() => Promise.resolve({})),
            getRegistration: async () => ({ update, waiting: null }),
        };
        const reload = vi.fn();
        dom.window.location.reload = reload;

        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: 'v1' } }), dispatched),
        );
        expect(update).toHaveBeenCalledTimes(1);
        expect(reload).toHaveBeenCalledTimes(1);
    });

    it('ошибка → DEPLOYMENT_VERSION_LOAD_FAILED', async () => {
        fetchMock.respondStatus('GET', '/svc/health', 500);
        const dispatched = [];
        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );
        expect(dispatched.find((d) => d.type === PWA_EVENTS.DEPLOYMENT_VERSION_LOAD_FAILED)).toBeTruthy();
    });
});

describe('pwaEffect: PUSH_PERMISSION_REQUEST_REQUESTED', () => {
    it('эмитит PUSH_PERMISSION_REQUESTED с результатом запроса', async () => {
        const dispatched = [];
        const original = globalThis.Notification.requestPermission;
        globalThis.Notification.requestPermission = async () => 'granted';
        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.PUSH_PERMISSION_REQUEST_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );
        const perm = dispatched.find((d) => d.type === CoreEvents.PWA_PUSH_PERMISSION_REQUESTED);
        expect(perm.payload.permission).toBe('granted');
        globalThis.Notification.requestPermission = original;
    });
});
