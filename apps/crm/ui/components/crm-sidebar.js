/**
 * CRM Sidebar - Навигация в стиле Apple Notes
 * Использует platform-sidebar с collapsed/mobile режимами
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/layout/platform-sidebar.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-notification-manager.js';

export class CRMSidebar extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host {
                display: block;
                height: 100%;
            }

            platform-sidebar {
                --sidebar-logo-text-weight: 700;
                --sidebar-logo-text-gradient: var(--crm-main-gradient);
                --sidebar-logo-text-clip: text;
                --sidebar-logo-text-fill: transparent;
            }

            .crm-sidebar-header-slot {
                display: block;
                width: 100%;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
            }

            .namespace-selector {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                margin-bottom: var(--space-4);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                width: 100%;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
                flex-shrink: 0;
            }

            .namespace-label {
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-tertiary);
                white-space: nowrap;
                flex-shrink: 0;
            }

            .namespace-selector select {
                flex: 1;
                min-width: 0;
                background: transparent;
                border: none;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                outline: none;
                padding: var(--space-1) var(--space-2);
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .namespace-selector select option {
                background: var(--crm-surface-elevated);
                color: var(--text-primary);
            }

            .namespace-add-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                border: none;
                background: var(--crm-button-primary-bg);
                color: var(--text-inverse);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast);
                flex-shrink: 0;
            }

            .namespace-add-btn:hover {
                background: var(--crm-button-primary-hover);
                transform: scale(1.05);
            }

            .nav-section {
                margin-bottom: var(--space-6);
            }

            .nav-title {
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-3);
                padding: 0 var(--space-3);
            }

            .nav-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                margin-bottom: var(--space-1);
                background: transparent;
                border: none;
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-base);
                font-weight: 500;
                cursor: pointer;
                transition: all var(--duration-fast);
                width: 100%;
                text-align: left;
            }

            .nav-item:hover {
                background: var(--glass-solid-subtle);
            }

            .nav-item.active {
                background: var(--crm-selected-bg);
                border: 1px solid var(--crm-selected-stroke);
                color: var(--crm-selected-text);
            }

            .nav-item.active .nav-icon-wrapper {
                transform: scale(1.05);
            }

            .nav-icon-wrapper {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                color: var(--text-secondary);
                transition: transform var(--duration-fast);
                flex-shrink: 0;
            }

            .nav-item.active .nav-icon-wrapper {
                border-color: var(--crm-selected-stroke);
                color: var(--crm-selected-text);
                background: var(--crm-selected-bg);
            }

            .nav-label {
                flex: 1;
                font-size: var(--text-base);
            }

            .nav-count {
                font-size: 12px;
                font-weight: 600;
                color: var(--text-secondary);
                padding: var(--space-1) var(--space-2);
                background: var(--crm-surface-tint-strong);
                border-radius: var(--radius-full);
            }

            .user-section {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: var(--space-2);
                width: 100%;
                min-width: 0;
            }

            .user-section-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                min-width: 0;
            }

            .user-section-row platform-user {
                flex: 1;
                min-width: 0;
            }

            /* Collapsed mode */
            :host([collapsed]) .namespace-selector,
            :host([collapsed]) .nav-label,
            :host([collapsed]) .nav-count,
            :host([collapsed]) .nav-title {
                display: none;
            }

            :host([collapsed]) .nav-item {
                justify-content: center;
                padding: var(--space-3);
            }

            :host([collapsed]) .user-section-row {
                flex-direction: column;
                align-items: center;
            }

            :host([collapsed]) .user-section-row platform-user {
                flex: 0 0 auto;
                width: 100%;
                min-width: 0;
            }

            /* Light theme */
            :host-context([data-theme="light"]) .nav-item.active {
                background: var(--crm-selected-bg);
            }

            :host-context([data-theme="light"]) .nav-count {
                background: var(--crm-surface-tint-strong);
            }
        `
    ];

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
        _currentView: { state: true },
        _notesCount: { state: true },
        _namespaces: { state: true },
        _currentNamespace: { state: true },
    };

    constructor() {
        super();
        this.collapsed = false;
        this.mobileOpen = false;
        this._currentView = 'notes';
        this._notesCount = 0;
        this._namespaces = [];
        this._currentNamespace = null;

        this._unsubscribe = CRMStore.subscribe(state => {
            this._currentView = state.ui.currentView;
            this._notesCount = state.entities.notes?.length || 0;
            this._namespaces = state.namespaces.list || [];
            this._currentNamespace = state.namespaces.current;
        });
    }

    async connectedCallback() {
        super.connectedCallback();
        await this._loadNamespaces();
    }

    async _loadNamespaces() {
        const crmApi = this.services.get('crmApi');
        if (!crmApi) return;

        await CRMStore.loadNamespaces(crmApi);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
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

    _navigate(view) {
        CRMStore.setCurrentView(view);
        this.closeMobile();
    }

    _onNamespaceChange(e) {
        const namespaceName = e.target.value;
        const namespace = namespaceName
            ? this._namespaces.find(ns => ns.name === namespaceName)
            : null;

        CRMStore.setCurrentNamespace(namespace);
        this.emit('namespace-changed', { namespace });
    }

    _openNamespaceModal() {
        this.emit('open-namespace-modal');
    }

    _getCurrentNamespaceName() {
        if (!this._currentNamespace) {
            return '';
        }
        if (typeof this._currentNamespace === 'string') {
            return this._currentNamespace;
        }
        if (typeof this._currentNamespace === 'object' && typeof this._currentNamespace.name === 'string') {
            return this._currentNamespace.name;
        }
        throw new Error('Invalid namespace in sidebar state');
    }

    render() {
        return html`
            <platform-sidebar
                logo-src="/crm/ui/static/assets/icons/networkle_logo.svg"
                logo-text="NetWorkle"
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => this.collapsed = e.detail.collapsed}
                @mobile-change=${(e) => this.mobileOpen = e.detail.open}
            >
                <div slot="header" class="crm-sidebar-header-slot">
                    <div class="namespace-selector" data-hide-collapsed>
                        <span class="namespace-label">${this.i18n.t('app_shell.sidebar.namespace')}</span>
                        <select @change=${this._onNamespaceChange}>
                            <option value="">${this.i18n.t('filters.all')}</option>
                            ${this._namespaces.map(ns => html`
                                <option
                                    value=${ns.name}
                                    ?selected=${ns.name === this._getCurrentNamespaceName()}
                                >
                                    ${ns.name}
                                </option>
                            `)}
                        </select>
                        <button
                            class="namespace-add-btn"
                            @click=${this._openNamespaceModal}
                            title=${this.i18n.t('app_shell.sidebar.create_space')}
                        >
                            <platform-icon name="plus" size="14"></platform-icon>
                        </button>
                    </div>
                </div>

                <div class="nav-section">
                    <button
                        class="nav-item ${this._currentView === 'notes' ? 'active' : ''}"
                        @click=${() => this._navigate('notes')}
                    >
                        <div class="nav-icon-wrapper notes">
                            <platform-icon name="list" size="18"></platform-icon>
                        </div>
                        <span class="nav-label">${this.i18n.t('nav.notes')}</span>
                        ${this._notesCount > 0 ? html`
                            <span class="nav-count">${this._notesCount}</span>
                        ` : ''}
                    </button>
                    <button
                        class="nav-item ${this._currentView === 'entities' ? 'active' : ''}"
                        @click=${() => this._navigate('entities')}
                    >
                        <div class="nav-icon-wrapper entities">
                            <platform-icon name="database" size="18"></platform-icon>
                        </div>
                        <span class="nav-label">${this.i18n.t('nav.entities')}</span>
                    </button>
                    <button
                        class="nav-item ${this._currentView === 'graph' ? 'active' : ''}"
                        @click=${() => this._navigate('graph')}
                    >
                        <div class="nav-icon-wrapper graph">
                            <platform-icon name="share" size="18"></platform-icon>
                        </div>
                        <span class="nav-label">${this.i18n.t('pages.graph')}</span>
                    </button>
                </div>

                <div class="nav-section">
                    <div class="nav-title">${this.i18n.t('app_shell.sidebar.org_section')}</div>
                    <button
                        class="nav-item ${this._currentView === 'tasks' ? 'active' : ''}"
                        @click=${() => this._navigate('tasks')}
                    >
                        <div class="nav-icon-wrapper tasks">
                            <platform-icon name="check" size="18"></platform-icon>
                        </div>
                        <span class="nav-label">${this.i18n.t('nav.tasks')}</span>
                    </button>
                    <button
                        class="nav-item ${['settings', 'templates', 'spaces'].includes(this._currentView) ? 'active' : ''}"
                        @click=${() => this._navigate('settings')}
                    >
                        <div class="nav-icon-wrapper settings">
                            <platform-icon name="settings" size="18"></platform-icon>
                        </div>
                        <span class="nav-label">${this.i18n.t('nav.settings')}</span>
                    </button>
                </div>

                <div slot="footer" class="user-section">
                    <div class="user-section-row">
                        <platform-user block>
                            <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                        </platform-user>
                    </div>
                    <platform-deployment-version base-url="/crm" footer></platform-deployment-version>
                </div>
            </platform-sidebar>
        `;
    }
}

customElements.define('crm-sidebar', CRMSidebar);
