/**
 * WorktrackerSidebar — навигация сервиса задач.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/platform-notification-manager.js';

const NAV_ITEMS = [
    { route: 'inbox', icon: 'inbox', label_key: 'sidebar.nav.inbox' },
    { route: 'my', icon: 'user', label_key: 'sidebar.nav.my' },
    { route: 'board', icon: 'list-check', label_key: 'sidebar.nav.board' },
    { route: 'queues', icon: 'layers', label_key: 'sidebar.nav.queues' },
];

export class WorktrackerSidebar extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host { display: block; height: 100%; }
            .nav-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                min-height: 36px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                cursor: pointer;
                background: transparent;
                border: none;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                transition: var(--motion-transition-interactive);
                margin-bottom: 2px;
                width: 100%;
                text-align: left;
            }
            .nav-item:hover {
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
            }
            .nav-item.active {
                background: var(--accent-subtle);
                color: var(--accent);
                font-weight: var(--font-semibold);
            }
            platform-service-sidebar[collapsed] .nav-label { display: none; }
            platform-service-sidebar[collapsed] .nav-item {
                justify-content: center; padding: var(--space-3);
            }
            platform-service-sidebar[collapsed] .nav-item:hover { transform: none; }
            .nav-badge {
                margin-left: auto;
                min-width: 18px;
                height: 18px;
                padding: 0 5px;
                border-radius: var(--radius-full);
                background: var(--accent);
                color: var(--text-on-accent, #fff);
                font-size: 11px;
                font-weight: var(--font-semibold);
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            platform-service-sidebar[collapsed] .nav-badge { display: none; }
        `,
    ];

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._routeKeySel = this.select((s) => s.router.routeKey);
        this._countsOp = this.useOp('platform/work_item_counts');
    }

    _shell() {
        return this.renderRoot ? this.renderRoot.querySelector('platform-service-sidebar') : null;
    }

    closeMobile() {
        const shell = this._shell();
        if (shell && typeof shell.closeMobile === 'function') {
            shell.closeMobile();
        }
    }

    _navigate(routeKey, params) {
        this.navigate(routeKey, params || {});
        this.closeMobile();
    }

    _isActive(route) {
        const current = this._routeKeySel.value;
        if (route === 'queues') {
            return current === 'queues' || current === 'queue_detail';
        }
        return current === route;
    }

    _renderNavItem(item) {
        let badge = null;
        if (item.route === 'inbox') {
            const total = this._countsOp.state.total_open_count;
            if (typeof total === 'number' && total > 0) {
                badge = html`<span class="nav-badge">${total > 99 ? '99+' : total}</span>`;
            }
        }
        return html`
            <button
                class="nav-item ${this._isActive(item.route) ? 'active' : ''}"
                @click=${() => this._navigate(item.route, {})}
            >
                <platform-icon name=${item.icon} size="18"></platform-icon>
                <span class="nav-label">${this.t(item.label_key)}</span>
                ${badge}
            </button>
        `;
    }

    render() {
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/worktracker_logo.svg"
                logo-text=${this.t('sidebar.title')}
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e) => { this.mobileOpen = e.detail.open; }}
            >
                <nav>
                    ${NAV_ITEMS.map((item) => this._renderNavItem(item))}
                </nav>
                <div slot="footer">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/worktracker" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('worktracker-sidebar', WorktrackerSidebar);
