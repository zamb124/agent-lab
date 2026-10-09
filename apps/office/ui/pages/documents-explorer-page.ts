/**
 * OfficeDocumentsExplorerPage — file explorer (Untitled UI pattern).
 *
 * Маршрут `/documents`. Дерево каталогов + toolbar + list/grid + details panel.
 */

import { html } from 'lit';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { DocumentsOpController, OfficeDocumentItem } from '../events/documents.types.js';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { documentsExplorerStyles } from '../styles/documents-explorer.styles.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import {
    getActivePlatformNamespaceName,
    setPlatformNamespaceSelection,
} from '@platform/lib/utils/platform-namespace.js';
import {
    documentsExplorerPageQuery,
    documentsExplorerQueryNamespace,
} from '../_helpers/documents-explorer-query.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { formatFileRetentionRemaining } from '@platform/lib/utils/format-file-retention.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { storageGet, storageSet } from '@platform/lib/utils/platform-storage.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-file-table.js';
import '@platform/lib/components/platform-file-row.js';
import '@platform/lib/components/platform-file-card.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/office-integration-banner.js';
import '../components/office-file-toolbar.js';
import '../components/office-file-details-panel.js';
import '../components/office-file-actions-menu.js';
import '../components/office-catalog-actions-menu.js';
import '../components/office-catalog-semantic-search-results.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

const VIEW_MODE_STORAGE_KEY = 'documents_explorer_view_mode';
const SEARCH_DEBOUNCE_MS = 300;
const RAG_INDEX_STATUS_VALUES = new Set(['ready', 'pending', 'failed', 'absent']);

export class OfficeDocumentsExplorerPage extends PlatformPage {
    static i18nNamespace = 'documents';

