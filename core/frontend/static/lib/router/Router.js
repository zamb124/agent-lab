/**
 * Router - Универсальный роутер для SPA
 * Декларативная конфигурация маршрутов с параметрами
 * Интеграция с Store для синхронизации URL и состояния
 * Генерация хлебных крошек на основе конфигурации
 */
import { html } from 'lit';

export class RouteConfig {
    constructor(config) {
        this.path = config.path;
        this.key = config.key;
        this.title = config.title;
        this.parent = config.parent;
        this.itemTitle = config.itemTitle || null;
        this.component = config.component || null;
        this.onEnter = config.onEnter || null;
        this.onLeave = config.onLeave || null;
        
        this.paramNames = this._extractParamNames(this.path);
        this.pattern = this._buildPattern(this.path);
    }
    
    _extractParamNames(path) {
        const matches = path.match(/:([a-zA-Z_][a-zA-Z0-9_]*)/g);
        return matches ? matches.map(m => m.slice(1)) : [];
    }
    
    _buildPattern(path) {
        const pattern = path.replace(/:([a-zA-Z_][a-zA-Z0-9_]*)/g, '([^/]+)');
        return new RegExp(`^${pattern}$`);
    }
    
    match(pathSegment) {
        const match = pathSegment.match(this.pattern);
        if (!match) return null;
        
        const params = {};
        this.paramNames.forEach((name, index) => {
            params[name] = match[index + 1];
        });
        
        return { params };
    }
    
    buildPath(params = {}) {
        let path = this.path;
        this.paramNames.forEach(name => {
            path = path.replace(`:${name}`, params[name] || '');
        });
        return path;
    }
}

export class Router {
    constructor(appElement, options = {}) {
        this.appElement = appElement;
        this.baseUrl = options.baseUrl || '';
        this.store = options.store || null;
        
        this.routeConfigs = new Map();
        this.currentRoute = null;
        this.currentParams = {};
        
        this._onPopState = this._onPopState.bind(this);
        this._onNavigate = this._onNavigate.bind(this);
        this._subscribers = [];
    }

    start() {
        window.addEventListener('popstate', this._onPopState);
        window.addEventListener('navigate', this._onNavigate);
        this.initFromUrl();
    }

    stop() {
        window.removeEventListener('popstate', this._onPopState);
        window.removeEventListener('navigate', this._onNavigate);
    }
    
    registerRoute(config) {
        const route = new RouteConfig(config);
        this.routeConfigs.set(route.key, route);
        return route;
    }
    
    registerRoutes(configs) {
        return configs.map(config => this.registerRoute(config));
    }
    
    getRoute(key) {
        return this.routeConfigs.get(key);
    }
    
    subscribe(callback) {
        this._subscribers.push(callback);
        return () => {
            const index = this._subscribers.indexOf(callback);
            if (index !== -1) {
                this._subscribers.splice(index, 1);
            }
        };
    }
    
    _notifySubscribers() {
        this._subscribers.forEach(callback => callback());
    }

    navigateByRoute(routeKey, params = {}, options = {}) {
        const route = this.routeConfigs.get(routeKey);
        if (!route) {
            console.error(`[Router] Unknown route: ${routeKey}`);
            return;
        }
        
        const path = route.buildPath(params);
        const fullPath = `${this.baseUrl}/${path}`;
        
        if (this.currentRoute && this.currentRoute.onLeave) {
            this.currentRoute.onLeave(this.currentParams);
        }
        
        if (!options.skipUrl) {
            history.pushState({}, '', fullPath);
        }
        
        this.currentRoute = route;
        this.currentParams = params;
        
        if (this.store && this.store.syncRoute) {
            this.store.syncRoute(routeKey, params);
        }
        
        if (route.onEnter) {
            route.onEnter(params);
        }
        
        this._notifySubscribers();
        this.appElement.requestUpdate();
    }

    _onPopState(event) {
        this.initFromUrl();
    }

    _onNavigate(event) {
        const { routeKey, params } = event.detail;
        this.navigateByRoute(routeKey, params);
    }
    
    parseCurrentUrl() {
        const pathname = window.location.pathname;
        const relativePath = pathname.startsWith(this.baseUrl)
            ? pathname.slice(this.baseUrl.length)
            : pathname;
        
        const path = relativePath.startsWith('/') ? relativePath.slice(1) : relativePath;
        const segments = path.split('/').filter(Boolean);
        
        if (segments.length === 0) {
            return { route: null, params: {} };
        }
        
        // Проверяем полный путь, а не только первый сегмент
        for (const route of this.routeConfigs.values()) {
            const match = route.match(path);
            if (match) {
                return { route, params: match.params };
            }
        }
        
        return { route: null, params: {} };
    }
    
    initFromUrl() {
        const { route, params } = this.parseCurrentUrl();
        
        if (!route) {
            const defaultRoute = this.routeConfigs.values().next().value;
            if (defaultRoute) {
                this.navigateByRoute(defaultRoute.key, {}, { skipUrl: false });
            }
            return;
        }
        
        this.currentRoute = route;
        this.currentParams = params;
        
        if (this.store && this.store.syncRoute) {
            this.store.syncRoute(route.key, params);
        }
        
        if (route.onEnter) {
            route.onEnter(params);
        }
    }
    
    buildBreadcrumbs() {
        if (!this.currentRoute) return [];
        
        const breadcrumbs = [];
        const visited = new Set();
        
        let current = this.currentRoute;
        const chain = [];
        
        while (current && !visited.has(current.key)) {
            visited.add(current.key);
            chain.unshift(current);
            current = current.parent ? this.routeConfigs.get(current.parent) : null;
        }
        
        for (const route of chain) {
            const isLast = route === this.currentRoute;
            const hasItemId = this.currentParams.itemId && route.itemTitle;
            
            breadcrumbs.push({
                key: route.key,
                label: typeof route.title === 'function'
                    ? route.title(this.currentParams)
                    : route.title,
                routeKey: route.key,
                itemId: hasItemId ? this.currentParams.itemId : null,
                clickable: !isLast || !hasItemId,
            });
            
            if (hasItemId && isLast) {
                breadcrumbs.push({
                    key: `${route.key}-item`,
                    label: route.itemTitle(this.currentParams),
                    routeKey: route.key,
                    itemId: this.currentParams.itemId,
                    clickable: false,
                });
            }
        }
        
        return breadcrumbs;
    }

    render() {
        if (this.currentRoute && this.currentRoute.component) {
            const element = document.createElement(this.currentRoute.component);
            Object.assign(element, this.currentParams);
            return element;
        }
        
        return html`<div>Unknown route</div>`;
    }
}

export function navigateTo(routeKey, params = {}) {
    window.dispatchEvent(new CustomEvent('navigate', {
        detail: { routeKey, params }
    }));
}
