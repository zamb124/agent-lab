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
 * На маршруте `documents_list` (и `documents_recent`) — nav-rail и дерево
 * каталогов проводника внутри shell-сайдбара. Настройки каталога — контекстное
 * меню на пункте дерева (ПКМ или ⋮).
 *
 * Создание и загрузка документов — в toolbar file explorer (`office-file-toolbar`).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import {
    getPlatformNamespaceSidebarSelection,
    setPlatformNamespaceSelection,
} from '@platform/lib/utils/platform-namespace.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/layout/platform-service-sidebar.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/layout/platform-sidebar-namespace-select.js';
import './office-explorer-nav-rail.js';
import './office-explorer-tree.js';

const NAMESPACES_NAME = 'office/namespaces';
const CATALOGS_NAME = 'office/catalogs';
const INTEGRATION_OP = 'office/integration_status';
const DOCUMENTS_OP = 'office/documents';

export class OfficeSidebar extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
        explorerNav: { type: Boolean, reflect: true, attribute: 'explorer-nav' },
    };

    static styles = [
        PlatformElement.styles,
        sidebarStyles,
        sidebarNavItemStyles,
        css`
            :host {
                display: block;
                height: 100%;
            }
            :host([explorer-nav]) platform-service-sidebar {
                --sidebar-width: 18.75rem;
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
            .explorer-shell {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-height: 0;
                margin-top: var(--space-2);
                padding-top: var(--space-2);
                border-top: 1px solid var(--glass-border-subtle);
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
                transition: var(--motion-transition-interactive);
                width: 100%;
                text-align: left;
            }
            .nav-item:hover { background: var(--glass-solid-subtle); }
            .nav-label {
                flex: 1;
                font-size: var(--text-base);
                font-weight: 500;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            office-explorer-tree {
                flex: 1;
                min-height: 0;
            }
            platform-service-sidebar[collapsed] .nav-label { display: none; }
            platform-service-sidebar[collapsed] .nav-item {
                justify-content: center;
                padding: var(--space-3);
            }
            platform-service-sidebar[collapsed] platform-sidebar-namespace-select { display: none; }
            platform-service-sidebar[collapsed] .explorer-shell { display: none; }
            platform-service-sidebar[collapsed] .editor-back { display: none; }
        `,
    ];

    constructor() {
        super();
        this.collapsed = readShellSidebarCollapsed();
        this.mobileOpen = false;
        this.explorerNav = false;
        this._namespaces = this.useResource(NAMESPACES_NAME, { autoload: true });
        this._catalogs = this.useResource(CATALOGS_NAME, { autoload: true });
        this._integration = this.useOp(INTEGRATION_OP);
        this._documents = this.useOp(DOCUMENTS_OP);
        this._move = this.useOp('office/document_move');
        this._routeSel = this.select((s) => s.router.routeKey);
        this._authSel = this.select((s) => s.auth.user);
    }

    connectedCallback() {
        super.connectedCallback();
        if (!this._integration.lastResult && !this._integration.busy) {
            this._integration.run(null);
        }
    }

    updated(changed) {
        super.updated(changed);
        this.explorerNav = this._showExplorerNav();
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

    _showExplorerNav() {
        const key = this._routeKey();
        return key === 'documents_list' || key === 'documents_recent';
    }

    _isEditor() { return this._routeKey() === 'document_editor'; }

    _companyId() {
        const u = this._authSel.value;
        return u && typeof u.company_id === 'string' ? u.company_id.trim() : '';
    }

    _catalogItems() {
        return this._catalogs.items;
    }

    _activeCatalogId() {
        const state = this._documents.state;
        if (typeof state.activeCatalogId === 'string' && state.activeCatalogId.length > 0) {
            return state.activeCatalogId;
        }
        const cats = this._catalogItems();
        return cats.length > 0 ? cats[0].catalog_id : '';
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

    _onExplorerViewChange(e) {
        const explorerView = e.detail && e.detail.explorerView;
        if (typeof explorerView !== 'string') return;
        this._documents.setExplorerView({ explorerView });
        this._documents.clearBindingSelection(null);
    }

    _onCatalogSelect(e) {
        const catalogId = e.detail && e.detail.catalogId;
        if (typeof catalogId !== 'string') return;
        this._documents.setExplorerView({ explorerView: 'catalog' });
        this._documents.setActiveCatalog({ catalogId });
        this._documents.setFilterCatalogs({ catalogIds: [catalogId] });
        this._documents.setCatalogExpanded({ catalogId, expanded: true });
        this._documents.clearBindingSelection(null);
    }

    _onToggleCatalog(e) {
        const catalogId = e.detail && e.detail.catalogId;
        const expanded = e.detail && e.detail.expanded === true;
        if (typeof catalogId !== 'string') return;
        this._documents.setCatalogExpanded({ catalogId, expanded });
    }

    _onCreateCatalog(e) {
        const parentCatalogId = e.detail && e.detail.parentCatalogId;
        this.openModal('office.catalog_create', {
            parentCatalogId: typeof parentCatalogId === 'string' ? parentCatalogId : '',
        });
    }

    _onMoveToCatalog(e) {
        const bindingId = e.detail && e.detail.bindingId;
        const catalogId = e.detail && e.detail.catalogId;
        if (typeof bindingId !== 'string' || typeof catalogId !== 'string') {
            return;
        }
        this._move.run({ bindingId, catalogId });
    }

    async _onCatalogAction(e) {
        const action = e.detail && e.detail.action;
        const catalog = e.detail && e.detail.catalog;
        if (typeof action !== 'string' || !catalog) {
            return;
        }
        if (action === 'edit') {
            this.openModal('office.catalog_edit', {
                catalogId: catalog.catalog_id,
                title: catalog.title,
                isPublic: Boolean(catalog.is_public),
            });
            return;
        }
        if (action === 'members') {
            this.openModal('office.catalog_members', {
                catalogId: catalog.catalog_id,
                catalogTitle: catalog.title,
                isPublic: Boolean(catalog.is_public),
            });
            return;
        }
        if (action === 'access') {
            this.openModal('office.access', {
                resourceKind: 'catalog',
                resourceId: catalog.catalog_id,
                resourceTitle: catalog.title,
            });
            return;
        }
        if (action === 'rag') {
            this.openModal('office.catalog_rag', {
                catalogId: catalog.catalog_id,
                catalogTitle: catalog.title,
            });
            return;
        }
        if (action === 'delete') {
            const ok = await platformConfirm(
                this.t('catalogs.deleteConfirm', { title: catalog.title }),
                {
                    title: this.t('catalogs.deleteConfirmTitle'),
                    variant: 'danger',
                    confirmText: this.t('list.delete'),
                    cancelText: this.t('document_upload_modal.cancel'),
                    confirmVariant: 'danger',
                },
            );
            if (ok !== true) {
                return;
            }
            await this._catalogs.remove(catalog.catalog_id);
            this._documents.clearFilter(null);
        }
    }

    _renderExplorerNav() {
        if (!this._showExplorerNav()) return '';
        const cats = this._catalogItems();
        const state = this._documents.state;
        return html`
            <div class="explorer-shell" data-hide-collapsed>
                <office-explorer-nav-rail
                    active-view=${state.explorerView}
                    deleted-enabled
                    @view-change=${this._onExplorerViewChange}
                ></office-explorer-nav-rail>
                <office-explorer-tree
                    .catalogs=${cats}
                    active-catalog-id=${this._activeCatalogId()}
                    .expandedCatalogIds=${state.expandedCatalogIds || []}
                    @select-catalog=${this._onCatalogSelect}
                    @toggle-catalog=${this._onToggleCatalog}
                    @create-catalog=${this._onCreateCatalog}
                    @catalog-action=${this._onCatalogAction}
                    @move-to-catalog=${this._onMoveToCatalog}
                ></office-explorer-tree>
            </div>
        `;
    }

    render() {
        const items = this._namespaces.items;
        const companyId = this._companyId();
        const sidebarSel = getPlatformNamespaceSidebarSelection(companyId);
        this._ensureExplicitNamespace(items, sidebarSel, companyId);
        const isEditor = this._isEditor();
        const noNamespaces = items.length === 0;
        const nsValue = this._namespaceFieldValue(sidebarSel, items);
        const nsConfig = this._namespaceEnumConfig(items, noNamespaces);
        const sidebarWidth = this._showExplorerNav() ? '300px' : '280px';
        return html`
            <platform-service-sidebar
                logo-src="/static/core/assets/service_logos/documents_logo.svg"
                logo-text=${this.t('sidebar.title')}
                width=${sidebarWidth}
                ?logo-opens-services=${true}
                ?collapsed=${this.collapsed}
                ?mobile-open=${this.mobileOpen}
                @collapse-change=${(e) => { this.collapsed = e.detail.collapsed; }}
                @mobile-change=${(e) => { this.mobileOpen = e.detail.open; }}
            >
                <div slot="header">
                    <platform-sidebar-namespace-select
                        .label=${this.t('sidebar.namespace_label')}
                        .value=${nsValue}
                        .config=${nsConfig}
                        ?disabled=${!companyId || isEditor || noNamespaces}
                        ?show-edit=${false}
                        add-title=${this.t('sidebar.create_namespace_tooltip')}
                        @change=${this._onNamespaceChange}
                        @add-request=${this._openCreateNamespaceModal}
                    ></platform-sidebar-namespace-select>
                </div>
                ${isEditor ? html`
                    <button class="nav-item editor-back"
                            type="button"
                            @click=${() => this._navigateTo('documents_list')}>
                        <platform-icon name="chevron-left" size="18"></platform-icon>
                        <span class="nav-label">${this.t('sidebar.navBack')}</span>
                    </button>
                ` : ''}
                ${this._renderExplorerNav()}
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
