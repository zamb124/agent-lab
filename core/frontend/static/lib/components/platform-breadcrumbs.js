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
 * Подписи маршрутов: ключ routes.<routeKey> в defaultI18nNamespace сервиса.
 * Динамический хвост (имя заметки, имя
 * документа и т.д.) — через prop `currentLabel`.
 *
 * Вложенность внутри одного маршрута (дерево страниц wiki, папки документов)
 * не выражается маршрутами, поэтому её задаёт prop `trail` — массив
 * `{ label, routeKey, params }`. Он вставляется между цепочкой маршрутов и
 * текущей подписью, каждая крошка ведёт на свой узел.
 *
 * Клик по неактивной крошке диспатчит `ROUTER_NAVIGATE_REQUESTED` с params
 * текущего маршрута, если совпадает routeKey, иначе с `{}`.
 */
export class PlatformBreadcrumbs extends PlatformElement {
    static properties = {
        currentLabel: { type: String, attribute: 'current-label' },
        /** `{ label, routeKey, params }[]` — путь внутри текущего маршрута. */
        trail: { attribute: false },
        compact: { type: Boolean, reflect: true },
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

            :host([compact]) .breadcrumbs {
                margin-bottom: 0;
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
        this.trail = [];
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

    /** @returns {{ label: string, routeKey: string, params: object }[]} */
    _trailSegments() {
        if (!Array.isArray(this.trail)) {
            throw new Error('platform-breadcrumbs: trail must be an array');
        }
        return this.trail.map((item) => {
            if (!item || typeof item.label !== 'string' || item.label.length === 0) {
                throw new Error('platform-breadcrumbs: trail item requires non-empty label');
            }
            if (typeof item.routeKey !== 'string' || item.routeKey.length === 0) {
                throw new Error('platform-breadcrumbs: trail item requires routeKey');
            }
            if (item.params === null || typeof item.params !== 'object') {
                throw new Error('platform-breadcrumbs: trail item requires params object');
            }
            return { label: item.label, routeKey: item.routeKey, params: item.params };
        });
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
        const trail = this._trailSegments();
        // Цепочка из одного узла дублирует заголовок страницы и не несёт навигации,
        // поэтому показываем крошки только когда есть хотя бы один родитель,
        // либо когда страница даёт динамический хвост через current-label или trail.
        if (chain.length === 0) return html``;
        if (chain.length === 1 && trimmedCurrent.length === 0 && trail.length === 0) return html``;

        const routeSegments = chain.map((route) => ({
            label: this._resolveLabel(route),
            routeKey: route.key,
            params: route.key === router.routeKey ? router.params : {},
        }));
        const segments = trimmedCurrent.length > 0
            // Подпись текущей страницы занимает место последнего маршрута,
            // а путь внутри маршрута встаёт перед ней.
            ? [
                ...routeSegments.slice(0, -1),
                ...trail,
                { ...routeSegments[routeSegments.length - 1], label: trimmedCurrent },
            ]
            : [...routeSegments, ...trail];

        return html`
            <nav class="breadcrumbs" aria-label="Breadcrumb">
                ${segments.map((segment, index) => {
                    const isLast = index === segments.length - 1;
                    return html`
                        ${isLast
                            ? html`
                                <span class="breadcrumb-item breadcrumb-current" aria-current="page">
                                    ${segment.label}
                                </span>
                            `
                            : html`
                                <button
                                    type="button"
                                    class="breadcrumb-item"
                                    @click=${() => this._onClick(segment.routeKey, segment.params)}
                                >
                                    ${segment.label}
                                </button>
                            `}
                        ${isLast
                            ? html``
                            : html`<span class="breadcrumb-separator" aria-hidden="true">${this._separator}</span>`}
                    `;
                })}
            </nav>
        `;
    }
}

customElements.define('platform-breadcrumbs', PlatformBreadcrumbs);
