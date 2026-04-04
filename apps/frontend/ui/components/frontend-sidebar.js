/**
 * FrontendSidebar — навигация консоли; оболочка platform-service-sidebar.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { FrontendStore } from '../store/frontend.store.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';

export class FrontendSidebar extends PlatformElement {
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
                box-shadow: 0 4px 16px rgba(16, 185, 129, 0.15);
            }

            .nav-icon {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
            }

            .nav-item.active .nav-icon,
            .nav-item:hover .nav-icon {
                color: inherit;
            }

            .nav-icon platform-icon {
                display: flex;
            }

            .nav-label {
                flex: 1;
            }

            .services-section {
                padding-top: var(--space-4);
                border-top: 1px solid var(--glass-border-subtle);
                margin-top: var(--space-4);
            }

            .section-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-3);
                padding: 0 var(--space-3);
            }

            .service-link {
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
                text-decoration: none;
                width: 100%;
                text-align: left;
            }

            .service-link:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
                color: var(--text-primary);
                transform: translateX(4px);
            }

            platform-service-sidebar[collapsed] .nav-label,
            platform-service-sidebar[collapsed] .section-title,
            platform-service-sidebar[collapsed] .service-link span:not(.nav-icon) {
                display: none;
            }

            platform-service-sidebar[collapsed] .nav-item,
            platform-service-sidebar[collapsed] .service-link {
                justify-content: center;
                padding: var(--space-3);
            }

            platform-service-sidebar[collapsed] .nav-item:hover,
            platform-service-sidebar[collapsed] .service-link:hover {
                transform: none;
            }
        `
    ];

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    constructor() {
        super();
        this.collapsed = false;
        this.mobileOpen = false;

        this.state = this.use((s) => ({
            currentView: s.ui.currentView,
        }));
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this._onAuthChange = () => this.requestUpdate();
        window.addEventListener(AppEvents.AUTH_CHANGE, this._onAuthChange);
    }

    disconnectedCallback() {
        if (this._onAuthChange) {
            window.removeEventListener(AppEvents.AUTH_CHANGE, this._onAuthChange);
            this._onAuthChange = null;
        }
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    _shell() {
        return this.renderRoot?.querySelector('platform-service-sidebar');
    }

    closeMobile() {
        this._shell()?.closeMobile();
    }

    _navigate(view) {
        FrontendStore.setCurrentView(view);
        this.closeMobile();
    }

    render() {
        const { currentView } = this.state.value;
        const t = (key) => this.i18n.t(key, {});

        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/frontend_logo.svg"
                logo-text="HUMANITEC"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => {
                    this.collapsed = e.detail.collapsed;
                }}
                @mobile-change=${(e) => {
                    this.mobileOpen = e.detail.open;
                }}
            >
                <nav>
                    <button
                        class="nav-item ${currentView === 'dashboard' ? 'active' : ''}"
                        @click=${() => this._navigate('dashboard')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="chart" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">${t('console_sidebar.dashboard')}</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'team' ? 'active' : ''}"
                        @click=${() => this._navigate('team')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="user" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">${t('console_sidebar.team')}</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'api-keys' ? 'active' : ''}"
                        @click=${() => this._navigate('api-keys')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="key" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">${t('console_sidebar.api_keys')}</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'billing' ? 'active' : ''}"
                        @click=${() => this._navigate('billing')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="clipboard" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">${t('console_sidebar.billing')}</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'embed-configs' ? 'active' : ''}"
                        @click=${() => this._navigate('embed-configs')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="chat" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">${t('console_sidebar.embed')}</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'settings' ? 'active' : ''}"
                        @click=${() => this._navigate('settings')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="settings" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">${t('console_sidebar.settings')}</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'scheduler-tasks' ? 'active' : ''}"
                        @click=${() => this._navigate('scheduler-tasks')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="clock" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">${t('console_sidebar.scheduler')}</span>
                    </button>

                    ${this.auth.user?.company_id === 'system'
                        ? html`
                              <button
                                  class="nav-item ${currentView === 'lead-requests' ? 'active' : ''}"
                                  @click=${() => this._navigate('lead-requests')}
                              >
                                  <span class="nav-icon">
                                      <platform-icon name="access-request" size="18"></platform-icon>
                                  </span>
                                  <span class="nav-label">${t('console_sidebar.leads')}</span>
                              </button>
                              <button
                                  class="nav-item ${currentView === 'platform-tracing' ? 'active' : ''}"
                                  @click=${() => this._navigate('platform-tracing')}
                              >
                                  <span class="nav-icon">
                                      <platform-icon name="workflow" size="18"></platform-icon>
                                  </span>
                                  <span class="nav-label">${t('console_sidebar.tracing')}</span>
                              </button>
                          `
                        : ''}
                </nav>

                <div class="services-section" data-hide-collapsed>
                    <div class="section-title">${t('console_sidebar.docs_section')}</div>
                    <a class="service-link" href="/documentation">
                        <span class="nav-icon">
                            <platform-icon name="book-open" size="18"></platform-icon>
                        </span>
                        <span>${t('console_sidebar.docs_link')}</span>
                    </a>
                </div>

                <div slot="footer">
                    <platform-user block></platform-user>
                    <platform-deployment-version base-url="/frontend" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('frontend-sidebar', FrontendSidebar);
