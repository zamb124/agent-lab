/**
 * RAG Sidebar - боковая навигационная панель
 * Использует platform-sidebar с collapsed/mobile режимами
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { RagStore } from '../store/rag.store.js';
import '@platform/lib/components/layout/platform-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';

export class RagSidebar extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        buttonStyles,
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

            .nav-label {
                flex: 1;
            }

            .provider-section {
                margin-top: auto;
                padding-top: var(--space-4);
                border-top: 1px solid var(--glass-border-subtle);
                position: relative;
                z-index: var(--z-dropdown);
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

            .provider-card {
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(var(--glass-blur-medium));
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: var(--glass-shadow-subtle);
                margin-bottom: var(--space-3);
                position: relative;
                cursor: pointer;
                transition: all var(--duration-fast);
                z-index: 1;
            }

            .provider-card.open {
                z-index: var(--z-dropdown);
            }

            .provider-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
            }

            .provider-dropdown {
                position: absolute;
                top: calc(100% + 4px);
                left: 0;
                right: 0;
                background: var(--glass-solid-strong);
                backdrop-filter: blur(var(--glass-blur-strong));
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                padding: var(--space-2);
                box-shadow: var(--glass-shadow-strong);
                z-index: var(--z-modal);
            }

            .provider-option {
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast);
                display: flex;
                align-items: center;
                justify-content: space-between;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }

            .provider-option:hover {
                background: var(--glass-solid-medium);
            }

            .provider-option.active {
                background: var(--accent-subtle);
                color: var(--accent);
            }

            .provider-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-2);
            }

            .provider-name {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .status-indicator {
                width: 8px;
                height: 8px;
                border-radius: var(--radius-full);
                background: var(--success);
                box-shadow: 0 0 8px var(--success);
            }

            .usage {
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(var(--glass-blur-medium));
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                position: relative;
                z-index: 1;
            }

            .usage-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-bottom: var(--space-2);
                color: var(--text-secondary);
            }

            .usage-item:last-child {
                margin-bottom: 0;
            }

            /* Collapsed mode */
            :host([collapsed]) .nav-label,
            :host([collapsed]) .section-title,
            :host([collapsed]) .provider-section {
                display: none;
            }

            :host([collapsed]) .nav-item {
                justify-content: center;
                padding: var(--space-3);
            }

            :host([collapsed]) .nav-item:hover {
                transform: none;
            }
        `
    ];

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
        _providerDropdownOpen: { state: true },
    };

    constructor() {
        super();
        this.collapsed = false;
        this.mobileOpen = false;
        this._providerDropdownOpen = false;

        this.state = this.use(s => ({
            currentView: s.ui.currentView,
            usage: s.usage,
            currentProvider: s.providers.current,
            providers: s.providers.list,
        }));
    }

    connectedCallback() {
        super.connectedCallback();
        const ragApi = this.services.get('ragApi');

        if (ragApi) {
            RagStore.loadProviders(ragApi).catch(err => {
                console.error('[RagSidebar] Failed to load providers:', err);
            });
        }

        document.addEventListener('click', this._handleClickOutside);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._handleClickOutside);
    }

    _handleClickOutside = (e) => {
        if (!this.shadowRoot.contains(e.target)) {
            this._providerDropdownOpen = false;
        }
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
            window.dispatchEvent(new CustomEvent('platform-sidebar-mobile-change', {
                detail: { open: false },
            }));
        }
    }

    _toggleProviderDropdown(e) {
        e?.stopPropagation();
        this._providerDropdownOpen = !this._providerDropdownOpen;
    }

    async _selectProvider(providerName, e) {
        e?.stopPropagation();
        const ragApi = this.services.get('ragApi');

        await RagStore.switchProvider(ragApi, providerName);
        this._providerDropdownOpen = false;
    }

    _navigate(view) {
        RagStore.setCurrentView(view);
        this.closeMobile();
    }

    render() {
        const { currentView, usage, currentProvider, providers } = this.state.value;

        return html`
            <platform-sidebar
                logo-src="/static/core/assets/service_logos/rag_logo.svg"
                logo-text="RAG Service"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => this.collapsed = e.detail.collapsed}
                @mobile-change=${(e) => this.mobileOpen = e.detail.open}
            >
                <nav>
                    <button
                        class="nav-item ${currentView === 'namespaces' ? 'active' : ''}"
                        @click=${() => this._navigate('namespaces')}
                    >
                        <platform-icon name="folder" size="18"></platform-icon>
                        <span class="nav-label">Namespaces</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'search' ? 'active' : ''}"
                        @click=${() => this._navigate('search')}
                    >
                        <platform-icon name="eye" size="18"></platform-icon>
                        <span class="nav-label">Search</span>
                    </button>

                    <button
                        class="nav-item ${currentView === 'settings' ? 'active' : ''}"
                        @click=${() => this._navigate('settings')}
                    >
                        <platform-icon name="settings" size="18"></platform-icon>
                        <span class="nav-label">Settings</span>
                    </button>
                </nav>

                <div class="provider-section" data-hide-collapsed>
                    <div class="section-title">Provider</div>
                    <div
                        class="provider-card ${this._providerDropdownOpen ? 'open' : ''}"
                        @click=${(e) => this._toggleProviderDropdown(e)}
                    >
                        <div class="provider-header">
                            <span class="provider-name">
                                <span class="status-indicator"></span>
                                ${currentProvider}
                            </span>
                            <platform-icon name="collapse" size="14"></platform-icon>
                        </div>

                        ${this._providerDropdownOpen && providers.length > 0 ? html`
                            <div class="provider-dropdown" @click=${(e) => e.stopPropagation()}>
                                ${providers.map(provider => html`
                                    <div
                                        class="provider-option ${provider.name === currentProvider ? 'active' : ''}"
                                        @click=${(e) => this._selectProvider(provider.name, e)}
                                    >
                                        <span>${provider.name}</span>
                                        ${provider.name === currentProvider ? html`
                                            <platform-icon name="check" size="14"></platform-icon>
                                        ` : ''}
                                    </div>
                                `)}
                            </div>
                        ` : this._providerDropdownOpen ? html`
                            <div class="provider-dropdown" @click=${(e) => e.stopPropagation()}>
                                <div style="padding: var(--space-3); text-align: center; color: var(--text-tertiary);">
                                    Loading providers...
                                </div>
                            </div>
                        ` : ''}
                    </div>

                    <div class="usage">
                        <div class="usage-item">
                            <platform-icon name="file" size="14"></platform-icon>
                            <span>Pages: ${usage.pages} / ${usage.maxPages}</span>
                        </div>
                        <div class="usage-item">
                            <platform-icon name="eye" size="14"></platform-icon>
                            <span>Retrievals: ${usage.retrievals} / ${usage.maxRetrievals}</span>
                        </div>
                    </div>
                </div>

                <div slot="footer">
                    <platform-user block></platform-user>
                </div>
            </platform-sidebar>
        `;
    }
}

customElements.define('rag-sidebar', RagSidebar);
