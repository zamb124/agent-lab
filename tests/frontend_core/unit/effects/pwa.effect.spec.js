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

    it('новая версия → дополнительно UPDATE_AVAILABLE', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v2' });
        const dispatched = [];
        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: 'v1' } }), dispatched),
        );
        const upd = dispatched.find((d) => d.type === CoreEvents.PWA_UPDATE_AVAILABLE);
        expect(upd.payload).toEqual({ from: 'v1', to: 'v2' });
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
