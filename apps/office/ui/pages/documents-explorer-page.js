/**
 * OfficeDocumentsExplorerPage — file explorer (Untitled UI pattern).
 *
 * Маршрут `/documents`. Дерево каталогов + toolbar + list/grid + details panel.
 */

import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { documentsExplorerStyles } from '../styles/documents-explorer.styles.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-file-table.js';
import '@platform/lib/components/platform-file-row.js';
import '@platform/lib/components/platform-file-card.js';
import '../components/office-integration-banner.js';
import '../components/office-file-toolbar.js';
import '../components/office-file-details-panel.js';
import '../components/office-file-actions-menu.js';
import '../components/office-catalog-semantic-search-results.js';

const VIEW_MODE_STORAGE_KEY = 'documents_explorer_view_mode';
const SEARCH_DEBOUNCE_MS = 300;

export class OfficeDocumentsExplorerPage extends PlatformPage {
    static i18nNamespace = 'documents';

    static properties = {
        initialExplorerView: { type: String, attribute: false },
        _dragOver: { state: true },
        _searchDebounceTimer: { state: false },
    };

    static styles = [
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
        this._documents = this.useOp('office/documents');
        this._deleted = this.useOp('office/documents_deleted');
        this._upload = this.useOp('office/document_upload');
        this._remove = this.useOp('office/document_remove');
        this._restore = this.useOp('office/document_restore');
        this._permanentDelete = this.useOp('office/document_permanent_delete');
        this._shareCreate = this.useOp('office/document_share_create');
        this._catalogRagSearch = this.useOp('office/catalog_rag_search');
        this._lastLoadKey = '';
        this._lastSemanticSearchKey = '';
        this._localeSel = this.select((s) => s.i18n.locale);
    }

