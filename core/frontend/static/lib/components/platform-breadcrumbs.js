import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { CoreEvents } from '../events/contract.js';
import '@platform/lib/components/platform-icon.js';

/**
 * <platform-breadcrumbs> — единый компонент хлебных крошек для всех сервисов
 * платформы (CRM, RAG, Documents и др.).
 *
 * Источник правды — slice `state.router`:
 *   - routes  — массив { key, path, parent? }, регистрируется через
 *               `ROUTER_ROUTES_REGISTERED` при создании `createRouterEffect`.
 *   - routeKey — текущий маршрут (`ROUTER_ROUTE_CHANGED`).
 *   - params   — параметры текущего маршрута.
 *
 * Подписи берутся через `this.t('routes.<routeKey>')` (резолв через
 * `defaultI18nNamespace` сервиса). Динамический хвост (имя заметки, имя
 * документа и т.д.) — через prop `currentLabel`.
 *
 * Клик по неактивной крошке диспатчит `ROUTER_NAVIGATE_REQUESTED` с params
 * текущего маршрута, если совпадает routeKey, иначе с `{}`.
 */
export class PlatformBreadcrumbs extends PlatformElement {
    static properties = {
        currentLabel: { type: String, attribute: 'current-label' },
        _separator: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .breadcrumbs {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .breadcrumb-item {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                cursor: pointer;
                transition: color var(--duration-fast);
                background: transparent;
                border: none;
                padding: 0;
                color: inherit;
                font: inherit;
            }

            .breadcrumb-item:hover {
                color: var(--text-primary);
            }

            .breadcrumb-separator {
                color: var(--text-tertiary);
            }

            .breadcrumb-current {
                color: var(--text-primary);
                font-weight: 500;
                cursor: default;
            }

            .breadcrumb-current:hover {
                color: var(--text-primary);
            }

            @media (max-width: 767px) {
                .breadcrumbs {
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    max-width: 100%;
                }

                .breadcrumb-item {
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    max-width: 200px;
                }

                .breadcrumb-current {
                    max-width: 250px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.currentLabel = '';
        this._separator = '/';
        this._routerSel = this.select((s) => ({
            routeKey: s.router.routeKey,
            params: s.router.params,
            routes: s.router.routes,
        }));
    }

    _buildChain(routes, routeKey) {
        if (!Array.isArray(routes) || routes.length === 0) return [];
        if (typeof routeKey !== 'string' || routeKey.length === 0) return [];
        const byKey = new Map();
        for (const route of routes) {
            if (route && typeof route.key === 'string' && !byKey.has(route.key)) {
                byKey.set(route.key, route);
            }
        }
        const chain = [];
        const visited = new Set();
        let cursor = byKey.get(routeKey);
        while (cursor !== undefined) {
            if (visited.has(cursor.key)) break;
            visited.add(cursor.key);
            chain.push(cursor);
            cursor = typeof cursor.parent === 'string' && cursor.parent.length > 0
                ? byKey.get(cursor.parent)
                : undefined;
        }
        return chain.reverse();
    }

    _resolveLabel(route) {
        if (typeof route.titleKey === 'string' && route.titleKey.length > 0) {
            return this.t(route.titleKey);
        }
        return this.t(`routes.${route.key}`);
    }

    _onClick(routeKey, params) {
        this.dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, {
            routeKey,
            params,
        });
    }

    render() {
        const router = this._routerSel.value;
        const chain = this._buildChain(router.routes, router.routeKey);
        const trimmedCurrent = typeof this.currentLabel === 'string' ? this.currentLabel.trim() : '';
        // Цепочка из одного узла дублирует заголовок страницы и не несёт навигации,
        // поэтому показываем крошки только когда есть хотя бы один родитель,
        // либо когда страница даёт динамический хвост через current-label.
        if (chain.length === 0) return html``;
        if (chain.length === 1 && trimmedCurrent.length === 0) return html``;

        return html`
            <nav class="breadcrumbs" aria-label="Breadcrumb">
                ${chain.map((route, index) => {
                    const isLast = index === chain.length - 1;
                    const label = isLast && trimmedCurrent.length > 0
                        ? trimmedCurrent
                        : this._resolveLabel(route);
                    const params = route.key === router.routeKey ? router.params : {};
                    return html`
                        ${isLast
                            ? html`
                                <span class="breadcrumb-item breadcrumb-current" aria-current="page">
                                    ${label}
                                </span>
                            `
                            : html`
                                <button
                                    type="button"
                                    class="breadcrumb-item"
                                    @click=${() => this._onClick(route.key, params)}
                                >
                                    ${label}
                                </button>
                            `}
                        ${index < chain.length - 1
                            ? html`<span class="breadcrumb-separator" aria-hidden="true">${this._separator}</span>`
                            : html``}
                    `;
                })}
            </nav>
        `;
    }
}

customElements.define('platform-breadcrumbs', PlatformBreadcrumbs);