    static override properties: PropertyDeclarations = {
        initialExplorerView: { type: String, attribute: false },
        _dragOver: { state: true },
        _searchDebounceTimer: { state: false },
    }
    declare initialExplorerView: string;
    declare _dragOver: boolean;
    declare _searchDebounceTimer: ReturnType<typeof setTimeout> | false;

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        buttonStyles,
        documentsExplorerStyles,
    ];

    constructor() {
        super();
        this.initialExplorerView = 'catalog';
        this._dragOver = false;
        this._searchDebounceTimer = false;
        this._integration = this.useOp('office/integration_status');
        this._catalogs = this.useResource('office/catalogs', { autoload: true });
        this._documents = this.useOp('office/documents') as unknown as DocumentsOpController;
        this._deleted = this.useOp('office/documents_deleted');
        this._upload = this.useOp('office/document_upload');
        this._remove = this.useOp('office/document_remove');
        this._restore = this.useOp('office/document_restore');
        this._permanentDelete = this.useOp('office/document_permanent_delete');
        this._shareCreate = this.useOp('office/document_share_create');
        this._catalogRagSearch = this.useOp('office/catalog_rag_search');
        this._move = this.useOp('office/document_move');
        this._lastLoadKey = '';
        this._lastSemanticSearchKey = '';
        this._localeSel = this.select((s) => (s.i18n as Record<string, unknown>).locale);
        this._routerSearchSel = this.select((s) => (s.router as Record<string, unknown>).search);
        this._authSel = this.select((s) => (s.auth as Record<string, unknown>).user);
        this._accessModalOpened = false;
        this._deepLinkApplied = '';
        this._deepLinkMissing = '';
    }
    private _integration: OpController;
    private _catalogs: ResourceController;
    private _documents: DocumentsOpController;
    private _deleted: OpController;
    private _upload: OpController;
    private _remove: OpController;
    private _restore: OpController;
    private _permanentDelete: OpController;
    private _shareCreate: OpController;
    private _catalogRagSearch: OpController;
    private _move: OpController;
    private _lastLoadKey: string;
    private _lastSemanticSearchKey: string;
    private _localeSel: SelectController<unknown>;
    private _routerSearchSel: SelectController<unknown>;
    private _authSel: SelectController<unknown>;
    private _accessModalOpened: boolean;
    private _deepLinkApplied: string;
    private _deepLinkMissing: string;
    private _searchTimer: number | undefined;


    override connectedCallback(): void {
        super.connectedCallback();
        if (!this._integration.lastResult && !this._integration.busy) {
            this._integration.run(null);
        }
        this._restoreViewMode();
        if (this.initialExplorerView === 'recent') {
            this._documents.setExplorerView({ explorerView: 'recent' });
        }
        this.useEvent(CoreEvents.UI_DOCUMENTS_RELOAD_REQUESTED, () => this._onNamespaceReload());
    }

    private _restoreViewMode() {
        const raw = storageGet(platformStorageKey('office', VIEW_MODE_STORAGE_KEY));
        if (raw === 'list' || raw === 'grid') {
            this._documents.setViewMode({ viewMode: raw });
        }
    }

    private _persistViewMode(mode: unknown) {
        if (mode !== 'list' && mode !== 'grid') return;
        storageSet(platformStorageKey('office', VIEW_MODE_STORAGE_KEY), mode);
    }

    private _onNamespaceReload() {
        this._lastLoadKey = '';
        this._documents.clearFilter(null);
        this._documents.setSearchQuery({ searchQuery: '' });
        this._documents.clearFileSelection(null);
        this._catalogs.load();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated && super.updated(changed);
        this._ensureSearchMode();
        this._applyExplorerQuery();
        this._maybeReloadDocs();
        this._maybeRunSemanticSearch();
        this._ensureActiveCatalog();
        this._maybeOpenAccessFromQuery();
    }

    private _companyId() {
        const user = this._authSel.value as Record<string, unknown> | null;
        return user && typeof user.company_id === 'string' ? user.company_id.trim() : '';
    }

    private _explorerQuery() {
        return documentsExplorerPageQuery(
            this._routerSearchSel.value,
            window.location.search,
        );
    }

    private _applyExplorerQuery() {
        const query = this._explorerQuery();
        const targetNs = documentsExplorerQueryNamespace(query);
        const companyId = this._companyId();
        if (targetNs.length > 0) {
            if (companyId.length === 0) {
                return;
            }
            if (getActivePlatformNamespaceName(companyId) !== targetNs) {
                setPlatformNamespaceSelection(companyId, targetNs);
                return;
            }
        }
        if (query.catalogId.length === 0) {
            return;
        }
        if (this._catalogs.loading || this._catalogs.refreshing) {
            return;
        }
        const catalog = this._catalogById(query.catalogId);
        if (!catalog) {
            if (this._deepLinkMissing !== query.catalogId) {
                this._deepLinkMissing = query.catalogId;
                this.toast('toast.catalog_open_failed', { type: 'error' });
            }
            return;
        }
        const appliedKey = `${targetNs}|${query.catalogId}`;
        if (
            this._deepLinkApplied === appliedKey
            && this._documents.state.activeCatalogId === query.catalogId
        ) {
            return;
        }
        this._deepLinkApplied = appliedKey;
        this._documents.setExplorerView({ explorerView: 'catalog' });
        this._documents.setActiveCatalog({ catalogId: query.catalogId });
        this._documents.setFilterCatalogs({ catalogIds: [query.catalogId] });
        for (const ancestor of this._catalogAncestorChain(query.catalogId)) {
            this._documents.setCatalogExpanded({ catalogId: ancestor.catalog_id, expanded: true });
        }
        this._documents.clearFileSelection(null);
        this._lastLoadKey = '';
    }

    private _maybeOpenAccessFromQuery() {
        if (this._accessModalOpened) {
            return;
        }
        const query = this._explorerQuery();
        if (!query.access || query.catalogId.length === 0) {
            return;
        }
        const catalog = this._catalogById(query.catalogId);
        if (!catalog) {
            return;
        }
        this._accessModalOpened = true;
        this._documents.setActiveCatalog({ catalogId: query.catalogId });
        this._documents.setFilterCatalogs({ catalogIds: [query.catalogId] });
        this._onCatalogAccess(catalog);
    }

    private _ragIndexStatusLabel(status: unknown) {
        if (typeof status !== 'string' || !RAG_INDEX_STATUS_VALUES.has(status)) {
            return '';
        }
        return this.t(`rag_index.${status}`);
    }

    private _semanticSearchAvailable() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) return false;
        const catalogs = this._catalogItems();
        const active = catalogs.find((item: Record<string, unknown>) => item.catalog_id === catalogId);
        if (!active) return false;
        return active.rag_index_enabled === true;
    }

    private _ensureSearchMode() {
        const state = this._documents.state;
        if (state.explorerView !== 'catalog') {
            if (state.searchMode === 'semantic') {
                this._documents.setSearchMode({ searchMode: 'files' });
            }
            return;
        }
        if (state.searchMode === 'semantic' && !this._semanticSearchAvailable()) {
            this._documents.setSearchMode({ searchMode: 'files' });
        }
    }

    private _maybeRunSemanticSearch() {
        const state = this._documents.state;
        if (state.explorerView !== 'catalog') return;
        if (state.searchMode !== 'semantic') return;
        const catalogId = this._activeCatalogId();
        const query = typeof state.searchQuery === 'string' ? state.searchQuery.trim() : '';
        if (!catalogId || query.length === 0) return;
        const catalogOptions = this._activeCatalogSearchOptions();
        const key = `${catalogId}|${query}|${JSON.stringify(catalogOptions)}`;
        if (key === this._lastSemanticSearchKey) return;
        this._lastSemanticSearchKey = key;
        this._catalogRagSearch.run({
            catalog_id: catalogId,
            query,
            limit: 20,
            ...catalogOptions,
        });
    }

    private _activeCatalogSearchOptions() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) {
            return {};
        }
        const catalogs = this._catalogItems();
        const active = catalogs.find((item: Record<string, unknown>) => item.catalog_id === catalogId);
        if (!active || !active.rag_index_search_options || typeof active.rag_index_search_options !== 'object') {
            return {};
        }
        return active.rag_index_search_options as Record<string, unknown>;
    }

    private _semanticSearchItems(): OfficeDocumentItem[] {
        const result = this._catalogRagSearch.lastResult as { items?: unknown } | null;
        if (!result || typeof result !== 'object' || !Array.isArray(result.items)) {
            return [];
        }
        return result.items as OfficeDocumentItem[];
    }

    private _showSemanticResults() {
        const state = this._documents.state;
        if (state.explorerView !== 'catalog') return false;
        if (state.searchMode !== 'semantic') return false;
        return typeof state.searchQuery === 'string' && state.searchQuery.trim().length > 0;
    }

    private _catalogItems(): Array<Record<string, unknown>> {
        return this._catalogs.items as Array<Record<string, unknown>>;
    }

    private _activeCatalogId() {
        const state = this._documents.state;
        if (typeof state.activeCatalogId === 'string' && state.activeCatalogId.length > 0) {
            return state.activeCatalogId;
        }
        return '';
    }

    private _isNamespaceRoot() {
        return this._documents.state.explorerView === 'catalog' && this._activeCatalogId().length === 0;
    }

    private _activeCatalogTitle() {
        const id = this._activeCatalogId();
        if (!id) {
            return this.t('nav.allDocuments');
        }
        const hit = this._catalogItems().find((c: Record<string, unknown>) => c.catalog_id === id);
        return hit ? hit.title : this.t('list.catalogUnknown');
    }

    private _ensureActiveCatalog() {
        if (this._catalogs.loading) return;
        const cats = this._catalogItems();
        const active = this._documents.state.activeCatalogId;
        if (typeof active !== 'string' || active.length === 0) {
            return;
        }
        const query = this._explorerQuery();
        if (query.catalogId.length > 0 && query.catalogId === active) {
            return;
        }
        const exists = cats.some((c: Record<string, unknown>) => c.catalog_id === active);
        if (exists) return;
        this._documents.setActiveCatalog({ catalogId: null });
        this._documents.setFilterCatalogs({ catalogIds: [] });
    }

    private _listPayloadFor(catalogIds: string[]) {
        const state = this._documents.state;
        const query = typeof state.searchQuery === 'string' ? state.searchQuery.trim() : '';
        return {
            catalog_ids: catalogIds,
            q: query.length > 0 ? query : null,
            sort: state.sortKey,
            order: state.sortDir,
        };
    }

    private _listPayload() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) {
            throw new Error('OfficeDocumentsExplorerPage: active catalog required');
        }
        return this._listPayloadFor([catalogId]);
    }

    private _childCatalogsAtCurrentLevel() {
        if (this._documents.state.explorerView !== 'catalog') return [];
        const catalogId = this._activeCatalogId();
        return this._catalogItems().filter((catalog: Record<string, unknown>) => {
            const parentId = typeof catalog.parent_catalog_id === 'string' ? catalog.parent_catalog_id : '';
            return parentId === catalogId;
        });
    }

    private _visibleChildCatalogs() {
        const children = this._childCatalogsAtCurrentLevel();
        const rawQuery = this._documents.state.searchQuery;
        const query = typeof rawQuery === 'string' ? rawQuery.trim().toLowerCase() : '';
        const matched = query.length === 0
            ? children
            : children.filter((catalog: Record<string, unknown>) => typeof catalog.title === 'string' && catalog.title.toLowerCase().includes(query));
        if (matched.length < 2) {
            return matched;
        }
        const locale = this._localeSel.value;
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('OfficeDocumentsExplorerPage: i18n locale required');
        }
        const direction = this._documents.state.sortDir === 'asc' ? 1 : -1;
        return [...matched].sort((left: Record<string, unknown>, right: Record<string, unknown>) => (
            direction * String(left.title).localeCompare(String(right.title), locale, { sensitivity: 'base' })
        ));
    }

    private _catalogSizeLabel(catalog: Record<string, unknown>) {
        if (typeof catalog.file_count !== 'number') {
            throw new Error('OfficeDocumentsExplorerPage: catalog.file_count required');
        }
        return this.t('catalogs.fileCount', { count: String(catalog.file_count) });
    }

    private _catalogCanDelete(catalog: Record<string, unknown>) {
        if (catalog.is_owner !== true) {
            return false;
        }
        if (typeof catalog.file_count !== 'number') {
            throw new Error('OfficeDocumentsExplorerPage: catalog.file_count required');
        }
        return catalog.file_count === 0 && this._subcatalogCount(catalog.catalog_id as string) === 0;
    }

    private _catalogItemKey(catalog: Record<string, unknown>) {
        return `catalog:${catalog.catalog_id}`;
    }

    private _subcatalogCount(catalogId: string) {
        return this._catalogItems().filter((catalog: Record<string, unknown>) => catalog.parent_catalog_id === catalogId).length;
    }

    private _catalogById(catalogId: string) {
        return this._catalogItems().find((catalog: Record<string, unknown>) => catalog.catalog_id === catalogId);
    }

    private _catalogAncestorChain(catalogId: string) {
        const cats = this._catalogItems();
        const byId = new Map(cats.map((catalog: Record<string, unknown>) => [catalog.catalog_id as string, catalog]));
        const chain: Array<Record<string, unknown>> = [];
        let currentId = catalogId;
        const visited = new Set();
        while (typeof currentId === 'string' && currentId.length > 0) {
            if (visited.has(currentId)) break;
            visited.add(currentId);
            const catalog = byId.get(currentId);
            if (!catalog) break;
            chain.unshift(catalog);
            currentId = typeof catalog.parent_catalog_id === 'string' ? catalog.parent_catalog_id : '';
        }
        return chain;
    }

    private _buildBreadcrumbs(): Array<Record<string, unknown>> {
        if (this._documents.state.explorerView !== 'catalog') return [];
        const catalogId = this._activeCatalogId();
        const crumbs: Array<Record<string, unknown>> = [{
            id: 'namespace-root',
            type: 'root',
            label: this.t('nav.allDocuments'),
            ariaLabel: this.t('breadcrumbs.root'),
            catalogId: null,
            current: catalogId.length === 0,
        }];
        for (const catalog of this._catalogAncestorChain(catalogId)) {
            crumbs.push({
                id: catalog.catalog_id,
                type: 'catalog',
                label: catalog.title,
                catalogId: catalog.catalog_id,
                current: false,
            });
        }
        if (crumbs.length > 1) {
            crumbs[crumbs.length - 1]!.current = true;
            crumbs[0]!.current = false;
        }
        return crumbs;
    }

    private _goToNamespaceRoot() {
        this._documents.setExplorerView({ explorerView: 'catalog' });
        this._documents.setActiveCatalog({ catalogId: null });
        this._documents.setFilterCatalogs({ catalogIds: [] });
        this._documents.clearFileSelection(null);
        this._lastLoadKey = '';
        this._maybeReloadDocs();
    }

    private _maybeReloadDocs() {
        const state = this._documents.state;
        if (state.searchMode === 'semantic' && state.explorerView === 'catalog') {
            return;
        }
        const explorerView = state.explorerView;
        if (explorerView === 'deleted') {
            const key = `deleted|${this._documents.state.searchQuery}`;
            if (key === this._lastLoadKey) return;
            this._lastLoadKey = key;
            this._deleted.run(null);
            return;
        }
        if (this._catalogs.loading) return;
        if (explorerView === 'recent' || explorerView === 'starred') {
            const ids = explorerView === 'recent'
                ? this._documents.state.recentFileIds
                : this._documents.state.starredFileIds;
            const catalogIds = this._catalogItems()
                .map((catalog: Record<string, unknown>) => catalog.catalog_id)
                .filter((id): id is string => typeof id === 'string' && id.length > 0);
            const key = `${explorerView}|${(ids || []).join(',')}|${catalogIds.join(',')}|${this._documents.state.searchQuery}`;
            if (key === this._lastLoadKey) return;
            this._lastLoadKey = key;
            if (catalogIds.length === 0) return;
            this._documents.run(this._listPayloadFor(catalogIds));
            return;
        }
        const catalogId = this._activeCatalogId();
        if (!catalogId) {
            const key = [
                explorerView,
                'root',
                state.searchQuery,
                state.sortKey,
                state.sortDir,
            ].join('|');
            if (key === this._lastLoadKey) return;
            this._lastLoadKey = key;
            return;
        }
        const key = [
            explorerView,
            catalogId,
            state.searchQuery,
            state.sortKey,
            state.sortDir,
        ].join('|');
        if (key === this._lastLoadKey) return;
        this._lastLoadKey = key;
        this._documents.run(this._listPayload());
    }

    private _visibleDocuments(): OfficeDocumentItem[] {
        const state = this._documents.state;
        if (state.explorerView === 'deleted') {
            const last = this._deleted.lastResult as { items?: unknown } | null;
            const deletedItems = last && Array.isArray(last.items)
                ? last.items as OfficeDocumentItem[]
                : [];
            return deletedItems;
        }
        if (this._isNamespaceRoot()) {
            return [];
        }
        let docs = state.items || [];
        if (state.explorerView === 'recent') {
            const order = new Map(
                (state.recentFileIds || []).map((id: string, index: number) => [id, index]),
            );
            docs = docs.filter((doc: OfficeDocumentItem) => order.has(doc.file_id!));
            docs.sort((a: OfficeDocumentItem, b: OfficeDocumentItem) => order.get(a.file_id!)! - order.get(b.file_id!)!);
        }
        if (state.explorerView === 'starred') {
            const starred = new Set(state.starredFileIds || []);
            docs = docs.filter((doc: OfficeDocumentItem) => starred.has(doc.file_id!));
        }
        return docs;
    }

    private _pageTitle() {
        const view = this._documents.state.explorerView;
        if (view === 'recent') return this.t('nav.recent');
        if (view === 'starred') return this.t('nav.starred');
        if (view === 'deleted') return this.t('nav.deleted');
        if (view === 'shared') return this.t('nav.shared');
        return this._activeCatalogTitle();
    }

    private _onCatalogSelect(e: CustomEvent<{ catalogId?: unknown }> | { detail: { catalogId?: unknown } }) {
        const catalogId = e.detail && e.detail.catalogId;
        if (typeof catalogId !== 'string') return;
        this._documents.setExplorerView({ explorerView: 'catalog' });
        this._documents.setActiveCatalog({ catalogId });
        this._documents.setFilterCatalogs({ catalogIds: [catalogId] });
        this._documents.setCatalogExpanded({ catalogId, expanded: true });
        this._documents.clearFileSelection(null);
        this._lastLoadKey = '';
        this._maybeReloadDocs();
    }

    private _onSubcatalogOpen(catalogId: string) {
        this._onCatalogSelect({ detail: { catalogId } });
    }

    private _onBreadcrumbNavigate(e: CustomEvent<{ crumb?: unknown }>) {
        const crumb = e.detail && e.detail.crumb;
        if (!crumb || typeof crumb !== 'object') return;
        if ((crumb as Record<string, unknown>).type === 'root') {
            this._goToNamespaceRoot();
            return;
        }
        const c = crumb as Record<string, unknown>;
        if (c.type === 'catalog') {
            this._onCatalogSelect({ detail: { catalogId: c.catalogId } });
        }
    }

    private _onCatalogEdit(catalog: Record<string, unknown>) {
        this.openModal('office.catalog_edit', {
            catalogId: catalog.catalog_id,
            title: catalog.title,
            companyVisible: Boolean(catalog.company_visible),
        });
    }

    private _onCatalogMembers(catalog: Record<string, unknown>) {
        this.openModal('office.catalog_members', {
            catalogId: catalog.catalog_id,
            catalogTitle: catalog.title,
            companyVisible: Boolean(catalog.company_visible),
        });
    }

    private _onCatalogCreateSubcatalog(catalog: Record<string, unknown>) {
        this.openModal('office.catalog_create', {
            parentCatalogId: catalog.catalog_id,
        });
    }

    private async _onCatalogDelete(catalog: Record<string, unknown>) {
        const ok = await platformConfirm(
            this.t('catalogs.deleteConfirm', { title: String(catalog.title) }),
            {
                title: this.t('catalogs.deleteConfirmTitle'),
                variant: 'danger',
                confirmText: this.t('list.delete'),
                cancelText: this.t('document_upload_modal.cancel'),
                confirmVariant: 'danger',
            },
        );
        if (ok !== true) return;
        await this._catalogs.remove(catalog.catalog_id as string);
        if (this._documents.state.selectedCatalogId === catalog.catalog_id) {
            this._documents.setSelectedCatalog({ catalogId: null });
        }
        this._lastLoadKey = '';
        this._ensureActiveCatalog();
        this._maybeReloadDocs();
    }

    private _onSearchChange(e: CustomEvent<{ searchQuery?: unknown }>) {
        const searchQuery = e.detail && typeof e.detail.searchQuery === 'string'
            ? e.detail.searchQuery
            : '';
        this._documents.setSearchQuery({ searchQuery });
        window.clearTimeout(this._searchTimer);
        this._searchTimer = window.setTimeout(() => {
            const state = this._documents.state;
            if (state.searchMode === 'semantic' && state.explorerView === 'catalog') {
                this._lastSemanticSearchKey = '';
                this._maybeRunSemanticSearch();
                return;
            }
            this._lastLoadKey = '';
            this._maybeReloadDocs();
        }, SEARCH_DEBOUNCE_MS);
    }

    private _onSearchModeChange(e: CustomEvent<{ searchMode?: unknown }>) {
        const searchMode = e.detail && e.detail.searchMode;
        if (searchMode !== 'files' && searchMode !== 'semantic') return;
        if (searchMode === 'semantic' && !this._semanticSearchAvailable()) return;
        this._documents.setSearchMode({ searchMode });
        this._lastLoadKey = '';
        this._lastSemanticSearchKey = '';
        if (searchMode === 'semantic') {
            this._maybeRunSemanticSearch();
            return;
        }
        this._maybeReloadDocs();
    }

    private _onSemanticResultOpen(e: CustomEvent<{ fileId?: unknown }>) {
        const fileId = e.detail && typeof e.detail.fileId === 'string' ? e.detail.fileId : '';
        if (fileId.length === 0) return;
        this._onOpenDocument(fileId);
    }

    private _onViewChange(e: CustomEvent<{ viewMode?: unknown }>) {
        const viewMode = e.detail && e.detail.viewMode;
        if (viewMode !== 'list' && viewMode !== 'grid') return;
        this._documents.setViewMode({ viewMode });
        this._persistViewMode(viewMode);
    }

    private _onSortChange(e: CustomEvent<{ sortKey?: unknown; sortDir?: unknown }>) {
        const sortKey = e.detail && e.detail.sortKey;
        const sortDir = e.detail && e.detail.sortDir;
        this._documents.setSort({ sortKey, sortDir });
        this._lastLoadKey = '';
        this._maybeReloadDocs();
    }

    private _openCreateEmpty() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) {
            throw new Error('OfficeDocumentsExplorerPage: catalog required to create a file');
        }
        this.openModal('office.document_create_empty', {
            catalogId,
            openAfterCreate: true,
        });
    }

    private _openUploadModal() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) {
            throw new Error('OfficeDocumentsExplorerPage: catalog required to upload a file');
        }
        this.openModal('office.document_upload', {
            catalogId,
            openAfterUpload: false,
        });
    }

    private _uploadFile(file: unknown, openAfterUpload: boolean) {
        const catalogId = this._activeCatalogId();
        if (!catalogId) {
            throw new Error('OfficeDocumentsExplorerPage: catalog required to upload a file');
        }
        if (!(file instanceof File)) {
            throw new Error('OfficeDocumentsExplorerPage: File required to upload');
        }
        const localId = `upload-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        this.dispatch(
            this._documents.op.events.UPLOAD_JOB_ADD!,
            { job: { localId, fileName: file.name, status: 'uploading', progress: 0 } },
        );
        this._upload.run({ file, catalog_id: catalogId, openAfterUpload, localId });
    }

    private _onFileDragStart(e: DragEvent, doc: OfficeDocumentItem) {
        if (!e.dataTransfer) return;
        e.dataTransfer.setData('application/x-office-file-id', doc.file_id!);
        e.dataTransfer.effectAllowed = 'move';
    }

    private _isOfficeFileDrag(dataTransfer: DataTransfer | null | undefined) {
        if (!dataTransfer || !dataTransfer.types) {
            return false;
        }
        return Array.from(dataTransfer.types).includes('application/x-office-file-id');
    }

    private _onDragOver(e: DragEvent) {
        if (this._isOfficeFileDrag(e.dataTransfer)) {
            return;
        }
        if (this._actionsDisabled()) {
            return;
        }
        e.preventDefault();
        this._dragOver = true;
    }

    private _onDragLeave(e: DragEvent) {
        e.preventDefault();
        this._dragOver = false;
    }

    private _onDrop(e: DragEvent) {
        e.preventDefault();
        this._dragOver = false;
        if (this._isOfficeFileDrag(e.dataTransfer)) {
            return;
        }
        const files = e.dataTransfer && e.dataTransfer.files
            ? Array.from(e.dataTransfer.files)
            : [];
        for (const file of files) {
            this._uploadFile(file, false);
        }
    }

    private _onCatalogDrop(e: CustomEvent<{ nativeEvent?: DragEvent }>, catalog: Record<string, unknown>) {
        const native = e.detail && e.detail.nativeEvent;
        const dataTransfer = native && native.dataTransfer ? native.dataTransfer : null;
        const fileId = dataTransfer ? dataTransfer.getData('application/x-office-file-id') : '';
        if (typeof fileId !== 'string' || fileId.length === 0) {
            return;
        }
        this._move.run({ file_id: fileId, catalog_id: catalog.catalog_id as string });
    }

    private _docByFileId(fileId: string): OfficeDocumentItem | undefined {
        const fromList = (this._documents.state.items || []).find((d: OfficeDocumentItem) => d.file_id === fileId);
        if (fromList) return fromList;
        if (this._documents.state.explorerView === 'deleted' && this._deleted.lastResult) {
            const deletedItems = (this._deleted.lastResult as { items?: unknown }).items;
            if (Array.isArray(deletedItems)) {
                return (deletedItems as OfficeDocumentItem[]).find((d: OfficeDocumentItem) => d.file_id === fileId);
            }
        }
        return undefined;
    }

    private _onOpenDocument(fileId: string) {
        if (typeof fileId !== 'string' || fileId.length === 0) return;
        const doc = this._docByFileId(fileId);
        if (doc && doc.file_availability === 'missing') {
            this.toast(this.t('list.fileMissingOpenBlocked'), { type: 'warning' });
            return;
        }
        this._documents.recordRecentOpen({ fileId });
        this.navigate('document_editor', { fileId });
    }

    private _isFileMissing(doc: OfficeDocumentItem | null | undefined) {
        return Boolean(doc && doc.file_availability === 'missing');
    }

    private _docTypeLabel(doc: OfficeDocumentItem) {
        if (this._isFileMissing(doc)) {
            return this.t('list.fileMissing');
        }
        return this.t(`list.docType.${doc.file_category}`);
    }

    private _onSelectDocument(fileId: string) {
        this._documents.setSelectedFile({ fileId });
    }

    private _onSelectCatalog(catalogId: string) {
        this._documents.setSelectedCatalog({ catalogId });
    }

    private _selectedCatalog() {
        const catalogId = this._documents.state.selectedCatalogId;
        if (typeof catalogId !== 'string' || catalogId.length === 0) {
            return null;
        }
        const catalog = this._catalogById(catalogId);
        return catalog ? catalog : null;
    }

    private _onRowSelectToggle(e: CustomEvent<{ itemKey?: unknown }>) {
        const fileId = e.detail && e.detail.itemKey;
        if (typeof fileId !== 'string') return;
        this._documents.toggleFileSelection({ fileId });
    }

    private _onSelectAllToggle(e: CustomEvent<{ selected?: unknown }>) {
        const selected = e.detail && e.detail.selected === true;
        if (selected) {
            const ids = (this._documents.state.items || []).map((d: OfficeDocumentItem) => d.file_id!);
            this._documents.setFileSelection({ fileIds: ids });
        } else {
            this._documents.clearFileSelection(null);
        }
    }

    private async _onRenameDocument(doc: OfficeDocumentItem | null | undefined) {
        if (!doc) return;
        this.openModal('office.document_rename', {
            fileId: doc.file_id,
            currentTitle: doc.title,
        });
    }

    private async _onDeleteDocument(doc: OfficeDocumentItem | null | undefined) {
        if (!doc) return;
        const isDeletedView = this._documents.state.explorerView === 'deleted';
        const ok = await platformConfirm(
            isDeletedView
                ? this.t('trash.permanentConfirm', { title: doc.title ?? '' })
                : this.t('list.deleteConfirm', { title: doc.title ?? '' }),
            {
                title: isDeletedView ? this.t('trash.permanentConfirmTitle') : this.t('list.deleteConfirmTitle'),
                variant: 'danger',
                confirmText: this.t('list.delete'),
                cancelText: this.t('document_upload_modal.cancel'),
                confirmVariant: 'danger',
            },
        );
        if (ok !== true) return;
        if (isDeletedView) {
            this._permanentDelete.run({ file_id: doc.file_id });
        } else {
            this._remove.run({ file_id: doc.file_id });
        }
        if (this._documents.state.selectedFileId === doc.file_id) {
            this._documents.clearFileSelection(null);
        }
    }

    private async _onRestoreDocument(doc: OfficeDocumentItem | null | undefined) {
        if (!doc) return;
        this._restore.run({ file_id: doc.file_id });
    }

    private async _onShareDocument(doc: OfficeDocumentItem | null | undefined) {
        if (!doc) return;
        this.openModal('office.access', {
            resourceKind: 'binding',
            resourceId: doc.file_id,
            resourceTitle: doc.title,
        });
    }

    private _onCatalogAccess(catalog: Record<string, unknown>) {
        if (!catalog) return;
        this.openModal('office.access', {
            resourceKind: 'catalog',
            resourceId: catalog.catalog_id,
            resourceTitle: catalog.title,
        });
    }

    private _onCatalogRag(catalog: Record<string, unknown> | null | undefined) {
        if (!catalog) return;
        this.openModal('office.catalog_rag', {
            catalogId: catalog.catalog_id,
            catalogTitle: catalog.title,
        });
    }

    private _handleCatalogAction(action: unknown, catalog: Record<string, unknown> | null | undefined) {
        if (!catalog || typeof action !== 'string') {
            return;
        }
        if (action === 'open') this._onSubcatalogOpen(catalog!.catalog_id as string);
        if (action === 'edit') this._onCatalogEdit(catalog);
        if (action === 'access') this._onCatalogAccess(catalog);
        if (action === 'members') this._onCatalogMembers(catalog);
        if (action === 'rag') this._onCatalogRag(catalog);
        if (action === 'create-subcatalog') this._onCatalogCreateSubcatalog(catalog);
        if (action === 'delete') void this._onCatalogDelete(catalog);
    }

    private _onCatalogRowAction(e: CustomEvent<{ action?: unknown }>, catalog: Record<string, unknown>) {
        const action = e.detail && e.detail.action;
        this._handleCatalogAction(action, catalog);
    }

    private _onFileAction(e: CustomEvent<{ action?: unknown }>, doc: OfficeDocumentItem) {
        const action = e.detail && e.detail.action;
        if (action === 'open') {
            this._onOpenDocument(doc.file_id!);
        } else if (action === 'rename') {
            void this._onRenameDocument(doc);
        } else if (action === 'delete') {
            void this._onDeleteDocument(doc);
        } else if (action === 'restore') {
            void this._onRestoreDocument(doc);
        } else if (action === 'share') {
            void this._onShareDocument(doc);
        }
    }

    private _formatDate(iso: unknown) {
        const locale = this._localeSel.value;
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('OfficeDocumentsExplorerPage: i18n locale required');
        }
        return formatPlatformDateTime(iso as string | number | Date, locale);
    }

    private _tableColumns() {
        return [
            { key: 'title', label: this.t('list.colTitle'), sortable: true },
            { key: 'file_size', label: this.t('list.colSize'), sortable: true, hideMobile: true },
            { key: 'updated_at', label: this.t('list.colUpdated'), sortable: true, hideMobile: true },
            { key: 'file_expires_at', label: this.t('list.colRetention'), hideMobile: true },
            { key: 'created_by', label: this.t('list.colAuthor'), hideMobile: true },
            { key: 'file_category', label: this.t('list.colType'), hideMobile: true },
        ];
    }

    private _retentionLabel(doc: OfficeDocumentItem) {
        const locale = this._localeSel.value;
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('OfficeDocumentsExplorerPage: i18n locale required');
        }
        if (this._isFileMissing(doc)) {
            return '—';
        }
        const expiresAt = doc.file_expires_at;
        const remaining = formatFileRetentionRemaining(expiresAt as string | null | undefined, locale);
        if (remaining === 'permanent') {
            return this.t('list.retentionPermanent');
        }
        if (remaining === 'expired') {
            return this.t('list.retentionExpired');
        }
        return remaining;
    }

    private _selectedDocument() {
        const id = this._documents.state.selectedFileId;
        if (typeof id !== 'string' || id.length === 0) return null;
        return this._docByFileId(id);
    }

    private _onDetailsAction(e: CustomEvent<{ action?: unknown }>) {
        const action = e.detail && e.detail.action;
        const doc = this._selectedDocument();
        if (doc) {
            if (action === 'open') this._onOpenDocument(doc.file_id!);
            if (action === 'rename' && !this._isFileMissing(doc)) this._onRenameDocument(doc);
            if (action === 'delete') this._onDeleteDocument(doc);
            if (action === 'restore') this._onRestoreDocument(doc);
            if (action === 'share' && !this._isFileMissing(doc)) this._onShareDocument(doc);
            if (action === 'toggle-starred') {
                this._documents.toggleStarred({ fileId: doc.file_id });
            }
            if (action === 'create-work-item') {
                this.toast(this.t('links.createWorkItem'));
            }
            if (action === 'attach-crm') {
                this.toast(this.t('links.attachCrm'));
            }
            if (action === 'open-sync') {
                this.toast(this.t('links.openSync'));
            }
            return;
        }
        const catalog = this._selectedCatalog() || this._catalogById(this._activeCatalogId());
        this._handleCatalogAction(action, catalog);
    }

    private _openMobileCatalogPicker() {
        this.openBottomSheet('office.catalog_picker');
    }

    private _renderUploadJobs() {
        const jobs = this._documents.state.uploadJobs;
        if (!Array.isArray(jobs) || jobs.length === 0) return '';
        return html`
            <div class="upload-jobs">
                ${jobs.map((job: Record<string, unknown>) => html`
                    <div class="upload-job ${job.status}">
                        <platform-icon name="paperclip" size="16"></platform-icon>
                        <span>${job.fileName}</span>
                        <span>${this.t(`explorer.upload.${job.status}`)}</span>
                    </div>
                `)}
            </div>
        `;
    }

    private _renderCatalogKebab(catalog: Record<string, unknown>) {
        return html`
            <office-catalog-actions-menu
                slot="actions"
                ?is-owner=${catalog.is_owner === true}
                ?show-members=${catalog.is_owner === true && catalog.company_visible !== true}
                ?can-delete=${this._catalogCanDelete(catalog)}
                @action=${(e: CustomEvent<{ action?: unknown }>) => this._onCatalogRowAction(e, catalog)}
            ></office-catalog-actions-menu>
        `;
    }

    private _renderCatalogRow(catalog: Record<string, unknown>) {
        const state = this._documents.state;
        const ragHint = catalog.rag_index_enabled === true;
        return html`
            <platform-file-row
                item-kind="catalog"
                item-key=${this._catalogItemKey(catalog)}
                file-name=${catalog.title as string}
                size-label=${this._catalogSizeLabel(catalog)}
                date-label="—"
                retention-label="—"
                type-label=${this.t('list.docType.catalog')}
                author-user-id=${catalog.owner_user_id as string}
                hint-icon=${ragHint ? 'search' : ''}
                hint-icon-label=${ragHint ? this.t('catalog_context_menu.rag') : ''}
                ?selected=${state.selectedCatalogId === catalog.catalog_id}
                @open=${() => this._onSelectCatalog(catalog.catalog_id as string)}
                @activate=${() => this._onSubcatalogOpen(catalog.catalog_id as string)}
                @row-drop=${(e: CustomEvent<{ nativeEvent?: DragEvent }>) => this._onCatalogDrop(e, catalog)}
            >
                ${this._renderCatalogKebab(catalog)}
            </platform-file-row>
        `;
    }

    private _renderCatalogCard(catalog: Record<string, unknown>) {
        const state = this._documents.state;
        const ragHint = catalog.rag_index_enabled === true;
        return html`
            <platform-file-card
                item-kind="catalog"
                item-key=${this._catalogItemKey(catalog)}
                file-name=${catalog.title as string}
                size-label=${this._catalogSizeLabel(catalog)}
                type-label=${this.t('list.docType.catalog')}
                hint-icon=${ragHint ? 'search' : ''}
                hint-icon-label=${ragHint ? this.t('catalog_context_menu.rag') : ''}
                ?selected=${state.selectedCatalogId === catalog.catalog_id}
                @open=${() => this._onSelectCatalog(catalog.catalog_id as string)}
                @activate=${() => this._onSubcatalogOpen(catalog.catalog_id as string)}
                @row-drop=${(e: CustomEvent<{ nativeEvent?: DragEvent }>) => this._onCatalogDrop(e, catalog)}
            >
                ${this._renderCatalogKebab(catalog)}
            </platform-file-card>
        `;
    }

    private _renderList(docs: OfficeDocumentItem[]) {
        const state = this._documents.state;
        const selectedIds = new Set(Array.isArray(state.selectedFileIds) ? state.selectedFileIds : []);
        const allSelected = docs.length > 0 && docs.every((d: OfficeDocumentItem) => selectedIds.has(d.file_id!));
        const childCatalogs = this._visibleChildCatalogs();
        return html`
            <platform-file-table
                .columns=${this._tableColumns()}
                sort-key=${state.sortKey}
                sort-dir=${state.sortDir}
                selectable
                ?all-selected=${allSelected}
                aria-label=${this.t('list.tableAria')}
                @sort-change=${this._onSortChange}
                @select-all-toggle=${this._onSelectAllToggle}
            >
                ${repeat(childCatalogs, (catalog: Record<string, unknown>) => this._catalogItemKey(catalog), (catalog: Record<string, unknown>) => this._renderCatalogRow(catalog))}
                ${repeat(docs, (doc: OfficeDocumentItem) => doc.file_id, (doc: OfficeDocumentItem) => html`
                    <platform-file-row
                        item-key=${doc.file_id}
                        file-name=${doc.title}
                        file-size=${doc.file_size}
                        date-label=${this._formatDate(doc.updated_at)}
                        retention-label=${this._retentionLabel(doc)}
                        type-label=${this._docTypeLabel(doc)}
                        author-user-id=${doc.created_by_user_id}
                        index-status=${typeof doc.rag_index_status === 'string' ? doc.rag_index_status : ''}
                        index-status-label=${this._ragIndexStatusLabel(doc.rag_index_status)}
                        ?selected=${state.selectedFileId === doc.file_id || selectedIds.has(doc.file_id!)}
                        selectable
                        ?draggable=${!this._isFileMissing(doc)}
                        @row-dragstart=${(e: CustomEvent<{ nativeEvent?: DragEvent }>) => this._onFileDragStart(e.detail.nativeEvent!, doc)}
                        @open=${() => this._onSelectDocument(doc.file_id!)}
                        @activate=${() => this._onOpenDocument(doc.file_id!)}
                        @select-toggle=${this._onRowSelectToggle}
                    >
                        <office-file-actions-menu
                            slot="actions"
                            ?file-missing=${this._isFileMissing(doc)}
                            @action=${(e: CustomEvent<{ action?: unknown }>) => this._onFileAction(e, doc)}
                        ></office-file-actions-menu>
                    </platform-file-row>
                `)}
            </platform-file-table>
        `;
    }

    private _renderGrid(docs: OfficeDocumentItem[]) {
        const state = this._documents.state;
        const childCatalogs = this._visibleChildCatalogs();
        return html`
            <div class="grid" aria-label=${this.t('list.cardsAria')}>
                ${repeat(childCatalogs, (catalog: Record<string, unknown>) => this._catalogItemKey(catalog), (catalog: Record<string, unknown>) => this._renderCatalogCard(catalog))}
                ${repeat(docs, (doc: OfficeDocumentItem) => doc.file_id, (doc: OfficeDocumentItem) => html`
                    <platform-file-card
                        item-key=${doc.file_id}
                        file-name=${doc.title}
                        file-size=${doc.file_size}
                        date-label=${this._formatDate(doc.updated_at)}
                        retention-label=${this._retentionLabel(doc)}
                        type-label=${this._docTypeLabel(doc)}
                        index-status=${typeof doc.rag_index_status === 'string' ? doc.rag_index_status : ''}
                        index-status-label=${this._ragIndexStatusLabel(doc.rag_index_status)}
                        ?selected=${state.selectedFileId === doc.file_id}
                        @open=${() => this._onSelectDocument(doc.file_id!)}
                        @activate=${() => this._onOpenDocument(doc.file_id!)}
                    >
                        <office-file-actions-menu
                            slot="actions"
                            ?file-missing=${this._isFileMissing(doc)}
                            @action=${(e: CustomEvent<{ action?: unknown }>) => this._onFileAction(e, doc)}
                        ></office-file-actions-menu>
                    </platform-file-card>
                `)}
            </div>
        `;
    }

    private _renderEmptyNamespaceRoot() {
        return html`
            <div class="dropzone-panel" role="status" aria-label=${this.t('explorer.rootAria')}>
                <div class="dropzone-icon"><platform-icon name="folder" size="64"></platform-icon></div>
                <div class="dropzone-title">${this.t('explorer.rootEmptyTitle')}</div>
                <div class="dropzone-hint">${this.t('explorer.rootEmptyHint')}</div>
                <div class="dropzone-actions">
                    <button class="btn btn-primary" type="button" @click=${() => this.openModal('office.catalog_create')}>
                        ${this.t('catalogs.create')}
                    </button>
                </div>
            </div>
        `;
    }

    private _renderEmptyNoDocuments() {
        return html`
            <div class="dropzone-panel ${this._dragOver ? 'drag-over' : ''}">
                <div class="dropzone-icon"><platform-icon name="cloud" size="64"></platform-icon></div>
                <div class="dropzone-title">${this.t('list.emptyStateTitle')}</div>
                <div class="dropzone-hint">${this.t('explorer.emptyDropHint')}</div>
                <div class="dropzone-actions">
                    <button class="btn btn-primary" type="button"
                            ?disabled=${this._actionsDisabled()}
                            @click=${this._openUploadModal}>
                        ${this.t('list.upload')}
                    </button>
                    <button class="btn" type="button"
                            ?disabled=${this._actionsDisabled()}
                            @click=${this._openCreateEmpty}>
                        ${this.t('list.newEmpty')}
                    </button>
                </div>
            </div>
        `;
    }

    private _actionsDisabled() {
        const integrationConfigured = this._integration.lastResult
            ? Boolean((this._integration.lastResult as Record<string, unknown>).configured)
            : true;
        return !integrationConfigured || !this._activeCatalogId();
    }

    private _renderEmptyNoCatalogs() {
        return html`
            <div class="dropzone-panel">
                <div class="dropzone-icon"><platform-icon name="folder" size="64"></platform-icon></div>
                <div class="dropzone-title">${this.t('list.noCatalogsStateTitle')}</div>
                <div class="dropzone-hint">${this.t('list.noCatalogsStateHint')}</div>
                <div class="dropzone-actions">
                    <button class="btn btn-primary" type="button" @click=${() => this.openModal('office.catalog_create')}>
                        ${this.t('catalogs.create')}
                    </button>
                </div>
            </div>
        `;
    }

    private _renderBulkBar(selectedCount: number) {
        if (selectedCount === 0) return '';
        return html`
            <div class="bulk-bar">
                <span>${this.t('bulk.selected', { count: selectedCount })}</span>
                <div class="bulk-actions">
                    <button class="btn btn-danger" type="button" @click=${() => this._bulkDelete()}>
                        ${this.t('list.delete')}
                    </button>
                </div>
            </div>
        `;
    }

    private async _bulkDelete() {
        const state = this._documents.state;
        const ids = Array.isArray(state.selectedFileIds) ? state.selectedFileIds : [];
        for (const fileId of ids) {
            const doc = this._docByFileId(fileId);
            if (doc) {
                await this._onDeleteDocument(doc);
            }
        }
        this._documents.clearFileSelection(null);
    }

    override render(): TemplateResult {
        const cats = this._catalogItems();
        const noCatalogs = !this._catalogs.loading && cats.length === 0;
        const state = this._documents.state;
        const docs = this._visibleDocuments();
        const actionsDisabled = this._actionsDisabled();
        // Spinner только при первой загрузке пустого списка — soft-refresh не прячет таблицу.
        const selectedDoc = this._selectedDocument();
        const selectedCatalog = this._selectedCatalog();
        const selectedCount = Array.isArray(state.selectedFileIds) ? state.selectedFileIds.length : 0;
        const activeCatalog = this._catalogById(this._activeCatalogId());
        const detailsCatalog = selectedCatalog || activeCatalog;
        const breadcrumbs = this._buildBreadcrumbs();
        const childCatalogs = this._visibleChildCatalogs();
        const atRoot = this._isNamespaceRoot();
        const showSemanticResults = this._showSemanticResults();
        const semanticSearchAvailable = this._semanticSearchAvailable();
        const docsLoading = state.explorerView === 'deleted'
            ? (this._deleted.busy && docs.length === 0)
            : (this._documents.busy && docs.length === 0 && childCatalogs.length === 0);
        const showEmpty = !showSemanticResults && !docsLoading && docs.length === 0 && childCatalogs.length === 0;
        const subcatalogCount = detailsCatalog ? this._subcatalogCount(detailsCatalog.catalog_id as string) : 0;

        return html`
            <div class="explorer-banner">
                <office-integration-banner></office-integration-banner>
            </div>
            ${this._dragOver ? html`
                <div class="drop-overlay">
                    <div class="drop-overlay-inner">
                        <platform-icon name="cloud" size="40"></platform-icon>
                        <span>${this.t('explorer.dropOverlay')}</span>
                    </div>
                </div>
            ` : ''}
            <div class="page-body"
                 @dragover=${this._onDragOver}
                 @dragleave=${this._onDragLeave}
                 @drop=${this._onDrop}>
                ${noCatalogs ? html`
                    <div class="main-pane">
                        <div class="main-content">${this._renderEmptyNoCatalogs()}</div>
                    </div>
                ` : html`
                    <div class="main-pane">
                        <button class="btn mobile-catalog-btn" type="button" @click=${this._openMobileCatalogPicker}>
                            <platform-icon name="folder" size="16"></platform-icon>
                            ${this._pageTitle()}
                        </button>
                        <div class="main-toolbar">
                            <office-file-toolbar
                                page-title=${this._pageTitle()}
                                search-query=${state.searchQuery}
                                search-mode=${state.searchMode}
                                ?semantic-search-available=${semanticSearchAvailable}
                                view-mode=${state.viewMode}
                                ?actions-disabled=${actionsDisabled}
                                ?show-breadcrumbs=${breadcrumbs.length > 0}
                                .breadcrumbs=${breadcrumbs}
                                @search-change=${this._onSearchChange}
                                @search-mode-change=${this._onSearchModeChange}
                                @view-change=${this._onViewChange}
                                @upload=${this._openUploadModal}
                                @create-empty=${this._openCreateEmpty}
                                @refresh=${() => { this._lastLoadKey = ''; this._maybeReloadDocs(); }}
                                @breadcrumb-navigate=${this._onBreadcrumbNavigate}
                            ></office-file-toolbar>
                        </div>
                        <div class="main-content">
                            ${this._renderUploadJobs()}
                            ${this._renderBulkBar(selectedCount)}
                            <div class="content-row">
                                <div class="files-area ${showEmpty ? 'dropzone-empty' : ''}">
                                    ${showSemanticResults ? html`
                                        <office-catalog-semantic-search-results
                                            .items=${this._semanticSearchItems()}
                                            .query=${state.searchQuery}
                                            ?loading=${this._catalogRagSearch.busy}
                                            @result-open=${this._onSemanticResultOpen}
                                        ></office-catalog-semantic-search-results>
                                    ` : html`
                                        ${docsLoading ? html`<div class="loading"><glass-spinner size="lg"></glass-spinner></div>` : ''}
                                        ${showEmpty ? (atRoot ? this._renderEmptyNamespaceRoot() : this._renderEmptyNoDocuments()) : ''}
                                        ${!docsLoading && (docs.length > 0 || childCatalogs.length > 0)
                                            ? (state.viewMode === 'grid'
                                                ? this._renderGrid(docs)
                                                : this._renderList(docs))
                                            : ''}
                                    `}
                                </div>
                                <office-file-details-panel
                                    .document=${selectedDoc}
                                    .catalog=${activeCatalog}
                                    .selectedCatalog=${selectedCatalog}
                                    catalog-title=${this._activeCatalogTitle()}
                                    subcatalog-count=${subcatalogCount}
                                    explorer-view=${state.explorerView}
                                    ?namespace-root=${atRoot && !selectedCatalog}
                                    ?starred=${Boolean(selectedDoc && selectedDoc.file_id && (state.starredFileIds || []).includes(selectedDoc.file_id))}
                                    @close=${() => this._documents.clearFileSelection(null)}
                                    @action=${this._onDetailsAction}
                                ></office-file-details-panel>
                            </div>
                        </div>
                    </div>
                `}
            </div>
        `;
    }
}

customElements.define('office-documents-explorer-page', OfficeDocumentsExplorerPage);
