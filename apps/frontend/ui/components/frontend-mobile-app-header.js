/**
 * frontend-mobile-app-header — мобильный заголовок консоли frontend.
 *
 * Только ширина <= 767px. Внутри `<page-header>` (бургер → сайдбар).
 * Заголовок по `state.router.routeKey` и ключам `console_sidebar.*`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/layout/page-header.js';

const ROUTE_TITLE_KEYS = {
    dashboard: 'console_sidebar.dashboard',
    team: 'console_sidebar.team',
    'api-keys': 'console_sidebar.api_keys',
    'embed-configs': 'console_sidebar.embed',
    billing: 'console_sidebar.billing',
    'scheduler-tasks': 'console_sidebar.scheduler',
    settings: 'console_sidebar.settings',
    'lead-requests': 'console_sidebar.leads',
    'platform-tracing': 'console_sidebar.tracing',
    'platform-billing': 'console_sidebar.billing_admin',
};

export class FrontendMobileAppHeader extends PlatformElement {
    static i18nNamespace = 'frontend';

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
            : 'console_sidebar.dashboard';
        return html`
            <page-header
                title=${this.t(titleKey)}
                subtitle=""
            ></page-header>
        `;
    }
}

customElements.define('frontend-mobile-app-header', FrontendMobileAppHeader);
