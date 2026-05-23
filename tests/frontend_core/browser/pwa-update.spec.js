import { createPwaEffect, PWA_EVENTS, _setPwaReloadForTests } from '@platform/lib/events/effects/pwa.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { expect } from './helpers/render.js';
import { installFetchMock } from './helpers/fake-fetch.js';
import { buildCtx } from '../helpers/bus-fixtures.js';

const DEPLOYMENT_VERSION_STORAGE_KEY = 'platform:core:deployment_version';

const ev = (type, payload = null) => ({
    id: `browser_${type}`,
    type,
    payload,
    meta: { ts: 0, source: 'test' },
});

async function deleteHumanitecCaches() {
    if (typeof caches === 'undefined') {
        return;
    }
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith('humanitec-')).map((name) => caches.delete(name)));
}

async function putCacheEntry(cacheName, url, body = 'cached') {
    const cache = await caches.open(cacheName);
    await cache.put(url, new Response(body, { status: 200 }));
}

describe('pwa deployment update browser flow', () => {
    let fetchMock;
    let reloadCalls;

    beforeEach(async () => {
        fetchMock = installFetchMock();
        reloadCalls = 0;
        _setPwaReloadForTests(() => {
            reloadCalls += 1;
        });
        window.localStorage.removeItem(DEPLOYMENT_VERSION_STORAGE_KEY);
        await deleteHumanitecCaches();
    });

    afterEach(async () => {
        fetchMock.uninstall();
        _setPwaReloadForTests(null);
        window.localStorage.removeItem(DEPLOYMENT_VERSION_STORAGE_KEY);
        await deleteHumanitecCaches();
    });

    it('на холодном запуске сохраняет первую увиденную deployment version без reload', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v2' });
        const dispatched = [];

        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );

        expect(window.localStorage.getItem(DEPLOYMENT_VERSION_STORAGE_KEY)).to.equal('v2');
        expect(dispatched.some((event) => event.type === CoreEvents.PWA_UPDATE_AVAILABLE)).to.equal(false);
        expect(reloadCalls).to.equal(0);
    });

    it('старая persisted version в реальном браузере чистит Cache Storage и вызывает reload', async () => {
        fetchMock.respondJson('GET', '/svc/health', { deployment_version: 'v2' });
        window.localStorage.setItem(DEPLOYMENT_VERSION_STORAGE_KEY, 'v1');
        await putCacheEntry('humanitec-static-v6', '/static/core/old-module.js', 'old static');
        await putCacheEntry('humanitec-dynamic-v6', '/old-page', 'old html');
        await putCacheEntry('other-cache', '/untouched', 'keep');
        const dispatched = [];

        await createPwaEffect({ baseUrl: '/svc' })(
            ev(PWA_EVENTS.DEPLOYMENT_VERSION_CHECK_REQUESTED),
            buildCtx(() => ({ pwa: { deploymentVersion: null } }), dispatched),
        );

        const updateEvent = dispatched.find((event) => event.type === CoreEvents.PWA_UPDATE_AVAILABLE);
        expect(updateEvent.payload).to.deep.equal({ from: 'v1', to: 'v2' });
        expect(window.localStorage.getItem(DEPLOYMENT_VERSION_STORAGE_KEY)).to.equal('v2');
        expect(reloadCalls).to.equal(1);

        const cacheNames = await caches.keys();
        expect(cacheNames.includes('humanitec-static-v6')).to.equal(false);
        expect(cacheNames.includes('humanitec-dynamic-v6')).to.equal(false);
        expect(cacheNames.includes('other-cache')).to.equal(true);
        await caches.delete('other-cache');
    });
});
