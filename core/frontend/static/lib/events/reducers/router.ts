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
import type { PlatformEvent } from '../contract.js';

export interface RouterRoute {
    key: string;
    path: string;
    parent?: string;
    titleKey?: string;
    title?: string | ((params: Record<string, string>) => string);
    itemTitle?: (params: Record<string, string>) => string;
}

export interface RouterState {
    routeKey: string | null;
    params: Record<string, string>;
    pathname: string;
    search: string;
    notFound: boolean;
    routes: readonly RouterRoute[];
}

export const initialRouterState: RouterState = Object.freeze({
    routeKey: null,
    params: {},
    pathname: typeof location !== 'undefined' ? location.pathname : '/',
    search: typeof location !== 'undefined' ? location.search : '',
    notFound: false,
    routes: Object.freeze([]),
});

export function routerReducer(state: RouterState = initialRouterState, event: PlatformEvent): RouterState {
    switch (event.type) {
        case CoreEvents.ROUTER_ROUTE_CHANGED: {
            const p = (event.payload || {}) as {
                routeKey?: string | null; params?: Record<string, string>;
                pathname?: string; search?: unknown;
            };
            const searchNext = typeof p.search === 'string' ? p.search : '';
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
            const p = (event.payload || {}) as { pathname?: string };
            return {
                ...state,
                routeKey: null,
                params: {},
                pathname: p.pathname || state.pathname,
                notFound: true,
            };
        }
        case CoreEvents.ROUTER_ROUTES_REGISTERED: {
            const p = (event.payload || {}) as { routes?: RouterRoute[] };
            const routes = Array.isArray(p.routes) ? p.routes : state.routes;
            return { ...state, routes };
        }
        default:
            return state;
    }
}
