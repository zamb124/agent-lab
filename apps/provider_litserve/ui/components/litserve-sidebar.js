import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import { LitserveStore } from '../store/litserve.store.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-deployment-version.js';

export class LitserveSidebar extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host {
                display: block;
                height: 100%;
            }

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
                transition: all var(--duration-normal) var(--easing-default);
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
                box-shadow: 0 4px 16px rgba(153, 166, 249, 0.15);
            }

            .nav-label {
                flex: 1;
            }

            platform-service-sidebar[collapsed] .nav-label {
                display: none;
            }

            platform-service-sidebar[collapsed] .nav-item {
                justify-content: center;
                padding: var(--space-3);
            }

            platform-service-sidebar[collapsed] .nav-item:hover {
                transform: none;
            }
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
        this.state = this.use((state) => ({
            currentView: state.ui.currentView,
        }));
    }

    _shell() {
        return this.renderRoot?.querySelector('platform-service-sidebar');
    }

    closeMobile() {
        this._shell()?.closeMobile();
    }

    _navigate(view) {
        LitserveStore.setCurrentView(view);
        this.closeMobile();
    }

    render() {
        const { currentView } = this.state.value;
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/frontend_logo.svg"
                logo-text="Humanitec Models"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(event) => {
                    this.collapsed = event.detail.collapsed;
                }}
                @mobile-change=${(event) => {
                    this.mobileOpen = event.detail.open;
                }}
            >
                <nav>
                    <button
                        class="nav-item ${currentView === 'models' ? 'active' : ''}"
                        @click=${() => this._navigate('models')}
                    >
                        <platform-icon name="database" size="18"></platform-icon>
                        <span class="nav-label">${this.i18n.t('sidebar.models')}</span>
                    </button>
                </nav>
                <div slot="footer">
                    <platform-user block></platform-user>
                    <platform-deployment-version base-url="/litserve" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('litserve-sidebar', LitserveSidebar);
