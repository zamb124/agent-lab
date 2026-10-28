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
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { sidebarStyles, sidebarNavItemStyles } from '@platform/lib/styles/shared/sidebar.styles.js';
import {
    getPlatformNamespaceSidebarSelection,
    setPlatformNamespaceSelection,
} from '@platform/lib/utils/platform-namespace.js';
import {
    documentsExplorerPageQuery,
    documentsExplorerQueryNamespace,
} from '../_helpers/documents-explorer-query.js';
import { readShellSidebarCollapsed } from '@platform/lib/utils/shell-sidebar-preference.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { PlatformServiceSidebar } from '@platform/lib/components/layout/platform-service-sidebar.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user.js';
import '@platform/lib/components/platform-notification-manager.js';
import '@platform/lib/components/platform-deployment-version.js';
import '@platform/lib/components/layout/platform-sidebar-namespace-select.js';
import './office-explorer-nav-rail.js';
import './office-explorer-tree.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

const NAMESPACES_NAME = 'office/namespaces';
const CATALOGS_NAME = 'office/catalogs';
const INTEGRATION_OP = 'office/integration_status';
const DOCUMENTS_OP = 'office/documents';

export class OfficeSidebar extends PlatformElement {
    static i18nNamespace = 'documents';

    static override properties: PropertyDeclarations = {
        collapsed: { type: Boolean, reflect: true },
        mobileOpen: { type: Boolean, reflect: true, attribute: 'mobile-open' },
        explorerNav: { type: Boolean, reflect: true, attribute: 'explorer-nav' },
    }
    declare collapsed: boolean;
    declare mobileOpen: boolean;
    declare explorerNav: boolean;
;

