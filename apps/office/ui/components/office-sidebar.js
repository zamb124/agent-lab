/**
 * OfficeSidebar — навигация сервиса Документы.
 *
 * NS-селектор питается из `useResource('office/namespaces', { autoload: true })`
 * (BFF проксирует список workspace-ов из CRM); выбор пишется через
 * `setPlatformNamespaceSelection(companyId, name)` (core utility публикует
 * `UI_NAMESPACE_SELECT_REQUESTED`, ui.effect персистит). Кнопка "+" открывает
 * модалку `office.namespace_create`.
 *
 * В сервисе Документы режим «все пространства» запрещён: каталоги и документы
 * жёстко привязаны к конкретному namespace. Если выбора ещё нет (или он
 * сохранён как `all`), sidebar автоматически выбирает первый namespace из
 * загруженного списка через `setPlatformNamespaceSelection`.
 *
 * Меню навигирует через `this.navigate(routeKey)` → core router.effect.
 * Активный пункт — по `state.router.routeKey`. В режиме editor (route
 * `document_editor`) NS-select disabled и появляется кнопка «назад».
 *
 * Кнопки New empty / Upload открывают модалки `office.document_create_empty`
 * / `office.document_upload` с активным catalogId, который читается из
 * slice `state.officeDocuments.activeCatalogId`. Если активный каталог
 * не выбран — кнопки disabled (бэкенд требует явный catalog_id).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import {
    getPlatformNamespaceSidebarSelection,
    setPlatformNamespaceSelection,
} from '@platform/lib/utils/platform-namespace.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/fields/platform-field.js';

const NAMESPACES_NAME = 'office/namespaces';
const INTEGRATION_OP = 'office/integration_status';
const DOCUMENTS_OP = 'office/documents';

export class OfficeSidebar extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
    };

    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        buttonStyles,
        css`
            :host { display: block; height: 100%; }
            platform-service-sidebar {
                --sidebar-logo-text-weight: 700;
                --sidebar-logo-text-gradient: var(--documents-title-gradient);
                --sidebar-logo-text-clip: text;
                --sidebar-logo-text-fill: transparent;
            }
            .office-sidebar-footer {
                display: flex; flex-direction: column;
                align-items: stretch;
                gap: 6px; width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
            .nav-item {
                display: flex; align-items: center;
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
            .nav-item:hover { background: var(--glass-solid-subtle); }
            .nav-item.active {
                background: var(--accent-subtle);
                color: var(--accent);
                font-weight: 600;
            }
            .nav-item:disabled { opacity: 0.4; cursor: not-allowed; }
            .nav-label {
                flex: 1;
                font-size: var(--text-base);
                font-weight: 500;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            platform-service-sidebar[collapsed] .nav-label { display: none; }
            platform-service-sidebar[collapsed] .nav-item {
                justify-content: center;
                padding: var(--space-3);
            }
            .namespace-selector {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-bottom: var(--space-3);
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
            .namespace-selector-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                width: 100%;
            }
            .namespace-label {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-tertiary);
                line-height: 1.2;
                align-self: stretch;
            }
            .namespace-selector-row platform-field {
                flex: 1 1 0;
                min-width: 0;
                display: block;
            }
            .namespace-add-btn {
                display: flex; align-items: center; justify-content: center;
                width: 24px; height: 24px;
                flex-shrink: 0;
                border: none;
                background: var(--accent);
                color: var(--text-inverse, white);
                border-radius: var(--radius-md);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .namespace-add-btn:hover { transform: scale(1.05); }
            platform-service-sidebar[collapsed] .namespace-selector { display: none; }
        `,
    ];

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this._namespaces = this.useResource(NAMESPACES_NAME, { autoload: true });
        this._integration = this.useOp(INTEGRATION_OP);
        this._documents = this.useOp(DOCUMENTS_OP);
        this._routeSel = this.select((s) => s.router.routeKey);
        this._authSel = this.select((s) => s.auth.user);
    }

    connectedCallback() {
        super.connectedCallback();
        if (!this._integration.lastResult && !this._integration.busy) {
            this._integration.run(null);
        }
    }

    _shell() { return this.renderRoot ? this.renderRoot.querySelector('platform-service-sidebar') : null; }
    closeMobile() {
        const shell = this._shell();
        if (shell && typeof shell.closeMobile === 'function') {
            shell.closeMobile();
        }
    }

    _routeKey() {
        const v = this._routeSel.value;
        return typeof v === 'string' && v !== '' ? v : 'documents_list';
    }
    _isList() { return this._routeKey() === 'documents_list'; }
    _isCatalogs() { return this._routeKey() === 'documents_catalogs'; }
    _isEditor() { return this._routeKey() === 'document_editor'; }

    _companyId() {
        const u = this._authSel.value;
        return u && typeof u.company_id === 'string' ? u.company_id.trim() : '';
    }

    _activeCatalogId() {
        const state = this._documents.state;
        if (typeof state.activeCatalogId === 'string' && state.activeCatalogId.length > 0) {
            return state.activeCatalogId;
        }
        if (Array.isArray(state.loadedCatalogIds) && state.loadedCatalogIds.length === 1) {
            return state.loadedCatalogIds[0];
        }
        return '';
    }

    _namespaceEnumConfig(items, noNamespaces) {
        if (noNamespaces) {
            return {
                values: [{ value: '', label: this.t('sidebar.namespace_empty_placeholder') }],
            };
        }
        if (!Array.isArray(items)) {
            throw new Error('OfficeSidebar._namespaceEnumConfig: items must be an array');
        }
        const values = [];
        for (const ns of items) {
            if (!ns || typeof ns.name !== 'string' || ns.name.length === 0) {
                throw new Error('OfficeSidebar._namespaceEnumConfig: invalid namespace item');
            }
            values.push({ value: ns.name, label: ns.name });
        }
        return { values };
    }

    _namespaceFieldValue(sidebarSel, items) {
        if (!Array.isArray(items) || items.length === 0) return '';
        if (typeof sidebarSel === 'string' && sidebarSel !== 'all') {
            const hit = items.find((ns) => ns && ns.name === sidebarSel);
            if (hit && typeof hit.name === 'string') return hit.name;
        }
        const first = items[0];
        if (!first || typeof first.name !== 'string') {
            throw new Error('OfficeSidebar._namespaceFieldValue: invalid first namespace');
        }
        return first.name;
    }

    _onNamespaceChange(e) {
        const cid = this._companyId();
        if (!cid) return;
        const detail = e.detail;
        const raw = detail && typeof detail.value === 'string' ? detail.value : '';
        const name = raw.trim();
        if (!name) return;
        setPlatformNamespaceSelection(cid, name);
        this._documents.clearFilter(null);
    }

    _ensureExplicitNamespace(items, sidebarSel, companyId) {
        if (!companyId) return;
        if (sidebarSel !== 'all') return;
        if (!Array.isArray(items) || items.length === 0) return;
        const first = items[0];
        if (!first || typeof first.name !== 'string' || first.name.length === 0) return;
        setPlatformNamespaceSelection(companyId, first.name);
    }

    _openCreateNamespaceModal() {
        this.openModal('office.namespace_create');
    }

    _navigateTo(routeKey) {
        this.navigate(routeKey);
        this.closeMobile();
    }

    _openEmpty() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) return;
        this.openModal('office.document_create_empty', { catalogId, openAfterCreate: true });
    }

    _openUpload() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) return;
        this.openModal('office.document_upload', { catalogId, openAfterUpload: true });
    }

    _reloadList() {
        const ids = this._documents.state.loadedCatalogIds;
        if (Array.isArray(ids) && ids.length > 0) {
            this._documents.run({ catalogIds: ids });
        }
    }

    render() {
        const items = this._namespaces.items;
        const companyId = this._companyId();
        const sidebarSel = getPlatformNamespaceSidebarSelection(companyId);
        this._ensureExplicitNamespace(items, sidebarSel, companyId);
        const isEditor = this._isEditor();
        const integrationConfigured = this._integration.lastResult
            ? Boolean(this._integration.lastResult.configured)
            : true;
        const actionsDisabled = !integrationConfigured || !this._activeCatalogId();
        const refreshDisabled = !this._documents.state.loadedCatalogIds.length;
        const noNamespaces = items.length === 0;
        const nsValue = this._namespaceFieldValue(sidebarSel, items);
        const nsConfig = this._namespaceEnumConfig(items, noNamespaces);
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/documents_logo.svg"
                logo-text=${this.t('sidebar.title')}
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e) => { this.mobileOpen = e.detail.open; }}
            >
                <div slot="header">
                    <div class="namespace-selector" data-hide-collapsed>
                        <span class="namespace-label">${this.t('sidebar.namespace_label')}</span>
                        <div class="namespace-selector-row">
                            <platform-field
                                type="enum"
                                mode="edit"
                                label=""
                                pill-density="compact"
                                .value=${nsValue}
                                .config=${nsConfig}
                                ?disabled=${!companyId || isEditor || noNamespaces}
                                @change=${this._onNamespaceChange}
                            ></platform-field>
                            <button type="button"
                                    class="namespace-add-btn"
                                    title=${this.t('sidebar.create_namespace_tooltip')}
                                    @click=${this._openCreateNamespaceModal}>
                                <platform-icon name="plus" size="14"></platform-icon>
                            </button>
                        </div>
                    </div>
                </div>
                <button class="nav-item ${this._isList() ? 'active' : ''}"
                        type="button"
                        @click=${() => this._navigateTo('documents_list')}>
                    <platform-icon name="list" size="18"></platform-icon>
                    <span class="nav-label">${this.t('sidebar.navList')}</span>
                </button>
                <button class="nav-item ${this._isCatalogs() ? 'active' : ''}"
                        type="button"
                        @click=${() => this._navigateTo('documents_catalogs')}>
                    <platform-icon name="folder" size="18"></platform-icon>
                    <span class="nav-label">${this.t('sidebar.navCatalogs')}</span>
                </button>
                ${isEditor ? html`
                    <button class="nav-item"
                            type="button"
                            @click=${() => this._navigateTo('documents_list')}>
                        <platform-icon name="chevron-left" size="18"></platform-icon>
                        <span class="nav-label">${this.t('sidebar.navBack')}</span>
                    </button>
                ` : ''}
                <button class="nav-item"
                        type="button"
                        ?disabled=${actionsDisabled}
                        @click=${this._openEmpty}>
                    <platform-icon name="plus" size="18"></platform-icon>
                    <span class="nav-label">${this.t('sidebar.navNew')}</span>
                </button>
                <button class="nav-item"
                        type="button"
                        ?disabled=${actionsDisabled}
                        @click=${this._openUpload}>
                    <platform-icon name="paperclip" size="18"></platform-icon>
                    <span class="nav-label">${this.t('sidebar.navUpload')}</span>
                </button>
                <button class="nav-item"
                        type="button"
                        ?disabled=${refreshDisabled || isEditor || this._isCatalogs()}
                        @click=${this._reloadList}>
                    <platform-icon name="refresh" size="18"></platform-icon>
                    <span class="nav-label">${this.t('sidebar.navRefresh')}</span>
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
