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

            .namespace-selector {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                margin-bottom: var(--space-4);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                min-width: 0;
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
            }

            .namespace-selector select option {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
            }

            .namespace-add-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                height: 24px;
                border: none;
                background: var(--accent);
                color: white;
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast);
                flex-shrink: 0;
            }

            .namespace-add-btn:hover {
                background: var(--accent-hover);
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
                background: rgba(255, 149, 0, 0.15);
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
                transition: transform var(--duration-fast);
                flex-shrink: 0;
            }

            .nav-icon-wrapper.notes {
                background: linear-gradient(145deg, #FFD60A 0%, #FF9500 100%);
                color: white;
                box-shadow: 0 2px 8px rgba(255, 149, 0, 0.3);
            }

            .nav-icon-wrapper.entities {
                background: linear-gradient(145deg, #5AC8FA 0%, #007AFF 100%);
                color: white;
                box-shadow: 0 2px 8px rgba(0, 122, 255, 0.3);
            }

            .nav-icon-wrapper.graph {
                background: linear-gradient(145deg, #AF52DE 0%, #5856D6 100%);
                color: white;
                box-shadow: 0 2px 8px rgba(88, 86, 214, 0.3);
            }

            .nav-icon-wrapper.tasks {
                background: linear-gradient(145deg, #34C759 0%, #30D158 100%);
                color: white;
                box-shadow: 0 2px 8px rgba(52, 199, 89, 0.3);
            }

            .nav-icon-wrapper.calendar {
                background: linear-gradient(145deg, #FF3B30 0%, #FF453A 100%);
                color: white;
                box-shadow: 0 2px 8px rgba(255, 59, 48, 0.3);
            }

            .nav-label {
                flex: 1;
                font-size: var(--text-base);
            }

            .nav-count {
                font-size: 12px;
                font-weight: 600;
                color: var(--text-secondary);
                padding: 3px 8px;
                background: var(--glass-solid-medium);
                border-radius: var(--radius-full);
            }

            .user-section {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }

            .user-section platform-user {
                flex: 1;
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

            :host([collapsed]) .user-section {
                flex-direction: column;
                align-items: center;
            }

            :host([collapsed]) .user-section platform-user {
                flex: 0 0 auto;
                width: 100%;
                min-width: 0;
            }

            :host([collapsed]) platform-notification-manager {
                display: none;
            }

            /* Light theme */
            :host-context([data-theme="light"]) .nav-item.active {
                background: rgba(255, 149, 0, 0.12);
            }

            :host-context([data-theme="light"]) .nav-count {
                background: rgba(0, 0, 0, 0.06);
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
                <div slot="header">
                    <div class="namespace-selector" data-hide-collapsed>
                        <span class="namespace-label">Пространство</span>
                        <select @change=${this._onNamespaceChange}>
                            <option value="">Все</option>
                            ${this._namespaces.map(ns => html`
                                <option
                                    value=${ns.name}
                                    ?selected=${ns.name === this._currentNamespace}
                                >
                                    ${ns.name}
                                </option>
                            `)}
                        </select>
                        <button
                            class="namespace-add-btn"
                            @click=${this._openNamespaceModal}
                            title="Создать пространство"
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
                            <platform-icon name="doc-detail" size="18"></platform-icon>
                        </div>
                        <span class="nav-label">Заметки</span>
                        ${this._notesCount > 0 ? html`
                            <span class="nav-count">${this._notesCount}</span>
                        ` : ''}
                    </button>
                    <button
                        class="nav-item ${this._currentView === 'entities' ? 'active' : ''}"
                        @click=${() => this._navigate('entities')}
                    >
                        <div class="nav-icon-wrapper entities">
                            <platform-icon name="building-one" size="18"></platform-icon>
                        </div>
                        <span class="nav-label">Сущности</span>
                    </button>
                    <button
                        class="nav-item ${this._currentView === 'graph' ? 'active' : ''}"
                        @click=${() => this._navigate('graph')}
                    >
                        <div class="nav-icon-wrapper graph">
                            <platform-icon name="network" size="18"></platform-icon>
                        </div>
                        <span class="nav-label">Граф связей</span>
                    </button>
                </div>

                <div class="nav-section">
                    <div class="nav-title">Организация</div>
                    <button
                        class="nav-item ${this._currentView === 'tasks' ? 'active' : ''}"
                        @click=${() => this._navigate('tasks')}
                    >
                        <div class="nav-icon-wrapper tasks">
                            <platform-icon name="checklist" size="18"></platform-icon>
                        </div>
                        <span class="nav-label">Задачи</span>
                    </button>
                    <button
                        class="nav-item ${this._currentView === 'calendar' ? 'active' : ''}"
                        @click=${() => this._navigate('calendar')}
                    >
                        <div class="nav-icon-wrapper calendar">
                            <platform-icon name="calendar" size="18"></platform-icon>
                        </div>
                        <span class="nav-label">Календарь</span>
                    </button>
                </div>

                <div slot="footer" class="user-section">
                    <platform-deployment-version base-url="/crm"></platform-deployment-version>
                    <platform-user block></platform-user>
                    <platform-notification-manager></platform-notification-manager>
                </div>
            </platform-sidebar>
        `;
    }
}

customElements.define('crm-sidebar', CRMSidebar);
