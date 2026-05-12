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
 * Активная вкладка определяется по state.router.routeKey:
 *   - точное совпадение routeKey, ИЛИ
 *   - текущий route — потомок item.routeKey в parent-цепочке state.router.routes.
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

function isRouteDescendantOf(routes, currentKey, ancestorKey) {
    if (!currentKey || !ancestorKey) return false;
    if (currentKey === ancestorKey) return true;
    const byKey = buildParentMap(routes);
    let cursor = byKey.get(currentKey);
    const visited = new Set();
    while (cursor) {
        if (visited.has(cursor.key)) return false;
        visited.add(cursor.key);
        if (cursor.key === ancestorKey) return true;
        const parent = typeof cursor.parent === 'string' && cursor.parent.length > 0
            ? byKey.get(cursor.parent)
            : null;
        cursor = parent;
    }
    return false;
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

    updated(changed) {
        super.updated && super.updated(changed);
        const v = this._routerSelect ? this._routerSelect.value : null;
        if (v) {
            this._routeKey = v.routeKey;
            this._routes = Array.isArray(v.routes) ? v.routes : [];
        }
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

    _isActive(item) {
        if (!this._routeKey) return false;
        if (!item || typeof item.routeKey !== 'string' || item.routeKey.length === 0) return false;
        return isRouteDescendantOf(this._routes || [], this._routeKey, item.routeKey);
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

    _renderTab(item) {
        const active = this._isActive(item);
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
        return html`
            <nav class="nav-capsule" role="tablist" aria-label=${this.t('mobile_nav.aria', null, 'platform')}>
                ${this.items.map((it) => this._renderTab(it))}
            </nav>
        `;
    }
}

customElements.define('platform-bottom-nav', PlatformBottomNav);
