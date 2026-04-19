/**
 * FrontendSidebar — навигация консоли через events.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';

export class FrontendSidebar extends PlatformElement {
    static styles = [
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
                transition: all var(--duration-normal) var(--easing-default);
                margin-bottom: var(--space-2); width: 100%; text-align: left;
            }
            .nav-item:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
                box-shadow: var(--glass-shadow-subtle);
                color: var(--text-primary); transform: translateX(4px);
            }
            .nav-item.active {
                background: var(--accent-subtle);
                border-color: var(--accent); color: var(--accent);
                font-weight: var(--font-semibold);
                box-shadow: 0 4px 16px rgba(153, 166, 249, 0.15);
            }
            .nav-icon {
                width: 32px; height: 32px;
                display: flex; align-items: center; justify-content: center;
                flex-shrink: 0; border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
            }
            .nav-item.active .nav-icon, .nav-item:hover .nav-icon { color: inherit; }
            .nav-icon platform-icon { display: flex; }
            .nav-label { flex: 1; }
            .services-section {
                padding-top: var(--space-4);
                border-top: 1px solid var(--glass-border-subtle);
                margin-top: var(--space-4);
            }
            .section-title {
                font-size: var(--text-xs); font-weight: var(--font-semibold);
                text-transform: uppercase; letter-spacing: 0.08em;
                color: var(--text-tertiary); margin-bottom: var(--space-3); padding: 0 var(--space-3);
            }
            .service-link {
                display: flex; align-items: center; gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-xl);
                cursor: pointer; background: transparent;
                border: 1px solid transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm); font-weight: var(--font-medium);
                transition: all var(--duration-normal) var(--easing-default);
                margin-bottom: var(--space-2); text-decoration: none; width: 100%; text-align: left;
            }
            .service-link:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
                color: var(--text-primary); transform: translateX(4px);
            }
            platform-service-sidebar[collapsed] .nav-label,
            platform-service-sidebar[collapsed] .section-title,
            platform-service-sidebar[collapsed] .service-link span:not(.nav-icon) { display: none; }
            platform-service-sidebar[collapsed] .nav-item,
            platform-service-sidebar[collapsed] .service-link { justify-content: center; padding: var(--space-3); }
            platform-service-sidebar[collapsed] .nav-item:hover,
            platform-service-sidebar[collapsed] .service-link:hover { transform: none; }
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
        this._routeKeySel = this.select((s) => s.router && s.router.routeKey);
        this._authSel = this.select((s) => s.auth.user);
    }

    _shell() { return this.renderRoot?.querySelector('platform-service-sidebar'); }
    closeMobile() { this._shell()?.closeMobile(); }

    _navigate(routeKey) {
        this.navigate(routeKey);
        this.closeMobile();
    }

    render() {
        const currentView = this._routeKeySel.value || 'dashboard';
        const user = this._authSel.value;
        const isSystem = !!user && (user.company_id === 'system' || (user.raw && user.raw.company_id === 'system'));
        const t = (k, fallback) => this.t(k) || fallback;

        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/frontend_logo.svg"
                logo-text="HUMANITEC"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e) => { this.mobileOpen = e.detail.open; }}
            >
                <nav>
                    ${this._renderNavItem('dashboard', 'chart', t('console_sidebar.dashboard', 'Dashboard'), currentView)}
                    ${this._renderNavItem('team', 'user', t('console_sidebar.team', 'Team'), currentView)}
                    ${this._renderNavItem('api-keys', 'key', t('console_sidebar.api_keys', 'API keys'), currentView)}
                    ${this._renderNavItem('embed-configs', 'chat', t('console_sidebar.embed', 'Embed widgets'), currentView)}
                    ${this._renderNavItem('billing', 'database', t('console_sidebar.billing', 'Billing'), currentView)}
                    ${this._renderNavItem('settings', 'settings', t('console_sidebar.settings', 'Settings'), currentView)}
                    ${this._renderNavItem('scheduler-tasks', 'clock', t('console_sidebar.scheduler', 'Scheduler'), currentView)}
                    ${isSystem ? html`
                        ${this._renderNavItem('lead-requests', 'access-request', t('console_sidebar.leads', 'Leads'), currentView)}
                        ${this._renderNavItem('platform-tracing', 'workflow', t('console_sidebar.tracing', 'Tracing'), currentView)}
                        ${this._renderNavItem('platform-billing', 'database', t('console_sidebar.billing_admin', 'Billing admin'), currentView)}
                    ` : ''}
                </nav>

                <div class="services-section" data-hide-collapsed>
                    <div class="section-title">${t('console_sidebar.docs_section', 'Resources')}</div>
                    ${isSystem ? html`
                        <a class="service-link" href="/litserve">
                            <span class="nav-icon"><platform-icon name="database" size="18"></platform-icon></span>
                            <span>${t('console_sidebar.litserve_service', 'LitServe')}</span>
                        </a>
                    ` : ''}
                    <a class="service-link" href="/documentation">
                        <span class="nav-icon"><platform-icon name="book-open" size="18"></platform-icon></span>
                        <span>${t('console_sidebar.docs_link', 'Documentation')}</span>
                    </a>
                </div>

                <div slot="footer">
                    <platform-user block></platform-user>
                    <platform-deployment-version base-url="/frontend" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }

    _renderNavItem(view, icon, label, currentView) {
        return html`
            <button class="nav-item ${currentView === view ? 'active' : ''}" @click=${() => this._navigate(view)}>
                <span class="nav-icon"><platform-icon name=${icon} size="18"></platform-icon></span>
                <span class="nav-label">${label}</span>
            </button>
        `;
    }
}

customElements.define('frontend-sidebar', FrontendSidebar);
