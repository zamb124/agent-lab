/**
 * crm-mobile-app-header — мобильный заголовок CRM поверх контента.
 *
 * Используется только на ширине <= 767px. Внутри — `<page-header>` (core),
 * который сам диспатчит `CoreEvents.UI_SIDEBAR_OPEN_REQUESTED` по бургеру
 * и слушает `state.ui.sidebar.mobileOpen`. Заголовок берём по
 * `state.router.routeKey`.
 *
 * На desktop компонент скрывается (display: none), потому что у каждого
 * сервиса свой layout с собственной шапкой/боковой панелью.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/layout/page-header.js';

const ROUTE_TITLE_KEYS = {
    notes: 'sidebar.nav.notes',
    note: 'sidebar.nav.notes',
    entities: 'sidebar.nav.entities',
    entity: 'sidebar.nav.entities',
    graph: 'sidebar.nav.graph',
    tasks: 'sidebar.nav.tasks',
    access_requests: 'sidebar.nav.access_requests',
    settings: 'sidebar.nav.settings',
    spaces: 'sidebar.nav.namespaces',
    templates: 'sidebar.nav.settings',
    namespace_imports: 'sidebar.nav.ai_analysis',
    relationship_types: 'sidebar.nav.settings',
};

export class CRMMobileAppHeader extends PlatformElement {
    static i18nNamespace = 'crm';

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: none;
            }
            @media (max-width: 767px) {
                :host {
                    display: block;
                    flex-shrink: 0;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._routeKeySel = this.select((s) => s.router.routeKey);
    }

    render() {
        const routeKey = this._routeKeySel.value;
        const titleKey = typeof routeKey === 'string' && ROUTE_TITLE_KEYS[routeKey] !== undefined
            ? ROUTE_TITLE_KEYS[routeKey]
            : 'sidebar.nav.notes';
        return html`
            <page-header
                title=${this.t(titleKey)}
                subtitle=""
            ></page-header>
        `;
    }
}

customElements.define('crm-mobile-app-header', CRMMobileAppHeader);
