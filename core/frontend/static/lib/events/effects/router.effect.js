/**
 * Router effect.
 *
 * Источник правды о текущем маршруте — state.router. Effect синхронизирует state
 * с реальным URL и наоборот:
 *   - на ROUTER_NAVIGATE_REQUESTED делает history.pushState и эмитит ROUTER_ROUTE_CHANGED.
 *   - слушает popstate / onload и эмитит ROUTER_ROUTE_CHANGED по текущему URL.
 *
 * Маршруты регистрируются через registerRoutes(routes) — массив { key, path, parent?, title? }.
 * Match — по строгому совпадению path с поддержкой параметров `:name`.
 */

import { CoreEvents } from '../contract.js';

function _extractParams(path) {
    const matches = path.match(/:([a-zA-Z_][a-zA-Z0-9_]*)/g);
    return matches ? matches.map((m) => m.slice(1)) : [];
}

function _buildPattern(path) {
    const re = path.replace(/:([a-zA-Z_][a-zA-Z0-9_]*)/g, '([^/]+)');
    return new RegExp(`^${re}$`);
}

function _matchRoute(routes, pathRel) {
    for (const r of routes) {
        const m = pathRel.match(r._pattern);
        if (m) {
            const params = {};
            r._paramNames.forEach((name, i) => { params[name] = decodeURIComponent(m[i + 1]); });
            return { route: r, params };
        }
    }
    return null;
}

function _buildPath(route, params) {
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

export function createRouterEffect({ baseUrl, routes }) {
    if (!Array.isArray(routes) || routes.length === 0) {
        throw new Error('router.effect: non-empty routes[] required');
    }
    const base = baseUrl || '';
    const compiled = routes.map((r) => ({
        ...r,
        _paramNames: _extractParams(r.path),
        _pattern: _buildPattern(r.path),
    }));
    const publicRoutes = routes.map((r) => {
        const out = { key: r.key, path: r.path };
        if (typeof r.parent === 'string' && r.parent.length > 0) out.parent = r.parent;
        if (typeof r.titleKey === 'string' && r.titleKey.length > 0) out.titleKey = r.titleKey;
        return out;
    });

    let popstateAttached = false;
    let routesRegistered = false;

    function _emitForCurrentUrl(ctx) {
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
            { routeKey: matched.route.key, params: matched.params, pathname },
            { source: 'router' },
        );
    }

    return async function routerEffect(event, ctx) {
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
                const p = event.payload || {};
                const route = compiled.find((r) => r.key === p.routeKey);
                if (!route) {
                    throw new Error(`router.effect: unknown routeKey "${p.routeKey}"`);
                }
                const path = _buildPath(route, p.params || {});
                const fullPath = `${base}/${path}`;
                history.pushState({}, '', fullPath);
                ctx.dispatch(
                    CoreEvents.ROUTER_ROUTE_CHANGED,
                    { routeKey: route.key, params: p.params || {}, pathname: fullPath },
                    { causation_id: event.id, source: 'router' },
                );
                return;
            }

            default:
                return;
        }
    };
}
