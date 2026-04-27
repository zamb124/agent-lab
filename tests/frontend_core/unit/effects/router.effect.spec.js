import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';

let dom;
let history;

beforeEach(() => {
    dom = installDomShim();
    const calls = [];
    history = { _calls: calls, pushState(...args) { calls.push(args); dom.window.location.pathname = String(args[2]); } };
    globalThis.history = history;
});
afterEach(() => {
    delete globalThis.history;
    dom.uninstall();
});

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'router' } });

const routes = [
    { key: 'shell', path: '' },
    { key: 'dashboard', path: 'dashboard' },
    { key: 'channel', path: 'c/:channelId' },
];

describe('createRouterEffect: contract', () => {
    it('требует non-empty routes[]', () => {
        expect(() => createRouterEffect({ baseUrl: '/sync', routes: [] })).toThrow(/routes/);
    });
});

describe('routerEffect: bootstrap', () => {
    it('эмитит ROUTER_ROUTE_CHANGED для текущего pathname', async () => {
        dom.window.location.pathname = '/sync/dashboard';
        Object.defineProperty(globalThis.location, 'pathname', { value: '/sync/dashboard', configurable: true });
        const dispatched = [];
        await createRouterEffect({ baseUrl: '/sync', routes })(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        const changed = dispatched.find((d) => d.type === CoreEvents.ROUTER_ROUTE_CHANGED);
        expect(changed.payload.routeKey).toBe('dashboard');
    });

    it('match с параметром', async () => {
        Object.defineProperty(globalThis.location, 'pathname', { value: '/sync/c/c1', configurable: true });
        const dispatched = [];
        await createRouterEffect({ baseUrl: '/sync', routes })(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        const changed = dispatched.find((d) => d.type === CoreEvents.ROUTER_ROUTE_CHANGED);
        expect(changed.payload.params).toEqual({ channelId: 'c1' });
    });

    it('не найден → ROUTER_NOT_FOUND', async () => {
        Object.defineProperty(globalThis.location, 'pathname', { value: '/sync/missing', configurable: true });
        const dispatched = [];
        await createRouterEffect({ baseUrl: '/sync', routes })(ev(CoreEvents.APP_BOOTSTRAP_STARTED), buildCtx(() => ({}), dispatched));
        expect(dispatched.find((d) => d.type === CoreEvents.ROUTER_NOT_FOUND)).toBeTruthy();
    });
});

describe('routerEffect: NAVIGATE_REQUESTED', () => {
    it('делает history.pushState и эмитит ROUTE_CHANGED', async () => {
        const dispatched = [];
        await createRouterEffect({ baseUrl: '/sync', routes })(ev(CoreEvents.ROUTER_NAVIGATE_REQUESTED, { routeKey: 'channel', params: { channelId: 'c1' } }), buildCtx(() => ({}), dispatched));
        expect(history._calls[0][2]).toBe('/sync/c/c1');
        const changed = dispatched.find((d) => d.type === CoreEvents.ROUTER_ROUTE_CHANGED);
        expect(changed.payload.routeKey).toBe('channel');
    });

    it('неизвестный routeKey — throw', async () => {
        const dispatched = [];
        await expect(createRouterEffect({ baseUrl: '/sync', routes })(
            ev(CoreEvents.ROUTER_NAVIGATE_REQUESTED, { routeKey: 'missing' }),
            buildCtx(() => ({}), dispatched),
        )).rejects.toThrow(/unknown routeKey/);
    });

    it('отсутствует обязательный param — throw', async () => {
        await expect(createRouterEffect({ baseUrl: '/sync', routes })(
            ev(CoreEvents.ROUTER_NAVIGATE_REQUESTED, { routeKey: 'channel', params: {} }),
            buildCtx(() => ({}), []),
        )).rejects.toThrow(/missing param/);
    });

    it('search добавляет query к pushState', async () => {
        const dispatched = [];
        await createRouterEffect({ baseUrl: '/sync', routes })(
            ev(CoreEvents.ROUTER_NAVIGATE_REQUESTED, {
                routeKey: 'dashboard',
                params: {},
                search: '?redirect_uri=%2Fsync',
            }),
            buildCtx(() => ({}), dispatched),
        );
        expect(history._calls[0][2]).toBe('/sync/dashboard?redirect_uri=%2Fsync');
    });

    it('search без ведущего ? — throw', async () => {
        await expect(createRouterEffect({ baseUrl: '/sync', routes })(
            ev(CoreEvents.ROUTER_NAVIGATE_REQUESTED, {
                routeKey: 'dashboard',
                params: {},
                search: 'bad=1',
            }),
            buildCtx(() => ({}), []),
        )).rejects.toThrow(/search must start/);
    });
});
