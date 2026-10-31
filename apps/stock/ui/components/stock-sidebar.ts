/**
 * StockSidebar — навигация сервиса склада.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import { PlatformServiceSidebar } from '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/platform-notification-manager.js';

const NAV_ITEMS = [
    { route: 'stock_home', icon: 'box', label_key: 'sidebar.nav.stock_home' },
    { route: 'stock_transfers', icon: 'truck', label_key: 'sidebar.nav.stock_transfers' },
    { route: 'stock_products', icon: 'tag', label_key: 'sidebar.nav.stock_products' },
    { route: 'stock_locations', icon: 'pin', label_key: 'sidebar.nav.stock_locations' },
    { route: 'stock_valuation', icon: 'chart', label_key: 'sidebar.nav.stock_valuation' },
];

export class StockSidebar extends PlatformElement {
    static i18nNamespace = 'stock';

    static override styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host { display: block; height: 100%; }
            .nav-item {
                margin-bottom: var(--space-1);
            }
            platform-service-sidebar[collapsed] .nav-label { display: none; }
            platform-service-sidebar[collapsed] .nav-item {
                justify-content: center;
                padding: var(--space-2);
            }
        `,
    ];
    declare collapsed: boolean;
    declare mobileOpen: boolean;
    private _routeKeySel: SelectController<unknown>;

    static override properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._routeKeySel = this.select((s) => s.router.routeKey);
    }

    private _shell(): PlatformServiceSidebar | null {
        if (!this.renderRoot) return null;
        const shell = this.renderRoot.querySelector('platform-service-sidebar');
        if (shell === null) return null;
        if (!(shell instanceof PlatformServiceSidebar)) {
            throw new Error('stock-sidebar: service sidebar required');
        }
        return shell;
    }

    closeMobile() {
        this._shell()?.closeMobile();
    }

    private _navigate(routeKey: string, params?: Record<string, string>) {
        this.navigate(routeKey, params === undefined ? {} : params);
        this.closeMobile();
    }

    private _isActive(route: string) {
        const current = this._routeKeySel.value;
        if (route === 'stock_transfers') {
            return current === 'stock_transfers' || current === 'stock_transfer';
        }
        return current === route;
    }

    private _renderNavItem(item: { route: string; icon: string; label_key: string }) {
        return html`
            <button
                class="nav-item ${this._isActive(item.route) ? 'active' : ''}"
                @click=${() => this._navigate(item.route, {})}
            >
                <platform-icon name=${item.icon} size="18"></platform-icon>
                <span class="nav-label">${this.t(item.label_key)}</span>
            </button>
        `;
    }

    override render() {
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/stock_logo.svg"
                logo-text=${this.t('sidebar.title')}
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e: CustomEvent<{ collapsed?: boolean }>) => { this.collapsed = e.detail.collapsed === true; }}
                @mobile-change=${(e: CustomEvent<{ open?: boolean }>) => { this.mobileOpen = e.detail.open === true; }}
            >
                <nav>
                    ${NAV_ITEMS.map((item) => this._renderNavItem(item))}
                </nav>
                <div slot="footer">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/stock" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('stock-sidebar', StockSidebar);
