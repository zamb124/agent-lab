import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { Services } from '@platform/services/index.js';

/**
 * Header для dashboard с навигацией между сервисами
 */
export class DashboardHeader extends PlatformElement {
    static properties = {
        currentPath: { type: String },
        showUserMenu: { type: Boolean }
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                position: sticky;
                top: 0;
                z-index: 100;
                background: var(--glass-bg);
                border-bottom: 1px solid var(--glass-border);
                backdrop-filter: blur(20px);
            }

            .header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 16px 32px;
                max-width: 1440px;
                margin: 0 auto;
            }

            .logo {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 24px;
                font-weight: 700;
                color: var(--landing-primary);
                text-decoration: none;
                cursor: pointer;
            }

            .main-nav {
                display: flex;
                gap: 8px;
            }

            .nav-link {
                padding: 10px 20px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                color: var(--landing-secondary);
                text-decoration: none;
                border-radius: 8px;
                transition: all 0.3s ease;
                cursor: pointer;
            }

            .nav-link:hover {
                background: rgba(255, 255, 255, 0.05);
            }

            .nav-link.active {
                background: var(--landing-primary);
                color: var(--landing-secondary);
            }

            .user-menu {
                display: flex;
                align-items: center;
                gap: 16px;
            }

            .user-button {
                padding: 10px 20px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: var(--landing-secondary);
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid var(--glass-border);
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.3s ease;
            }

            .user-button:hover {
                background: rgba(255, 255, 255, 0.1);
            }

            @media (max-width: 768px) {
                .header {
                    padding: max(12px, env(safe-area-inset-top, 0px)) 16px 12px;
                    flex-wrap: wrap;
                }

                .main-nav {
                    width: 100%;
                    order: 3;
                    margin-top: 12px;
                    overflow-x: auto;
                }

                .nav-link {
                    padding: 8px 16px;
                    font-size: 14px;
                    white-space: nowrap;
                }
            }
        `
    ];

    constructor() {
        super();
        this.currentPath = window.location.pathname;
        this.showUserMenu = false;
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('popstate', this._handleLocationChange.bind(this));
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('popstate', this._handleLocationChange.bind(this));
    }

    _handleLocationChange() {
        this.currentPath = window.location.pathname;
    }

    _isActive(path) {
        return this.currentPath.startsWith(path);
    }

    _handleNavigation(path, e) {
        e.preventDefault();
        window.location.href = path;
    }

    async _handleLogout() {
        try {
            await Services.auth.logout();
            window.location.href = '/';
        } catch (err) {
            console.error('Logout error:', err);
        }
    }

    render() {
        return html`
            <header class="header">
                <a href="/dashboard" class="logo" @click=${(e) => this._handleNavigation('/dashboard', e)}>
                    Humanitec
                </a>

                <nav class="main-nav">
                    <a 
                        href="/dashboard" 
                        class="nav-link ${this._isActive('/dashboard') ? 'active' : ''}"
                        @click=${(e) => this._handleNavigation('/dashboard', e)}
                    >
                        Dashboard
                    </a>
                    <a 
                        href="/flows" 
                        class="nav-link ${this._isActive('/flows') ? 'active' : ''}"
                        @click=${(e) => this._handleNavigation('/flows', e)}
                    >
                        Flows
                    </a>
                    <a 
                        href="/crm" 
                        class="nav-link ${this._isActive('/crm') ? 'active' : ''}"
                        @click=${(e) => this._handleNavigation('/crm', e)}
                    >
                        CRM
                    </a>
                    <a 
                        href="/billing" 
                        class="nav-link ${this._isActive('/billing') ? 'active' : ''}"
                        @click=${(e) => this._handleNavigation('/billing', e)}
                    >
                        Биллинг
                    </a>
                </nav>

                <div class="user-menu">
                    <company-switcher></company-switcher>
                    <button class="user-button" @click=${this._handleLogout}>
                        Выйти
                    </button>
                </div>
            </header>
        `;
    }
}

customElements.define('dashboard-header', DashboardHeader);

