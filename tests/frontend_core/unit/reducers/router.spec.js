import { describe, it, expect } from 'vitest';
import { routerReducer, initialRouterState } from '@platform/lib/events/reducers/router.js';
import { CoreEvents } from '@platform/lib/events/contract.js';

const ev = (type, payload = null) => ({ id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local' } });

describe('routerReducer', () => {
    it('initial: routeKey=null, params={}, notFound=false', () => {
        expect(initialRouterState.routeKey).toBeNull();
        expect(initialRouterState.params).toEqual({});
        expect(initialRouterState.notFound).toBe(false);
    });

    it('ROUTER_ROUTE_CHANGED заполняет routeKey/params/pathname/search', () => {
        const next = routerReducer(initialRouterState, ev(CoreEvents.ROUTER_ROUTE_CHANGED, {
            routeKey: 'channel',
            params: { id: 'c1' },
            pathname: '/sync/c/c1',
            search: '?tab=main',
        }));
        expect(next.routeKey).toBe('channel');
        expect(next.params).toEqual({ id: 'c1' });
        expect(next.pathname).toBe('/sync/c/c1');
        expect(next.search).toBe('?tab=main');
        expect(next.notFound).toBe(false);
    });

    it('ROUTER_NOT_FOUND ставит notFound=true', () => {
        const next = routerReducer(initialRouterState, ev(CoreEvents.ROUTER_NOT_FOUND, { pathname: '/missing' }));
        expect(next.notFound).toBe(true);
        expect(next.routeKey).toBeNull();
    });

    it('неизвестный event → identity', () => {
        const next = routerReducer(initialRouterState, ev('foo/bar/baz'));
        expect(next).toBe(initialRouterState);
    });
});
