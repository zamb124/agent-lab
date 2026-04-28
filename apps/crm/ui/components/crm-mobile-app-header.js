/**
 * crm-mobile-app-header — мобильный заголовок CRM поверх контента.
 *
 * Используется только на ширине <= 767px. Внутри — `<page-header>` (core),
 * который сам диспатчит `CoreEvents.UI_SIDEBAR_OPEN_REQUESTED` по бургеру
 * и слушает `state.ui.sidebar.mobileOpen`. Заголовок берём по
 * `state.router.routeKey`; при фильтрах в query (`entity_type` / `entity_subtype`)
 * добавляется суффикс к заголовку.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CoreEvents } from '@platform/lib/events/index.js';
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
        this._onPopState = () => this.requestUpdate();
        this._routeKeySel = this.select((s) => s.router.routeKey);
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined') {
            window.addEventListener('popstate', this._onPopState);
        }
        this.useEvent(CoreEvents.ROUTER_ROUTE_CHANGED, () => this.requestUpdate());
    }

    disconnectedCallback() {
        if (typeof window !== 'undefined') {
            window.removeEventListener('popstate', this._onPopState);
        }
        super.disconnectedCallback();
    }

    /**
     * @param {string} routeKey
     * @returns {string}
     */
    _routeSearchSuffix(routeKey) {
        if (typeof window === 'undefined') {
            return '';
        }
        const sp = new URLSearchParams(window.location.search);
        const es = sp.get('entity_subtype');
        const et = sp.get('entity_type');
        if (routeKey === 'notes') {
            if (es !== null && es.length > 0) {
                return es;
            }
            return '';
        }
        if (routeKey === 'tasks') {
            if (es !== null && es.length > 0) {
                return es;
            }
            return '';
        }
        if (routeKey === 'entities') {
            if (et !== null && et.length > 0) {
                if (es !== null && es.length > 0) {
                    return `${et}/${es}`;
                }
                return et;
            }
            return '';
        }
        return '';
    }

    render() {
        const routeKey = this._routeKeySel.value;
        const titleKey = typeof routeKey === 'string' && ROUTE_TITLE_KEYS[routeKey] !== undefined
            ? ROUTE_TITLE_KEYS[routeKey]
            : 'sidebar.nav.notes';
        const baseTitle = this.t(titleKey);
        const suffix = typeof routeKey === 'string' ? this._routeSearchSuffix(routeKey) : '';
        const title = suffix.length > 0 ? `${baseTitle} · ${suffix}` : baseTitle;
        return html`
            <page-header
                title=${title}
                subtitle=""
            ></page-header>
        `;
    }
}

customElements.define('crm-mobile-app-header', CRMMobileAppHeader);
