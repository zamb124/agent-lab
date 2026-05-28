/**
 * Слайс router.
 *
 * Поля state.router:
 *   routeKey:  string|null
 *   params:    object
 *   pathname:  string
 *   search:    string — query текущего URL (начинается с ? или пустая строка)
 *   notFound:  boolean
 *   routes:    array of { key, path, parent? } — конфигурация маршрутов сервиса,
 *              регистрируется через ROUTER_ROUTES_REGISTERED при создании effect.
 */

import { CoreEvents } from '../contract.js';

export const initialRouterState = Object.freeze({
    routeKey: null,
    params: {},
    pathname: typeof location !== 'undefined' ? location.pathname : '/',
    search: typeof location !== 'undefined' ? location.search : '',
    notFound: false,
    routes: Object.freeze([]),
});

export function routerReducer(state = initialRouterState, event) {
    switch (event.type) {
        case CoreEvents.ROUTER_ROUTE_CHANGED: {
            const p = event.payload || {};
            const searchRaw = p.search;
            const searchNext = typeof searchRaw === 'string' ? searchRaw : '';
            return {
                ...state,
                routeKey: p.routeKey || null,
                params: p.params || {},
                pathname: p.pathname || state.pathname,
                search: searchNext,
                notFound: false,
            };
        }
        case CoreEvents.ROUTER_NOT_FOUND: {
            const p = event.payload || {};
            return {
                ...state,
                routeKey: null,
                params: {},
                pathname: p.pathname || state.pathname,
                notFound: true,
            };
        }
        case CoreEvents.ROUTER_ROUTES_REGISTERED: {
            const p = event.payload || {};
            const routes = Array.isArray(p.routes) ? p.routes : [];
            return { ...state, routes };
        }
        default:
            return state;
    }
}
