/**
 * LinnexModelsSidebar — навигация реестра системных моделей Linnex.
 *
 * Активный маршрут берётся из `state.router.routeKey`. Переходы — через
 * `this.navigate(routeKey)`. У сервиса один экран — реестр моделей.
 */

import { html, css, type PropertyValues } from 'lit';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import { PlatformServiceSidebar } from '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-deployment-version.js';

interface LitserveNavItem {
    route: string;
    icon: string;
    label_key: string;
}

const NAV_ITEMS: LitserveNavItem[] = [
    { route: 'models', icon: 'database', label_key: 'sidebar.models' },
];

export class LinnexModelsSidebar extends PlatformElement {
    static i18nNamespace = 'litserve';

    static override styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host { display: block; height: 100%; }
            .nav-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-xl);
                cursor: pointer;
                background: transparent;
                border: 1px solid transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                transition: var(--motion-transition-interactive);
                margin-bottom: var(--space-2);
                width: 100%;
                text-align: left;
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
                box-shadow: 0 4px 16px var(--accent-subtle);
            }
            .nav-label { flex: 1; }
            platform-service-sidebar[collapsed] .nav-label { display: none; }
            platform-service-sidebar[collapsed] .nav-item {
                justify-content: center;
                padding: var(--space-3);
            }
            platform-service-sidebar[collapsed] .nav-item:hover { transform: none; }
        `,
    ];

    declare collapsed: boolean;
    declare mobileOpen: boolean;
    private _routeKeySel: SelectController<string | null>;

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
            throw new Error('litserve-sidebar: service sidebar required');
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
        const current = this._routeKeySel.value;
        if (!current && route === 'models') {
            return true;
        }
        return current === route;
    }

    private _renderNavItem(item: LitserveNavItem) {
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
                logo-src="/static/core/assets/service_logos/frontend_logo.svg"
                logo-text=${this.t('sidebar.title')}
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(event: CustomEvent<{ collapsed: boolean }>) => { this.collapsed = event.detail.collapsed; }}
                @mobile-change=${(event: CustomEvent<{ open: boolean }>) => { this.mobileOpen = event.detail.open; }}
            >
                <nav>
                    ${NAV_ITEMS.map((item) => this._renderNavItem(item))}
                </nav>
                <div slot="footer">
                    <platform-user block></platform-user>
                    <platform-deployment-version base-url="/litserve" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('litserve-sidebar', LinnexModelsSidebar);