    connectedCallback() {
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

    _restoreViewMode() {
        const raw = window.localStorage.getItem(platformStorageKey('office', VIEW_MODE_STORAGE_KEY));
        if (raw === 'list' || raw === 'grid') {
            this._documents.setViewMode({ viewMode: raw });
        }
    }

    _persistViewMode(mode) {
        if (mode !== 'list' && mode !== 'grid') return;
        window.localStorage.setItem(platformStorageKey('office', VIEW_MODE_STORAGE_KEY), mode);
    }

    _onNamespaceReload() {
        this._lastLoadKey = '';
        this._documents.clearFilter(null);
        this._documents.setSearchQuery({ searchQuery: '' });
        this._documents.clearBindingSelection(null);
        this._catalogs.load();
    }

    updated(changed) {
        super.updated && super.updated(changed);
        this._ensureSearchMode();
        this._maybeReloadDocs();
        this._maybeRunSemanticSearch();
        this._ensureActiveCatalog();
    }

    _semanticSearchAvailable() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) return false;
        const catalogs = this._catalogItems();
        const active = catalogs.find((item) => item.catalog_id === catalogId);
        if (!active) return false;
        return active.rag_index_enabled === true;
    }

    _ensureSearchMode() {
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

    _maybeRunSemanticSearch() {
        const state = this._documents.state;
        if (state.explorerView !== 'catalog') return;
        if (state.searchMode !== 'semantic') return;
        const catalogId = this._activeCatalogId();
        const query = typeof state.searchQuery === 'string' ? state.searchQuery.trim() : '';
        if (!catalogId || query.length === 0) return;
        const key = `${catalogId}|${query}`;
        if (key === this._lastSemanticSearchKey) return;
        this._lastSemanticSearchKey = key;
        this._catalogRagSearch.run({ catalogId, query, limit: 20 });
    }

    _semanticSearchItems() {
        const result = this._catalogRagSearch.lastResult;
        if (!result || typeof result !== 'object' || !Array.isArray(result.items)) {
            return [];
        }
        return result.items;
    }

    _showSemanticResults() {
        const state = this._documents.state;
        if (state.explorerView !== 'catalog') return false;
        if (state.searchMode !== 'semantic') return false;
        return typeof state.searchQuery === 'string' && state.searchQuery.trim().length > 0;
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

    _activeCatalogTitle() {
        const id = this._activeCatalogId();
        const hit = this._catalogItems().find((c) => c.catalog_id === id);
        return hit ? hit.title : this.t('list.catalogUnknown');
    }

    _ensureActiveCatalog() {
        if (this._catalogs.loading) return;
        const cats = this._catalogItems();
        if (cats.length === 0) return;
        const active = this._documents.state.activeCatalogId;
        if (typeof active === 'string' && active.length > 0) {
            const exists = cats.some((c) => c.catalog_id === active);
            if (exists) return;
        }
        this._documents.setActiveCatalog({ catalogId: cats[0].catalog_id });
        this._documents.setFilterCatalogs({ catalogIds: [cats[0].catalog_id] });
    }

    _listPayload() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) {
            throw new Error('OfficeDocumentsExplorerPage: active catalog required');
        }
        const state = this._documents.state;
        return {
            catalogIds: [catalogId],
            q: state.searchQuery,
            sortKey: state.sortKey,
            sortDir: state.sortDir,
        };
    }

    _childCatalogsAtCurrentLevel() {
        if (this._documents.state.explorerView !== 'catalog') return [];
        const catalogId = this._activeCatalogId();
        return this._catalogItems().filter((catalog) => {
            const parentId = typeof catalog.parent_catalog_id === 'string' ? catalog.parent_catalog_id : '';
            return parentId === catalogId;
        });
    }

    _subcatalogCount(catalogId) {
        return this._catalogItems().filter((catalog) => catalog.parent_catalog_id === catalogId).length;
    }

    _catalogById(catalogId) {
        return this._catalogItems().find((catalog) => catalog.catalog_id === catalogId);
    }

    _catalogAncestorChain(catalogId) {
        const cats = this._catalogItems();
        const byId = new Map(cats.map((catalog) => [catalog.catalog_id, catalog]));
        const chain = [];
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

    _buildBreadcrumbs() {
        if (this._documents.state.explorerView !== 'catalog') return [];
        const catalogId = this._activeCatalogId();
        if (!catalogId) return [];
        const crumbs = [];
        for (const catalog of this._catalogAncestorChain(catalogId)) {
            crumbs.push({
                id: catalog.catalog_id,
                type: 'catalog',
                label: catalog.title,
                catalogId: catalog.catalog_id,
                current: false,
            });
        }
        if (crumbs.length === 0) return [];
        crumbs[crumbs.length - 1].current = true;
        return crumbs;
    }

    _maybeReloadDocs() {
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
                ? this._documents.state.recentBindingIds
                : this._documents.state.starredBindingIds;
            const key = `${explorerView}|${(ids || []).join(',')}|${this._documents.state.searchQuery}`;
            if (key === this._lastLoadKey) return;
            this._lastLoadKey = key;
            const catalogId = this._activeCatalogId();
            if (!catalogId) return;
            this._documents.run(this._listPayload());
            return;
        }
        const catalogId = this._activeCatalogId();
        if (!catalogId) return;
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

    _visibleDocuments() {
        const state = this._documents.state;
        if (state.explorerView === 'deleted') {
            const deletedItems = this._deleted.lastResult && Array.isArray(this._deleted.lastResult.items)
                ? this._deleted.lastResult.items
                : [];
            return deletedItems;
        }
        let docs = state.items;
        if (state.explorerView === 'recent') {
            const order = new Map(
                (state.recentBindingIds || []).map((id, index) => [id, index]),
            );
            docs = docs.filter((doc) => order.has(doc.binding_id));
            docs.sort((a, b) => order.get(a.binding_id) - order.get(b.binding_id));
        }
        if (state.explorerView === 'starred') {
            const starred = new Set(state.starredBindingIds || []);
            docs = docs.filter((doc) => starred.has(doc.binding_id));
        }
        return docs;
    }

    _pageTitle() {
        const view = this._documents.state.explorerView;
        if (view === 'recent') return this.t('nav.recent');
        if (view === 'starred') return this.t('nav.starred');
        if (view === 'deleted') return this.t('nav.deleted');
        if (view === 'shared') return this.t('nav.shared');
        return this._activeCatalogTitle();
    }

    _onCatalogSelect(e) {
        const catalogId = e.detail && e.detail.catalogId;
        if (typeof catalogId !== 'string') return;
        this._documents.setExplorerView({ explorerView: 'catalog' });
        this._documents.setActiveCatalog({ catalogId });
        this._documents.setFilterCatalogs({ catalogIds: [catalogId] });
        this._documents.setCatalogExpanded({ catalogId, expanded: true });
        this._documents.clearBindingSelection(null);
        this._lastLoadKey = '';
        this._maybeReloadDocs();
    }

    _onSubcatalogOpen(catalogId) {
        this._onCatalogSelect({ detail: { catalogId } });
    }

    _onBreadcrumbNavigate(e) {
        const crumb = e.detail && e.detail.crumb;
        if (!crumb || typeof crumb !== 'object') return;
        if (crumb.type === 'catalog') {
            this._onCatalogSelect({ detail: { catalogId: crumb.catalogId } });
        }
    }

    _onCatalogEdit(catalog) {
        this.openModal('office.catalog_edit', {
            catalogId: catalog.catalog_id,
            title: catalog.title,
            isPublic: Boolean(catalog.is_public),
        });
    }

    _onCatalogMembers(catalog) {
        this.openModal('office.catalog_members', {
            catalogId: catalog.catalog_id,
            catalogTitle: catalog.title,
            isPublic: Boolean(catalog.is_public),
        });
    }

    _onCatalogCreateSubcatalog(catalog) {
        this.openModal('office.catalog_create', {
            parentCatalogId: catalog.catalog_id,
        });
    }

    async _onCatalogDelete(catalog) {
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
        if (ok !== true) return;
        await this._catalogs.remove(catalog.catalog_id);
        this._lastLoadKey = '';
        this._ensureActiveCatalog();
        this._maybeReloadDocs();
    }

    _onSearchChange(e) {
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

    _onSearchModeChange(e) {
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

    _onSemanticResultOpen(e) {
        const bindingId = e.detail && typeof e.detail.bindingId === 'string' ? e.detail.bindingId : '';
        if (bindingId.length === 0) return;
        this._onOpenDocument(bindingId);
    }

    _onViewChange(e) {
        const viewMode = e.detail && e.detail.viewMode;
        if (viewMode !== 'list' && viewMode !== 'grid') return;
        this._documents.setViewMode({ viewMode });
        this._persistViewMode(viewMode);
    }

    _onSortChange(e) {
        const sortKey = e.detail && e.detail.sortKey;
        const sortDir = e.detail && e.detail.sortDir;
        this._documents.setSort({ sortKey, sortDir });
        this._lastLoadKey = '';
        this._maybeReloadDocs();
    }

    _openCreateEmpty() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) return;
        this.openModal('office.document_create_empty', {
            catalogId,
            openAfterCreate: true,
        });
    }

    _openUploadModal() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) return;
        this.openModal('office.document_upload', {
            catalogId,
            openAfterUpload: false,
        });
    }

    _uploadFile(file, openAfterUpload) {
        const catalogId = this._activeCatalogId();
        if (!catalogId || !(file instanceof File)) return;
        const localId = `upload-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        this.dispatch(
            this._documents.op.events.UPLOAD_JOB_ADD,
            { job: { localId, fileName: file.name, status: 'uploading', progress: 0 } },
        );
        this._upload.run({ file, catalogId, openAfterUpload, localId });
    }

    _onFileDragStart(e, doc) {
        if (!e.dataTransfer) return;
        e.dataTransfer.setData('application/x-office-binding-id', doc.binding_id);
        e.dataTransfer.effectAllowed = 'move';
    }

    _onDragOver(e) {
        e.preventDefault();
        this._dragOver = true;
    }

    _onDragLeave(e) {
        e.preventDefault();
        this._dragOver = false;
    }

    _onDrop(e) {
        e.preventDefault();
        this._dragOver = false;
        const files = e.dataTransfer && e.dataTransfer.files
            ? Array.from(e.dataTransfer.files)
            : [];
        for (const file of files) {
            this._uploadFile(file, false);
        }
    }

    _docByBindingId(bindingId) {
        const fromList = this._documents.state.items.find((d) => d.binding_id === bindingId);
        if (fromList) return fromList;
        if (this._documents.state.explorerView === 'deleted' && this._deleted.lastResult) {
            const deletedItems = this._deleted.lastResult.items;
            if (Array.isArray(deletedItems)) {
                return deletedItems.find((d) => d.binding_id === bindingId);
            }
        }
        return undefined;
    }

    _onOpenDocument(bindingId) {
        if (typeof bindingId !== 'string' || bindingId.length === 0) return;
        this._documents.recordRecentOpen({ bindingId });
        this.navigate('document_editor', { bindingId });
    }

    _onSelectDocument(bindingId) {
        this._documents.setSelectedBinding({ bindingId });
    }

    _onRowSelectToggle(e) {
        const bindingId = e.detail && e.detail.itemKey;
        if (typeof bindingId !== 'string') return;
        this._documents.toggleBindingSelection({ bindingId });
    }

    _onSelectAllToggle(e) {
        const selected = e.detail && e.detail.selected === true;
        if (selected) {
            const ids = this._documents.state.items.map((d) => d.binding_id);
            this._documents.setBindingSelection({ bindingIds: ids });
        } else {
            this._documents.clearBindingSelection(null);
        }
    }

    async _onRenameDocument(doc) {
        if (!doc) return;
        this.openModal('office.document_rename', {
            bindingId: doc.binding_id,
            currentTitle: doc.title,
            catalogIds: [doc.catalog_id],
        });
    }

    async _onDeleteDocument(doc) {
        if (!doc) return;
        const isDeletedView = this._documents.state.explorerView === 'deleted';
        const ok = await platformConfirm(
            isDeletedView
                ? this.t('trash.permanentConfirm', { title: doc.title })
                : this.t('list.deleteConfirm', { title: doc.title }),
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
            this._permanentDelete.run({ bindingId: doc.binding_id });
        } else {
            this._remove.run({
                bindingId: doc.binding_id,
                catalogIds: [doc.catalog_id],
            });
        }
        if (this._documents.state.selectedBindingId === doc.binding_id) {
            this._documents.setSelectedBinding({ bindingId: null });
        }
    }

    async _onRestoreDocument(doc) {
        if (!doc) return;
        this._restore.run({ bindingId: doc.binding_id });
    }

    async _onShareDocument(doc) {
        if (!doc) return;
        this.openModal('office.access', {
            resourceKind: 'binding',
            resourceId: doc.binding_id,
            resourceTitle: doc.title,
        });
    }

    _onCatalogAccess(catalog) {
        if (!catalog) return;
        this.openModal('office.access', {
            resourceKind: 'catalog',
            resourceId: catalog.catalog_id,
            resourceTitle: catalog.title,
        });
    }

    _onFileAction(e, doc) {
        const action = e.detail && e.detail.action;
        if (action === 'open') {
            this._onOpenDocument(doc.binding_id);
        } else if (action === 'rename') {
            this._onRenameDocument(doc);
        } else if (action === 'delete') {
            this._onDeleteDocument(doc);
        } else if (action === 'restore') {
            this._onRestoreDocument(doc);
        } else if (action === 'share') {
            this._onShareDocument(doc);
        }
    }

    _formatDate(iso) {
        const locale = this._localeSel.value;
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('OfficeDocumentsExplorerPage: i18n locale required');
        }
        return formatPlatformDateTime(iso, locale);
    }

    _tableColumns() {
        return [
            { key: 'title', label: this.t('list.colTitle'), sortable: true },
            { key: 'file_size', label: this.t('list.colSize'), sortable: true, hideMobile: true },
            { key: 'updated_at', label: this.t('list.colUpdated'), sortable: true, hideMobile: true },
            { key: 'created_by', label: this.t('list.colAuthor'), hideMobile: true },
            { key: 'file_category', label: this.t('list.colType'), hideMobile: true },
        ];
    }

    _selectedDocument() {
        const id = this._documents.state.selectedBindingId;
        if (typeof id !== 'string' || id.length === 0) return null;
        return this._docByBindingId(id);
    }

    _onDetailsAction(e) {
        const action = e.detail && e.detail.action;
        const doc = this._selectedDocument();
        if (doc) {
            if (action === 'open') this._onOpenDocument(doc.binding_id);
            if (action === 'rename') this._onRenameDocument(doc);
            if (action === 'delete') this._onDeleteDocument(doc);
            if (action === 'restore') this._onRestoreDocument(doc);
            if (action === 'share') this._onShareDocument(doc);
            if (action === 'toggle-starred') {
                this._documents.toggleStarred({ bindingId: doc.binding_id });
            }
            if (action === 'create-work-item') {
                this.toast(this.t('links.createWorkItem'), { variant: 'info' });
            }
            if (action === 'attach-crm') {
                this.toast(this.t('links.attachCrm'), { variant: 'info' });
            }
            if (action === 'open-sync') {
                this.toast(this.t('links.openSync'), { variant: 'info' });
            }
            return;
        }
        const catalog = this._catalogById(this._activeCatalogId());
        if (!catalog) return;
        if (action === 'catalog-edit') this._onCatalogEdit(catalog);
        if (action === 'catalog-access') this._onCatalogAccess(catalog);
        if (action === 'catalog-members') this._onCatalogMembers(catalog);
        if (action === 'catalog-access') this._onCatalogAccess(catalog);
        if (action === 'catalog-create-subcatalog') this._onCatalogCreateSubcatalog(catalog);
        if (action === 'catalog-delete') this._onCatalogDelete(catalog);
    }

    _openMobileCatalogPicker() {
        this.openBottomSheet('office.catalog_picker');
    }

    _renderUploadJobs() {
        const jobs = this._documents.state.uploadJobs;
        if (!Array.isArray(jobs) || jobs.length === 0) return '';
        return html`
            <div class="upload-jobs">
                ${jobs.map((job) => html`
                    <div class="upload-job ${job.status}">
                        <platform-icon name="paperclip" size="16"></platform-icon>
                        <span>${job.fileName}</span>
                        <span>${this.t(`explorer.upload.${job.status}`)}</span>
                    </div>
                `)}
            </div>
        `;
    }

    _renderSubcatalogRows(subcatalogs) {
        if (!Array.isArray(subcatalogs) || subcatalogs.length === 0) return '';
        return html`
            <div class="folder-rows">
                ${subcatalogs.map((catalog) => html`
                    <button
                        class="folder-row"
                        type="button"
                        @click=${() => this._onSubcatalogOpen(catalog.catalog_id)}
                    >
                        <platform-icon name="folder" size="16"></platform-icon>
                        <span class="folder-row-label">${catalog.title}</span>
                    </button>
                `)}
            </div>
        `;
    }

    _renderList(docs) {
        const state = this._documents.state;
        const selectedIds = new Set(Array.isArray(state.selectedBindingIds) ? state.selectedBindingIds : []);
        const allSelected = docs.length > 0 && docs.every((d) => selectedIds.has(d.binding_id));
        const childCatalogs = this._childCatalogsAtCurrentLevel();
        return html`
            ${this._renderSubcatalogRows(childCatalogs)}
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
                ${docs.map((doc) => html`
                    <platform-file-row
                        item-key=${doc.binding_id}
                        file-name=${doc.title}
                        file-size=${doc.file_size}
                        date-label=${this._formatDate(doc.updated_at)}
                        type-label=${this.t(`list.docType.${doc.file_category}`)}
                        author-user-id=${doc.created_by_user_id}
                        ?selected=${state.selectedBindingId === doc.binding_id || selectedIds.has(doc.binding_id)}
                        selectable
                        draggable
                        @row-dragstart=${(e) => this._onFileDragStart(e.detail.nativeEvent, doc)}
                        @open=${() => this._onSelectDocument(doc.binding_id)}
                        @select-toggle=${this._onRowSelectToggle}
                    >
                        <office-file-actions-menu
                            slot="actions"
                            @action=${(e) => this._onFileAction(e, doc)}
                        ></office-file-actions-menu>
                    </platform-file-row>
                `)}
            </platform-file-table>
        `;
    }

    _renderGrid(docs) {
        const state = this._documents.state;
        return html`
            <div class="grid" aria-label=${this.t('list.cardsAria')}>
                ${docs.map((doc) => html`
                    <platform-file-card
                        item-key=${doc.binding_id}
                        file-name=${doc.title}
                        file-size=${doc.file_size}
                        date-label=${this._formatDate(doc.updated_at)}
                        type-label=${this.t(`list.docType.${doc.file_category}`)}
                        ?selected=${state.selectedBindingId === doc.binding_id}
                        @open=${() => this._onSelectDocument(doc.binding_id)}
                    >
                        <office-file-actions-menu
                            slot="actions"
                            @action=${(e) => this._onFileAction(e, doc)}
                        ></office-file-actions-menu>
                    </platform-file-card>
                `)}
            </div>
        `;
    }

    _renderEmptyNoDocuments() {
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

    _actionsDisabled() {
        const integrationConfigured = this._integration.lastResult
            ? Boolean(this._integration.lastResult.configured)
            : true;
        return !integrationConfigured || !this._activeCatalogId();
    }

    _renderEmptyNoCatalogs() {
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

    _renderBulkBar(selectedCount) {
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

    async _bulkDelete() {
        const state = this._documents.state;
        const ids = Array.isArray(state.selectedBindingIds) ? state.selectedBindingIds : [];
        for (const bindingId of ids) {
            const doc = this._docByBindingId(bindingId);
            if (doc) {
                await this._onDeleteDocument(doc);
            }
        }
        this._documents.clearBindingSelection(null);
    }

    render() {
        const cats = this._catalogItems();
        const noCatalogs = !this._catalogs.loading && cats.length === 0;
        const state = this._documents.state;
        const docs = this._visibleDocuments();
        const docsLoading = state.explorerView === 'deleted'
            ? this._deleted.busy
            : this._documents.busy;
        const actionsDisabled = this._actionsDisabled();
        const selectedDoc = this._selectedDocument();
        const selectedCount = Array.isArray(state.selectedBindingIds) ? state.selectedBindingIds.length : 0;
        const activeCatalog = this._catalogById(this._activeCatalogId());
        const breadcrumbs = this._buildBreadcrumbs();
        const childCatalogs = this._childCatalogsAtCurrentLevel();
        const showSemanticResults = this._showSemanticResults();
        const semanticSearchAvailable = this._semanticSearchAvailable();
        const showEmpty = !showSemanticResults && !docsLoading && docs.length === 0 && childCatalogs.length === 0;
        const subcatalogCount = activeCatalog ? this._subcatalogCount(activeCatalog.catalog_id) : 0;

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
                                        ${docsLoading ? html`<div class="loading">${this.t('list.loading')}</div>` : ''}
                                        ${showEmpty ? this._renderEmptyNoDocuments() : ''}
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
                                    catalog-title=${this._activeCatalogTitle()}
                                    subcatalog-count=${subcatalogCount}
                                    explorer-view=${state.explorerView}
                                    ?starred=${selectedDoc && (state.starredBindingIds || []).includes(selectedDoc.binding_id)}
                                    @close=${() => this._documents.setSelectedBinding({ bindingId: null })}
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
