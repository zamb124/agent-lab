/**
 * FrontendSidebar - боковая навигационная панель
 * Использует platform-sidebar с collapsed/mobile режимами
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { FrontendStore } from '../store/frontend.store.js';
import '@platform/lib/components/layout/platform-sidebar.js';
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

            /* Collapsed mode */
            :host([collapsed]) .nav-label,
            :host([collapsed]) .section-title,
            :host([collapsed]) .service-link span:not(.nav-icon) {
                display: none;
            }

            :host([collapsed]) .nav-item,
            :host([collapsed]) .service-link {
                justify-content: center;
                padding: var(--space-3);
            }

            :host([collapsed]) .nav-item:hover,
            :host([collapsed]) .service-link:hover {
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

    toggleCollapse() {
        this.collapsed = !this.collapsed;
        this.emit('collapse-change', { collapsed: this.collapsed });
    }

    toggleMobile() {
        this.mobileOpen = !this.mobileOpen;
        this.emit('mobile-change', { open: this.mobileOpen });
    }

    closeMobile() {
        if (this.mobileOpen) {
            this.mobileOpen = false;
            this.emit('mobile-change', { open: false });
            // Глобальное событие для platform-sidebar-trigger и platform-island
            window.dispatchEvent(new CustomEvent('platform-sidebar-mobile-change', {
                detail: { open: false },
            }));
        }
    }

    _navigate(view) {
        FrontendStore.setCurrentView(view);
        this.closeMobile();
    }

    render() {
        const { currentView } = this.state.value;

        return html`
            <platform-sidebar
                logo-src="/static/core/assets/service_logos/frontend_logo.svg"
                logo-text="HUMANITEC"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => this.collapsed = e.detail.collapsed}
                @mobile-change=${(e) => this.mobileOpen = e.detail.open}
            >
                <nav>
                    <button
                        class="nav-item ${currentView === 'dashboard' ? 'active' : ''}"
                        @click=${() => this._navigate('dashboard')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="chart" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">Dashboard</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'team' ? 'active' : ''}"
                        @click=${() => this._navigate('team')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="user" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">Команда</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'api-keys' ? 'active' : ''}"
                        @click=${() => this._navigate('api-keys')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="key" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">API Ключи</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'billing' ? 'active' : ''}"
                        @click=${() => this._navigate('billing')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="clipboard" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">Биллинг</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'embed-configs' ? 'active' : ''}"
                        @click=${() => this._navigate('embed-configs')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="chat" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">Embed Виджеты</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'settings' ? 'active' : ''}"
                        @click=${() => this._navigate('settings')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="settings" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">Настройки</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'scheduler-tasks' ? 'active' : ''}"
                        @click=${() => this._navigate('scheduler-tasks')}
                    >
                        <span class="nav-icon">
                            <platform-icon name="clock" size="18"></platform-icon>
                        </span>
                        <span class="nav-label">Scheduler</span>
                    </button>
                </nav>

                <div class="services-section" data-hide-collapsed>
                    <div class="section-title">Документация</div>
                    <a class="service-link" href="/documentation">
                        <span class="nav-icon">
                            <platform-icon name="book-open" size="18"></platform-icon>
                        </span>
                        <span>Humanitec Docs</span>
                    </a>
                </div>

                <div slot="footer">
                    <platform-user block></platform-user>
                    <platform-deployment-version base-url="/frontend" footer></platform-deployment-version>
                </div>
            </platform-sidebar>
        `;
    }
}

customElements.define('frontend-sidebar', FrontendSidebar);
