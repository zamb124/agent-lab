/**
 * Router slice.
 *
 * Поля state.router:
 *   routeKey:  string|null
 *   params:    object
 *   pathname:  string
 *   notFound:  boolean
 *   routes:    array of { key, path, parent? } — конфигурация маршрутов сервиса,
 *              регистрируется через ROUTER_ROUTES_REGISTERED при создании effect.
 */

import { CoreEvents } from '../contract.js';

export const initialRouterState = Object.freeze({
    routeKey: null,
    params: {},
    pathname: typeof location !== 'undefined' ? location.pathname : '/',
    notFound: false,
    routes: Object.freeze([]),
});

export function routerReducer(state = initialRouterState, event) {
    switch (event.type) {
        case CoreEvents.ROUTER_ROUTE_CHANGED: {
            const p = event.payload || {};
            return {
                ...state,
                routeKey: p.routeKey || null,
                params: p.params || {},
                pathname: p.pathname || state.pathname,
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
