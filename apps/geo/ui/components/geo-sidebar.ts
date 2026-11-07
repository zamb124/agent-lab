/**
 * GeoSidebar — навигация сервиса Geo.
 *
 * Active route подсвечивается по `state.router.routeKey`. Переходы — через
 * `this.navigate(routeKey)`.
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
    { route: 'overview',  icon: 'globe',                label_key: 'sidebar.menu_overview' },
    { route: 'sources',   icon: 'layers',               label_key: 'sidebar.menu_sources' },
    { route: 'addresses', icon: 'pin',                  label_key: 'sidebar.menu_addresses' },
    { route: 'route_lab', icon: 'circular-connection',  label_key: 'sidebar.menu_route_lab' },
    { route: 'map_lab',   icon: 'pin',                  label_key: 'sidebar.menu_map_lab' },
];

export class GeoSidebar extends PlatformElement {
    static i18nNamespace = 'geo';

    private _routeKeySel: SelectController<string | null>;

    static override styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host { display: block; height: 100%; }
            .nav-item {
                display: flex; align-items: center; gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-xl);
                cursor: pointer; background: transparent;
                border: 1px solid transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm); font-weight: var(--font-medium);
                transition: var(--motion-transition-interactive);
                margin-bottom: var(--space-2);
                width: 100%; text-align: left;
            }
            .nav-item:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
                box-shadow: var(--glass-shadow-subtle);
                color: var(--text-primary);
                transform: translateX(4px);
            }
            .nav-item.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
                font-weight: var(--font-semibold);
                box-shadow: 0 4px 16px color-mix(in srgb, var(--accent) 15%, transparent);
            }
            .nav-label { flex: 1; }
            platform-service-sidebar[collapsed] .nav-label { display: none; }
            platform-service-sidebar[collapsed] .nav-item { justify-content: center; padding: var(--space-3); }
            platform-service-sidebar[collapsed] .nav-item:hover { transform: none; }
        `,
    ];

    declare collapsed: boolean;
    declare mobileOpen: boolean;

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
        const root = this.renderRoot;
        if (!root) return null;
        const shell = root.querySelector('platform-service-sidebar');
        if (shell === null) return null;
        if (!(shell instanceof PlatformServiceSidebar)) {
            throw new Error('geo-sidebar: service sidebar required');
        }
        return shell;
    }

    closeMobile() {
        this._shell()?.closeMobile();
    }

    private _navigate(routeKey: string) {
        this.navigate(routeKey);
        this.closeMobile();
    }

    private _isActive(route: string) {
        return this._routeKeySel.value === route || (route === 'overview' && this._routeKeySel.value === null);
    }

    private _renderNavItem(item: { route: string; icon: string; label_key: string }) {
        return html`
            <button
                class="nav-item ${this._isActive(item.route) ? 'active' : ''}"
                @click=${() => this._navigate(item.route)}
            >
                <platform-icon name=${item.icon} size="18"></platform-icon>
                <span class="nav-label">${this.t(item.label_key)}</span>
            </button>
        `;
    }

    override render() {
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/geo_logo.svg"
                logo-text=${this.t('sidebar.title')}
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e: CustomEvent<{ collapsed: boolean }>) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e: CustomEvent<{ open: boolean }>) => { this.mobileOpen = e.detail.open; }}
            >
                <nav>
                    ${NAV_ITEMS.map((item) => this._renderNavItem(item))}
                </nav>

                <div slot="footer">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/geo" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('geo-sidebar', GeoSidebar);
