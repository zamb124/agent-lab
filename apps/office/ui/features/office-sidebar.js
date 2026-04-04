/**
 * Боковая панель «Документы»: навигация, действия, collapsed как CRM.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { OfficeStore } from '../store/office.store.js';
import {
    getPlatformNamespaceSidebarSelection,
    setPlatformNamespaceSelection,
} from '@platform/lib/utils/platform-namespace.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';

export class OfficeSidebar extends PlatformElement {
    static properties = {
        activeView: { type: String },
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
        _integrationOk: { state: true },
        _loading: { state: true },
    };

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

            platform-service-sidebar {
                --sidebar-logo-text-weight: 700;
                --sidebar-logo-text-gradient: var(--documents-title-gradient);
                --sidebar-logo-text-clip: text;
                --sidebar-logo-text-fill: transparent;
            }

            .office-sidebar-footer {
                display: flex;
                flex-direction: column;
                align-items: stretch;
                gap: 6px;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
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
                box-shadow: none;
            }

            .nav-item:hover {
                background: var(--glass-solid-subtle);
                border-color: transparent;
                color: var(--text-primary);
                transform: none;
            }

            .nav-item.active {
                background: var(--documents-selected-bg);
                border: 1px solid var(--documents-selected-stroke);
                color: var(--documents-selected-text);
                font-weight: 500;
                box-shadow: none;
            }

            .nav-item > platform-icon:first-child {
                flex-shrink: 0;
                margin: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
            }

            .nav-item.active > platform-icon:first-child,
            .nav-item:hover > platform-icon:first-child {
                color: inherit;
            }

            .nav-label {
                flex: 1;
                font-size: var(--text-base);
                font-weight: 500;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            platform-service-sidebar[collapsed] .nav-label {
                display: none;
            }

            platform-service-sidebar[collapsed] .nav-item {
                justify-content: center;
                padding: var(--space-3);
            }

            :host-context([data-theme="light"]) .nav-item.active {
                background: var(--documents-selected-bg);
            }

            .office-sidebar-header-slot {
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

            .namespace-selector select:disabled {
                opacity: 0.55;
                cursor: not-allowed;
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

            platform-service-sidebar[collapsed] .namespace-selector,
            platform-service-sidebar[collapsed] .namespace-label {
                display: none;
            }
        `,
    ];

    constructor() {
        super();
        this.activeView = 'list';
        this.collapsed = false;
        this.mobileOpen = false;
        this._integrationOk = true;
        this._loading = true;
        this._unsub = null;
        /** @type {{ name: string, is_default?: boolean }[]} */
        this._namespaceRows = [];
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsub = OfficeStore.subscribe(() => this._syncFromStore());
        this._syncFromStore();
        window.addEventListener(AppEvents.AUTH_CHANGE, this._boundAuthChange);
        window.addEventListener('office-sidebar-reload-namespaces', this._boundReloadNamespaces);
        queueMicrotask(() => void this._loadNamespaces());
    }

    disconnectedCallback() {
        this._unsub?.();
        window.removeEventListener(AppEvents.AUTH_CHANGE, this._boundAuthChange);
        window.removeEventListener('office-sidebar-reload-namespaces', this._boundReloadNamespaces);
        super.disconnectedCallback();
    }

    _boundAuthChange = () => {
        void this._loadNamespaces();
    };

    _boundReloadNamespaces = () => {
        void this._loadNamespaces();
    };

    _companyId() {
        const u = this.services?.auth?.user;
        return typeof u?.company_id === 'string' ? u.company_id.trim() : '';
    }

    async _loadNamespaces() {
        const api = this.services?.officeApi;
        if (!api) {
            return;
        }
        try {
            const res = await api.listNamespaces();
            const raw = res?.namespaces;
            this._namespaceRows = Array.isArray(raw) ? raw : [];
        } catch {
            this._namespaceRows = [];
        }
        const cid = this._companyId();
        if (cid && this._namespaceRows.length > 0) {
            const sel = getPlatformNamespaceSidebarSelection(cid);
            if (sel !== 'all' && !this._namespaceRows.some((r) => r.name === sel)) {
                setPlatformNamespaceSelection(cid, '');
            }
        }
        this.requestUpdate();
    }

    _onNamespaceChange(e) {
        const el = e.target;
        if (!(el instanceof HTMLSelectElement)) {
            return;
        }
        const cid = this._companyId();
        if (!cid) {
            return;
        }
        setPlatformNamespaceSelection(cid, el.value.trim());
        OfficeStore.setActiveCatalogId('');
        OfficeStore.setFilterCatalogIds([]);
    }

    _openNamespaceModal() {
        this.emit('open-namespace-modal');
    }

    _syncFromStore() {
        const s = OfficeStore.state;
        this._integrationOk = s.integration.loaded ? s.integration.configured : true;
        this._loading = s.documents.loading;
        this.requestUpdate();
    }

    _nav(path) {
        window.dispatchEvent(new CustomEvent('navigate', { detail: { path } }));
    }

    _openEmpty() {
        window.dispatchEvent(new CustomEvent('office-documents-open-empty'));
    }

    _pickUpload() {
        window.dispatchEvent(new CustomEvent('office-documents-pick-file'));
    }

    _reloadList() {
        window.dispatchEvent(new CustomEvent('office-documents-list-reload'));
    }

    _shell() {
        return this.renderRoot?.querySelector('platform-service-sidebar') ?? null;
    }

    closeMobile() {
        this._shell()?.closeMobile();
    }

    render() {
        const t = (k, p) => this.i18n.t(k, p);
        const isList = this.activeView === 'list';
        const isCatalogs = this.activeView === 'catalogs';
        const isEdit = this.activeView === 'edit';
        const actionsDisabled = !this._integrationOk || this._loading;
        const companyId = this._companyId();
        const sidebarSel = getPlatformNamespaceSidebarSelection(companyId);
        const nsSelectDisabled = !companyId || isEdit;
        const nsLabel = this.i18n.t('app_shell.sidebar.namespace', {}, 'crm');
        const nsAllLabel = this.i18n.t('filters.all', {}, 'crm');
        const createSpaceTitle = this.i18n.t('app_shell.sidebar.create_space', {}, 'crm');
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/documents_logo.svg"
                logo-text=${t('sidebar.title')}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => {
                    this.collapsed = e.detail.collapsed;
                }}
                @mobile-change=${(e) => {
                    this.mobileOpen = e.detail.open;
                }}
            >
                <div slot="header" class="office-sidebar-header-slot">
                    <div class="namespace-selector" data-hide-collapsed>
                        <span class="namespace-label">${nsLabel}</span>
                        <select
                            aria-label=${nsLabel}
                            ?disabled=${nsSelectDisabled}
                            @change=${this._onNamespaceChange}
                        >
                            <option value="" ?selected=${sidebarSel === 'all'}>${nsAllLabel}</option>
                            ${this._namespaceRows.map(
                                (ns) => html`
                                    <option
                                        value=${ns.name}
                                        ?selected=${sidebarSel !== 'all' && ns.name === sidebarSel}
                                    >
                                        ${ns.name}
                                    </option>
                                `,
                            )}
                        </select>
                        <button
                            type="button"
                            class="namespace-add-btn"
                            title=${createSpaceTitle}
                            @click=${this._openNamespaceModal}
                        >
                            <platform-icon name="plus" size="14"></platform-icon>
                        </button>
                    </div>
                </div>
                <button
                    type="button"
                    class="nav-item ${isList ? 'active' : ''}"
                    title=${t('sidebar.navList')}
                    @click=${() => this._nav('/documents')}
                >
                    <platform-icon name="list" size="18"></platform-icon>
                    <span class="nav-label" data-hide-collapsed>${t('sidebar.navList')}</span>
                </button>
                <button
                    type="button"
                    class="nav-item ${isCatalogs ? 'active' : ''}"
                    title=${t('sidebar.navCatalogs')}
                    @click=${() => this._nav('/documents/catalogs')}
                >
                    <platform-icon name="folder" size="18"></platform-icon>
                    <span class="nav-label" data-hide-collapsed>${t('sidebar.navCatalogs')}</span>
                </button>
                ${isEdit
                    ? html`
                          <button
                              type="button"
                              class="nav-item active"
                              title=${t('sidebar.navBack')}
                              @click=${() => this._nav('/documents')}
                          >
                              <platform-icon name="chevron-left" size="18"></platform-icon>
                              <span class="nav-label" data-hide-collapsed>${t('sidebar.navBack')}</span>
                          </button>
                      `
                    : null}
                <button
                    type="button"
                    class="nav-item"
                    title=${t('sidebar.navNew')}
                    ?disabled=${actionsDisabled}
                    @click=${this._openEmpty}
                >
                    <platform-icon name="plus" size="18"></platform-icon>
                    <span class="nav-label" data-hide-collapsed>${t('sidebar.navNew')}</span>
                </button>
                <button
                    type="button"
                    class="nav-item"
                    title=${t('sidebar.navUpload')}
                    ?disabled=${actionsDisabled}
                    @click=${this._pickUpload}
                >
                    <platform-icon name="paperclip" size="18"></platform-icon>
                    <span class="nav-label" data-hide-collapsed>${t('sidebar.navUpload')}</span>
                </button>
                <button
                    type="button"
                    class="nav-item"
                    title=${t('sidebar.navRefresh')}
                    ?disabled=${actionsDisabled || isEdit || isCatalogs}
                    @click=${this._reloadList}
                >
                    <platform-icon name="refresh" size="18"></platform-icon>
                    <span class="nav-label" data-hide-collapsed>${t('sidebar.navRefresh')}</span>
                </button>
                <div slot="footer" class="office-sidebar-footer">
                    <platform-user block>
                        <platform-notification-manager slot="user-toolbar"></platform-notification-manager>
                    </platform-user>
                    <platform-deployment-version base-url="/documents" footer></platform-deployment-version>
                </div>
            </platform-service-sidebar>
        `;
    }
}

customElements.define('office-sidebar', OfficeSidebar);
