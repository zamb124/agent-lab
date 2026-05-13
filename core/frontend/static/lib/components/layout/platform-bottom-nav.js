/**
 * platform-bottom-nav — единая плавающая капсула первичной мобильной навигации (mobile shell 2026).
 *
 * Видим только на `max-width: 767px`. На десктопе хост `display: none`.
 *
 * Items — массив:
 *   {
 *     key:       string,        // уникальный ключ внутри nav (для key функции)
 *     routeKey:  string,        // ROUTER маршрут, открывается при tap
 *     params?:   object,        // params для navigate (опц.)
 *     sheet?:    string,        // вместо navigate открыть bottom-sheet этого kind
 *     sheetProps?: object|null, // props для bottom-sheet
 *     icon:      string,        // platform-icon name
 *     labelKey:  string,        // i18n ключ подписи (через t())
 *     badge?:    string|number, // опц. бейдж
 *   }
 *
 * Активная вкладка (для item с `routeKey`): среди маршрутов в `items` выбирается
 * **ближайший предок** текущего `state.router.routeKey` — обход от текущего ключа
 * вверх по `parent` в `state.router.routes`. Так на `/billing` активна только вкладка
 * `billing`, а не `dashboard`, хотя у маршрута в дереве родитель `dashboard`.
 * Дочерние страницы без своей вкладки подсвечивают первый совпавший предок (например
 * `platform_services` → вкладка `dashboard` в консоли).
 * Items только со `sheet` не получают активности по маршруту.
 *
 * hide-on-routes (атрибут JSON-массива routeKeys) — на этих маршрутах капсула скрыта
 * (полноэкранный редактор, OnlyOffice iframe и т.д.).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { CoreEvents } from '../../events/contract.js';
import '../platform-icon.js';

function buildParentMap(routes) {
    const byKey = new Map();
    for (const r of routes) {
        if (r && typeof r.key === 'string') byKey.set(r.key, r);
    }
    return byKey;
}

function routeAncestorKeys(routes, currentKey) {
    if (!currentKey || typeof currentKey !== 'string') return [];
    const byKey = buildParentMap(routes);
    const keys = [];
    let k = currentKey;
    const visited = new Set();
    while (k && typeof k === 'string') {
        if (visited.has(k)) return keys;
        visited.add(k);
        keys.push(k);
        const node = byKey.get(k);
        if (!node || typeof node.parent !== 'string' || node.parent.length === 0) break;
        k = node.parent;
    }
    return keys;
}

export class PlatformBottomNav extends PlatformElement {
    static properties = {
        items: { type: Array },
        hideOnRoutes: { type: Array, attribute: 'hide-on-routes' },
        _routeKey: { state: true },
        _routes: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: none;
            }

            @media (max-width: 767px) {
                :host {
                    display: block;
                    position: fixed;
                    left: max(var(--platform-bottom-nav-inset), env(safe-area-inset-left, 0px));
                    right: max(var(--platform-bottom-nav-inset), env(safe-area-inset-right, 0px));
                    bottom: calc(env(safe-area-inset-bottom, 0px) + var(--platform-bottom-nav-inset));
                    z-index: var(--platform-bottom-nav-z-index);
                    pointer-events: none;
                }

                :host([hidden]) {
                    display: none;
                }
            }

            .nav-capsule {
                pointer-events: auto;
                display: flex;
                align-items: stretch;
                justify-content: space-around;
                gap: var(--space-1);
                width: 100%;
                min-height: var(--platform-bottom-nav-height);
                padding: var(--space-2);
                box-sizing: border-box;
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                -webkit-backdrop-filter: blur(var(--glass-blur-strong));
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--platform-bottom-nav-radius);
                box-shadow: var(--glass-shadow-strong), var(--glass-inner-glow-medium);
            }

            .nav-tab {
                flex: 1 1 0;
                min-width: 0;
                min-height: var(--platform-bottom-nav-tap-target);
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 2px;
                padding: var(--space-1) var(--space-2);
                background: transparent;
                border: 1px solid transparent;
                border-radius: var(--radius-xl);
                color: var(--text-secondary);
                font-family: inherit;
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                line-height: 1.1;
                cursor: pointer;
                transition: background var(--duration-fast) var(--easing-default),
                            color var(--duration-fast) var(--easing-default),
                            border-color var(--duration-fast) var(--easing-default),
                            transform var(--duration-fast) var(--easing-default);
                -webkit-tap-highlight-color: transparent;
            }

            .nav-tab:hover {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
            }

            .nav-tab:active {
                transform: scale(0.96);
            }

            .nav-tab:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }

            .nav-tab.active {
                color: var(--accent);
                background: var(--accent-subtle);
                border-color: var(--glass-border-subtle);
            }

            .nav-tab-icon {
                position: relative;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 26px;
                height: 26px;
            }

            .nav-tab-label {
                width: 100%;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                font-size: 10px;
                letter-spacing: 0.01em;
            }

            .nav-tab-badge {
                position: absolute;
                top: -4px;
                right: -8px;
                min-width: 16px;
                height: 16px;
                padding: 0 4px;
                box-sizing: border-box;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--accent-secondary);
                color: #ffffff;
                font-size: 10px;
                font-weight: var(--font-semibold);
                line-height: 1;
                border-radius: var(--radius-full);
                box-shadow: 0 0 0 2px var(--glass-solid-strong);
            }
        `,
    ];

    constructor() {
        super();
        this.items = [];
        this.hideOnRoutes = [];
        this._routeKey = null;
        this._routes = [];
        this._routerSelect = this.select((s) => ({
            routeKey: s.router.routeKey,
            routes: s.router.routes,
        }));
    }

    /**
     * Снимок роутера нужен до render(): updated() вызывается после render(),
     * иначе активная вкладка один цикл отстаёт от state.router (Dashboard подсвечен на Team).
     */
    willUpdate(changed) {
        super.willUpdate(changed);
        const v = this._routerSelect ? this._routerSelect.value : null;
        if (v) {
            this._routeKey = v.routeKey;
            this._routes = Array.isArray(v.routes) ? v.routes : [];
        } else {
            this._routeKey = null;
            this._routes = [];
        }
    }

    updated(changed) {
        super.updated(changed);
        const hide = this._shouldHide();
        if (hide && !this.hasAttribute('hidden')) {
            this.setAttribute('hidden', '');
        } else if (!hide && this.hasAttribute('hidden')) {
            this.removeAttribute('hidden');
        }
    }

    _shouldHide() {
        if (!Array.isArray(this.items) || this.items.length === 0) return true;
        if (!Array.isArray(this.hideOnRoutes) || this.hideOnRoutes.length === 0) return false;
        const cur = this._routeKey;
        if (!cur) return false;
        return this.hideOnRoutes.includes(cur);
    }

    _computeBottomNavActiveRouteKey() {
        const cur = this._routeKey;
        if (!cur || typeof cur !== 'string' || !Array.isArray(this.items)) return null;
        const navRouteKeys = new Set();
        for (const it of this.items) {
            if (
                it
                && typeof it.routeKey === 'string'
                && it.routeKey.length > 0
                && !(typeof it.sheet === 'string' && it.sheet.length > 0)
            ) {
                navRouteKeys.add(it.routeKey);
            }
        }
        if (navRouteKeys.size === 0) return null;
        const chain = routeAncestorKeys(this._routes || [], cur);
        for (const k of chain) {
            if (navRouteKeys.has(k)) return k;
        }
        return null;
    }

    _isActive(item, activeRouteKey) {
        if (typeof item.sheet === 'string' && item.sheet.length > 0) return false;
        if (!item || typeof item.routeKey !== 'string' || item.routeKey.length === 0) return false;
        if (!activeRouteKey) return false;
        return item.routeKey === activeRouteKey;
    }

    _onTap(item) {
        if (!item || typeof item !== 'object') {
            throw new Error('platform-bottom-nav: item must be a plain object');
        }
        if (typeof item.sheet === 'string' && item.sheet.length > 0) {
            const props = item.sheetProps === undefined ? null : item.sheetProps;
            this.dispatch(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, { kind: item.sheet, props });
            return;
        }
        if (typeof item.routeKey !== 'string' || item.routeKey.length === 0) {
            throw new Error(`platform-bottom-nav: item "${item.key}" missing routeKey/sheet`);
        }
        const params = item.params && typeof item.params === 'object' ? item.params : {};
        this.dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, { routeKey: item.routeKey, params });
    }

    _renderTab(item, activeRouteKey) {
        const active = this._isActive(item, activeRouteKey);
        const label = this.t(item.labelKey);
        const badge = item.badge;
        return html`
            <button
                type="button"
                class="nav-tab ${active ? 'active' : ''}"
                role="tab"
                aria-selected=${active ? 'true' : 'false'}
                aria-label=${label}
                @click=${() => this._onTap(item)}
            >
                <span class="nav-tab-icon">
                    <platform-icon name=${item.icon} size="22"></platform-icon>
                    ${badge !== undefined && badge !== null && badge !== '' && badge !== 0
                        ? html`<span class="nav-tab-badge">${badge}</span>`
                        : ''}
                </span>
                <span class="nav-tab-label">${label}</span>
            </button>
        `;
    }

    render() {
        if (!Array.isArray(this.items) || this.items.length === 0) {
            return html``;
        }
        const activeRouteKey = this._computeBottomNavActiveRouteKey();
        return html`
            <nav class="nav-capsule" role="tablist" aria-label=${this.t('mobile_nav.aria', null, 'platform')}>
                ${this.items.map((it) => this._renderTab(it, activeRouteKey))}
            </nav>
        `;
    }
}

customElements.define('platform-bottom-nav', PlatformBottomNav);