    static override styles: CSSResultGroup = [
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
                padding: var(--space-2);
            }
            platform-service-sidebar[collapsed] .nav-item:hover { transform: none; }
            platform-service-sidebar[collapsed] platform-sidebar-namespace-select { display: none; }
            platform-service-sidebar[collapsed] office-explorer-tree { display: none; }
            platform-service-sidebar[collapsed] .editor-back { display: none; }
            platform-service-sidebar[collapsed] .office-sidebar-footer {
                align-items: center;
            }
            platform-service-sidebar[collapsed] .explorer-shell {
                margin-top: 0;
                padding-top: 0;
                border-top: none;
            }
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
        this._routerSearchSel = this.select((s) => s.router.search);
        this._authSel = this.select((s) => s.auth.user);
    }
    private _namespaces: ResourceController;
    private _catalogs: ResourceController;
    private _integration: OpController;
    private _documents: ControllerFor<'office/documents'>;
    private _move: OpController;
    private _routeSel: SelectController<unknown>;
    private _routerSearchSel: SelectController<unknown>;
    private _authSel: SelectController<unknown>;


    override connectedCallback(): void {
        super.connectedCallback();
        if (!this._integration.lastResult && !this._integration.busy) {
            this._integration.run(null);
        }
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        this.explorerNav = this._showExplorerNav();
    }

    private _shell(): PlatformServiceSidebar | null {
        const shell = this.renderRoot.querySelector('platform-service-sidebar');
        if (shell === null) return null;
        if (!(shell instanceof PlatformServiceSidebar)) {
            throw new Error('office sidebar: platform-service-sidebar required');
        }
        return shell;
    }
    closeMobile() {
        const shell = this._shell();
        if (shell === null) return;
        shell.closeMobile();
    }

    private _routeKey() {
        const v = this._routeSel.value;
        return typeof v === 'string' && v !== '' ? v : 'documents_list';
    }

    private _showExplorerNav() {
        const key = this._routeKey();
        return key === 'documents_list' || key === 'documents_recent';
    }

    private _isEditor() { return this._routeKey() === 'document_editor'; }

    private _companyId() {
        const user = this._authSel.value;
        if (!isPlainRecord(user) || typeof user.company_id !== 'string') return '';
        return user.company_id.trim();
    }

    private _catalogItems(): readonly Record<string, unknown>[] {
        return this._catalogs.items;
    }

    private _activeCatalogId() {
        const catalogId = this._documents.state.activeCatalogId;
        if (typeof catalogId === 'string' && catalogId.length > 0) return catalogId;
        return '';
    }

    private _navRailActiveView(state: Record<string, unknown>) {
        if (state.explorerView !== 'catalog') {
            return state.explorerView;
        }
        return this._activeCatalogId().length === 0 ? 'catalog' : '';
    }

    private _namespaceEnumConfig(items: unknown, noNamespaces: boolean) {
        if (noNamespaces) {
            return {
                values: [{ value: '', label: this.t('sidebar.namespace_empty_placeholder') }],
            };
        }
        if (!Array.isArray(items)) {
            throw new Error('OfficeSidebar._namespaceEnumConfig: items must be an array');
        }
        const values: Array<{ value: string; label: string }> = [];
        for (const ns of items) {
            if (!isPlainRecord(ns) || typeof ns.name !== 'string' || ns.name.length === 0) {
                throw new Error('OfficeSidebar._namespaceEnumConfig: invalid namespace item');
            }
            values.push({ value: ns.name, label: ns.name });
        }
        return { values };
    }

    private _namespaceFieldValue(sidebarSel: unknown, items: unknown) {
        if (!Array.isArray(items) || items.length === 0) return '';
        if (typeof sidebarSel === 'string' && sidebarSel !== 'all') {
            const hit = items.find((ns: Record<string, unknown>) => ns && ns.name === sidebarSel);
            if (hit && typeof hit.name === 'string') return hit.name;
        }
        const first = items[0];
        if (!first || typeof first.name !== 'string') {
            throw new Error('OfficeSidebar._namespaceFieldValue: invalid first namespace');
        }
        return first.name;
    }

    private _onNamespaceChange(e: CustomEvent<{ value?: unknown }>) {
        const cid = this._companyId();
        if (!cid) return;
        const detail = e.detail;
        const raw = detail && typeof detail.value === 'string' ? detail.value : '';
        const name = raw.trim();
        if (!name) return;
        setPlatformNamespaceSelection(cid, name);
        this._documents.clearFilter(null);
    }

    private _ensureExplicitNamespace(items: unknown, sidebarSel: unknown, companyId: string) {
        if (!companyId) return;
        const queryNs = documentsExplorerQueryNamespace(
            documentsExplorerPageQuery(
                this._routerSearchSel.value,
                window.location.search,
            ),
        );
        if (queryNs.length > 0) {
            if (sidebarSel !== queryNs) {
                setPlatformNamespaceSelection(companyId, queryNs);
            }
            return;
        }
        if (sidebarSel !== 'all') return;
        if (!Array.isArray(items) || items.length === 0) return;
        const first = items[0];
        if (!first || typeof first.name !== 'string' || first.name.length === 0) return;
        setPlatformNamespaceSelection(companyId, first.name);
    }

    private _openCreateNamespaceModal() {
        this.openModal('office.namespace_create');
    }

    private _navigateTo(routeKey: string) {
        this.navigate(routeKey);
        this.closeMobile();
    }

    private _onExplorerViewChange(e: CustomEvent<{ explorerView?: unknown }>) {
        const explorerView = e.detail && e.detail.explorerView;
        if (typeof explorerView !== 'string') return;
        this._documents.setExplorerView({ explorerView });
        if (explorerView === 'catalog') {
            this._documents.setActiveCatalog({ catalogId: null });
            this._documents.setFilterCatalogs({ catalogIds: [] });
        }
        this._documents.clearFileSelection(null);
    }

    private _onCatalogSelect(e: CustomEvent<{ catalogId?: unknown }>) {
        const catalogId = e.detail && e.detail.catalogId;
        if (typeof catalogId !== 'string') return;
        this._documents.setExplorerView({ explorerView: 'catalog' });
        this._documents.setActiveCatalog({ catalogId });
        this._documents.setFilterCatalogs({ catalogIds: [catalogId] });
        this._documents.setCatalogExpanded({ catalogId, expanded: true });
        this._documents.clearFileSelection(null);
    }

    private _onToggleCatalog(e: CustomEvent<{ catalogId?: unknown; expanded?: unknown }>) {
        const catalogId = e.detail && e.detail.catalogId;
        const expanded = e.detail && e.detail.expanded === true;
        if (typeof catalogId !== 'string') return;
        this._documents.setCatalogExpanded({ catalogId, expanded });
    }

    private _onCreateCatalog(e: CustomEvent<{ parentCatalogId?: unknown }>) {
        const parentCatalogId = e.detail && e.detail.parentCatalogId;
        this.openModal('office.catalog_create', {
            parentCatalogId: typeof parentCatalogId === 'string' ? parentCatalogId : '',
        });
    }

    private _onMoveToCatalog(e: CustomEvent<{ fileId?: unknown; catalogId?: unknown }>) {
        const fileId = e.detail && e.detail.fileId;
        const catalogId = e.detail && e.detail.catalogId;
        if (typeof fileId !== 'string' || typeof catalogId !== 'string') {
            return;
        }
        this._move.run({ file_id: fileId, catalog_id: catalogId });
    }

    private async _onCatalogAction(e: CustomEvent<{ action?: unknown; catalog?: unknown }>) {
        const action = e.detail && e.detail.action;
        const catalog = e.detail && e.detail.catalog;
        if (typeof action !== 'string' || !isPlainRecord(catalog)) {
            return;
        }
        if (action === 'edit') {
            this.openModal('office.catalog_edit', {
                catalogId: catalog.catalog_id,
                title: catalog.title,
                companyVisible: Boolean(catalog.company_visible),
            });
            return;
        }
        if (action === 'members') {
            this.openModal('office.catalog_members', {
                catalogId: catalog.catalog_id,
                catalogTitle: catalog.title,
                companyVisible: Boolean(catalog.company_visible),
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
            const title = catalog.title;
            if (typeof title !== 'string') {
                throw new Error('office sidebar: catalog title required');
            }
            const ok = await platformConfirm(
                this.t('catalogs.deleteConfirm', { title }),
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
            const catalogId = catalog.catalog_id;
            if (typeof catalogId !== 'string' || catalogId.length === 0) {
                throw new Error('office sidebar: catalog_id required');
            }
            await this._catalogs.remove(catalogId);
            this._documents.clearFilter(null);
        }
    }

    private _renderExplorerNav() {
        if (!this._showExplorerNav()) return '';
        const cats = this._catalogItems();
        const state = this._documents.state;
        const expandedCatalogIds = state.expandedCatalogIds;
        if (expandedCatalogIds !== undefined && expandedCatalogIds !== null && !Array.isArray(expandedCatalogIds)) {
            throw new Error('office sidebar: expandedCatalogIds must be an array');
        }
        return html`
            <div class="explorer-shell">
                <office-explorer-nav-rail
                    active-view=${this._navRailActiveView(state)}
                    deleted-enabled
                    @view-change=${this._onExplorerViewChange}
                ></office-explorer-nav-rail>
                <office-explorer-tree
                    data-hide-collapsed
                    .catalogs=${cats}
                    active-catalog-id=${this._activeCatalogId()}
                    .expandedCatalogIds=${Array.isArray(expandedCatalogIds) ? expandedCatalogIds : []}
                    @select-catalog=${this._onCatalogSelect}
                    @toggle-catalog=${this._onToggleCatalog}
                    @create-catalog=${this._onCreateCatalog}
                    @catalog-action=${this._onCatalogAction}
                    @move-to-catalog=${this._onMoveToCatalog}
                ></office-explorer-tree>
            </div>
        `;
    }

    override render(): TemplateResult {
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
                @collapse-change=${(e: CustomEvent<{ collapsed?: unknown }>) => { this.collapsed = e.detail.collapsed === true; }}
                @mobile-change=${(e: CustomEvent<{ open?: unknown }>) => { this.mobileOpen = e.detail.open === true; }}
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
