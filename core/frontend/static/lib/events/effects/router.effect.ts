/**
 * Эффект router.
 *
 * Источник правды о текущем маршруте — state.router. Effect синхронизирует state
 * с реальным URL и наоборот:
 *   - на ROUTER_NAVIGATE_REQUESTED делает history.pushState или replaceState (payload.replace)
 *     и эмитит ROUTER_ROUTE_CHANGED.
 *   - слушает popstate / onload и эмитит ROUTER_ROUTE_CHANGED по текущему URL.
 *
 * Маршруты регистрируются через registerRoutes(routes) — массив { key, path, parent?, title? }.
 * Match — по строгому совпадению path с поддержкой параметров `:name`.
 */

import { CoreEvents } from '../contract.js';
import type { PlatformEvent, EffectCtx } from '../contract.js';
import type { RouterRoute } from '../reducers/router.js';
import { isPlainRecord, payloadFields, stringField } from '../payload.js';

interface CompiledRoute extends RouterRoute {
    _paramNames: string[];
    _pattern: RegExp;
}

function _extractParams(path: string): string[] {
    const matches = path.match(/:([a-zA-Z_][a-zA-Z0-9_]*)/g);
    return matches ? matches.map((m) => m.slice(1)) : [];
}

function _buildPattern(path: string): RegExp {
    const re = path.replace(/:([a-zA-Z_][a-zA-Z0-9_]*)/g, '([^/]+)');
    return new RegExp(`^${re}$`);
}

function _matchRoute(routes: CompiledRoute[], pathRel: string): { route: CompiledRoute; params: Record<string, string> } | null {
    for (const r of routes) {
        const m = pathRel.match(r._pattern);
        if (m) {
            const params: Record<string, string> = {};
            r._paramNames.forEach((name, i) => {
                const raw = m[i + 1];
                if (raw === undefined) {
                    throw new Error(`router.effect: missing capture for "${name}"`);
                }
                params[name] = decodeURIComponent(raw);
            });
            return { route: r, params };
        }
    }
    return null;
}

function _navigateParams(value: unknown): Record<string, string> {
    if (value === undefined || value === null) {
        return {};
    }
    if (!isPlainRecord(value)) {
        throw new Error('router.effect: params must be an object');
    }
    const params: Record<string, string> = {};
    for (const key of Object.keys(value)) {
        const item = value[key];
        if (typeof item !== 'string') {
            throw new Error(`router.effect: param "${key}" must be a string`);
        }
        params[key] = item;
    }
    return params;
}

function _buildPath(route: CompiledRoute, params: Record<string, string>): string {
    let p = route.path;
    for (const name of route._paramNames) {
        const v = params[name];
        if (v === undefined || v === null) {
            throw new Error(`router.effect: missing param "${name}" for route "${route.key}"`);
        }
        p = p.replace(`:${name}`, encodeURIComponent(v));
    }
    return p;
}

export function createRouterEffect({ baseUrl, routes }: { baseUrl?: string; routes: RouterRoute[] }): (event: PlatformEvent, ctx: EffectCtx) => Promise<void> {
    if (!Array.isArray(routes) || routes.length === 0) {
        throw new Error('router.effect: non-empty routes[] required');
    }
    const base = typeof baseUrl === 'string' ? baseUrl : '';
    const compiled = routes.map((r) => ({
        ...r,
        _paramNames: _extractParams(r.path),
        _pattern: _buildPattern(r.path),
    }));
    const publicRoutes = routes.map((r) => {
        const out: { key: string; path: string; parent?: string; titleKey?: string } = { key: r.key, path: r.path };
        if (typeof r.parent === 'string' && r.parent.length > 0) out.parent = r.parent;
        const titleKey = 'titleKey' in r ? r.titleKey : undefined;
        if (typeof titleKey === 'string' && titleKey.length > 0) {
            out.titleKey = titleKey;
        }
        return out;
    });

    let popstateAttached = false;
    let routesRegistered = false;

    function _emitForCurrentUrl(ctx: EffectCtx): void {
        const pathname = location.pathname;
        const rel = pathname.startsWith(base) ? pathname.slice(base.length) : pathname;
        const cleaned = rel.startsWith('/') ? rel.slice(1) : rel;
        const matched = _matchRoute(compiled, cleaned);
        if (!matched) {
            ctx.dispatch(CoreEvents.ROUTER_NOT_FOUND, { pathname }, { source: 'router' });
            return;
        }
        ctx.dispatch(
            CoreEvents.ROUTER_ROUTE_CHANGED,
            {
                routeKey: matched.route.key,
                params: matched.params,
                pathname,
                search: typeof location.search === 'string' ? location.search : '',
            },
            { source: 'router' },
        );
    }

    return async function routerEffect(event: PlatformEvent, ctx: EffectCtx): Promise<void> {
        if (!popstateAttached) {
            popstateAttached = true;
            window.addEventListener('popstate', () => _emitForCurrentUrl(ctx));
        }
        if (!routesRegistered) {
            routesRegistered = true;
            ctx.dispatch(
                CoreEvents.ROUTER_ROUTES_REGISTERED,
                { routes: publicRoutes },
                { source: 'router' },
            );
        }

        switch (event.type) {
            case CoreEvents.APP_BOOTSTRAP_STARTED:
                _emitForCurrentUrl(ctx);
                return;

            case CoreEvents.ROUTER_NAVIGATE_REQUESTED: {
                const p = payloadFields(event);
                const routeKey = stringField(p.routeKey);
                const route = routeKey === null ? undefined : compiled.find((r) => r.key === routeKey);
                if (!route) {
                    throw new Error(`router.effect: unknown routeKey "${String(p.routeKey)}"`);
                }
                const params = _navigateParams(p.params);
                const path = _buildPath(route, params);
                const fullPath = `${base}/${path}`;
                let search = '';
                if (Object.prototype.hasOwnProperty.call(p, 'search')) {
                    const s = p.search;
                    if (typeof s !== 'string') {
                        throw new Error('router.effect: search must be a string');
                    }
                    if (s.length > 0 && !s.startsWith('?')) {
                        throw new Error('router.effect: search must start with ?');
                    }
                    search = s;
                }
                const urlForHistory = fullPath + search;
                const replace = p.replace === true;
                if (replace) {
                    history.replaceState({}, '', urlForHistory);
                } else {
                    history.pushState({}, '', urlForHistory);
                }
                ctx.dispatch(
                    CoreEvents.ROUTER_ROUTE_CHANGED,
                    {
                        routeKey: route.key,
                        params,
                        pathname: fullPath,
                        search,
                    },
                    { causation_id: event.id, source: 'router' },
                );
                return;
            }

            default:
                return;
        }
    };
}
