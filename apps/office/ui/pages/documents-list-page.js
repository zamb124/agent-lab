/**
 * OfficeDocumentsListPage — список документов с фильтром по каталогам.
 *
 * Маршрут `/documents`. Фабрики:
 *   - useOp('office/integration_status')   — баннер настройки DS (через
 *     `<office-integration-banner>`);
 *   - useResource('office/catalogs', autoload) — список каталогов для
 *     фильтра и определения активного каталога;
 *   - useOp('office/documents')           — список документов по выбранным
 *     catalogIds (slice + activeCatalogId через extraReducer);
 *   - useOp('office/document_remove')     — удаление по подтверждению.
 *
 * Открытие модалок: создание — `office.document_create_empty`, загрузка —
 * `office.document_upload`, переименование — `office.document_rename`.
 * Открытие документа — `navigate('document_editor', { bindingId })`.
 *
 * Состояние фильтра (`filterCatalogIds`) и активного каталога
 * (`activeCatalogId`) живёт в slice `office/documents` (см. фабрику).
 *
 * Реакция на смену namespace: `useEvent(UI_DOCUMENTS_RELOAD_REQUESTED)` —
 * сбрасываем фильтр и кеш ключа, перезагружаем `office/catalogs`; после
 * прихода нового списка `_maybeReloadDocs()` в `updated()` сам пересоберёт
 * запрос к документам уже в актуальном namespace.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/layout/page-header.js';
import '../components/office-integration-banner.js';
import '../components/office-document-row.js';

const CATALOG_FILTER_SEARCH_MIN = 8;

export class OfficeDocumentsListPage extends PlatformPage {
    static i18nNamespace = 'documents';

    static properties = {
        _filterSearch: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        buttonStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                flex: 1;
                width: 100%;
            }
            .page-body {
                box-sizing: border-box;
                padding: var(--space-4);
                flex: 1;
                min-height: 0;
            }
            @media (max-width: 767px) {
                .page-body {
                    padding: var(--space-2);
                    padding-top: 0;
                    padding-left: max(var(--space-2), env(safe-area-inset-left, 0px));
                    padding-right: max(var(--space-2), env(safe-area-inset-right, 0px));
                    padding-bottom: var(--space-2);
                }
            }
            .head-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                justify-content: flex-end;
            }
            .catalog-filter {
                display: flex; align-items: center; flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-4);
            }
            .filter-label {
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-secondary);
            }
            .filter-search {
                flex: 0 0 7.5rem;
                padding: 6px 10px;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: 13px;
            }
            .tag {
                padding: 4px 12px;
                border-radius: var(--radius-full);
                border: 1px solid var(--glass-border-medium);
                background: transparent;
                color: var(--text-secondary);
                font-size: 12px;
                font-weight: 600;
                cursor: pointer;
                transition: all var(--duration-fast);
                max-width: 11rem;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .tag[aria-pressed="true"] {
                border-color: var(--accent);
                background: var(--accent-subtle);
                color: var(--accent);
            }
            .tag:hover { color: var(--text-primary); }
            .docs-grid {
                display: flex; flex-direction: column;
                gap: var(--space-2);
            }
            .empty {
                display: flex; flex-direction: column;
                align-items: center; justify-content: center;
                padding: var(--space-12);
                text-align: center;
                gap: var(--space-3);
                color: var(--text-secondary);
            }
            .empty-icon { color: var(--text-tertiary); opacity: 0.4; }
            .empty-title { font-size: var(--text-lg); font-weight: 600; color: var(--text-primary); }
            .empty-hint { font-size: var(--text-sm); color: var(--text-tertiary); }
            .loading { padding: var(--space-6); color: var(--text-tertiary); text-align: center; }
        `,
    ];

    constructor() {
        super();
        this._filterSearch = '';
        this._integration = this.useOp('office/integration_status');
        this._catalogs = this.useResource('office/catalogs', { autoload: true });
        this._documents = this.useOp('office/documents');
        this._remove = this.useOp('office/document_remove');
        this._lastEffectiveKey = '';
    }

    connectedCallback() {
        super.connectedCallback();
        if (!this._integration.lastResult && !this._integration.busy) {
            this._integration.run(null);
        }
        this.useEvent(CoreEvents.UI_DOCUMENTS_RELOAD_REQUESTED, () => this._onNamespaceReload());
    }

    _onNamespaceReload() {
        this._lastEffectiveKey = '';
        this._filterSearch = '';
        this._documents.clearFilter(null);
        this._catalogs.load();
    }

    updated(changed) {
        super.updated && super.updated(changed);
        this._maybeReloadDocs();
    }

    _availableCatalogs() {
        return this._catalogs.items;
    }

    _filterIds() {
        const ids = this._documents.state.filterCatalogIds;
        return Array.isArray(ids) ? ids : [];
    }

    _activeCatalogId() {
        const state = this._documents.state;
        if (typeof state.activeCatalogId === 'string' && state.activeCatalogId.length > 0) {
            return state.activeCatalogId;
        }
        const filter = this._filterIds();
        if (filter.length === 1) return filter[0];
        const all = this._availableCatalogs();
        return all.length > 0 ? all[0].catalog_id : '';
    }

    _effectiveCatalogIds() {
        const filter = this._filterIds();
        if (filter.length > 0) return filter;
        return this._availableCatalogs().map((c) => c.catalog_id);
    }

    _maybeReloadDocs() {
        if (this._catalogs.loading) return;
        const ids = this._effectiveCatalogIds();
        if (ids.length === 0) return;
        const key = ids.slice().sort().join(',');
        if (key === this._lastEffectiveKey) return;
        this._lastEffectiveKey = key;
        this._documents.run({ catalogIds: ids });
    }

    _onTagClick(catalogId) {
        const current = this._filterIds();
        let next;
        if (current.includes(catalogId)) {
            next = current.filter((id) => id !== catalogId);
        } else {
            next = [...current, catalogId];
        }
        this._documents.setFilterCatalogs({ catalogIds: next });
        this._documents.setActiveCatalog({ catalogId: next.length === 1 ? next[0] : null });
    }

    _onSearchInput(e) { this._filterSearch = e.target.value; }

    _openCreateEmpty() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) return;
        this.openModal('office.document_create_empty', { catalogId, openAfterCreate: true });
    }

    _openUpload() {
        const catalogId = this._activeCatalogId();
        if (!catalogId) return;
        this.openModal('office.document_upload', { catalogId, openAfterUpload: true });
    }

    _onOpenDocument(e) {
        const bindingId = e.detail && e.detail.bindingId;
        if (typeof bindingId !== 'string' || bindingId.length === 0) return;
        this.navigate('document_editor', { bindingId });
    }

    _onRenameDocument(e) {
        const doc = e.detail && e.detail.document;
        if (!doc) return;
        this.openModal('office.document_rename', {
            bindingId: doc.binding_id,
            currentTitle: doc.title,
            catalogIds: this._effectiveCatalogIds(),
        });
    }

    _onDeleteDocument(e) {
        const doc = e.detail && e.detail.document;
        if (!doc) return;
        if (!confirm(this.t('list.deleteConfirm', { title: doc.title }))) return;
        this._remove.run({
            bindingId: doc.binding_id,
            catalogIds: this._effectiveCatalogIds(),
        });
    }

    _renderCatalogFilter() {
        const cats = this._availableCatalogs();
        if (cats.length <= 1) return '';
        const filter = this._filterIds();
        const search = this._filterSearch.trim().toLowerCase();
        const filtered = search.length > 0
            ? cats.filter((c) => c.title.toLowerCase().includes(search) || filter.includes(c.catalog_id))
            : cats;
        const showSearch = cats.length >= CATALOG_FILTER_SEARCH_MIN;
        return html`
            <div class="catalog-filter">
                <span class="filter-label">${this.t('list.catalogLabel')}:</span>
                ${showSearch ? html`
                    <input class="filter-search" type="search"
                           placeholder=${this.t('list.catalogFilterSearchPlaceholder')}
                           .value=${this._filterSearch}
                           @input=${this._onSearchInput} />
                ` : ''}
                ${filtered.map((c) => html`
                    <button class="tag" type="button"
                            aria-pressed=${filter.includes(c.catalog_id) ? 'true' : 'false'}
                            title=${this.t('list.catalogToggleHint')}
                            @click=${() => this._onTagClick(c.catalog_id)}>
                        ${c.title}
                    </button>
                `)}
            </div>
        `;
    }

    _renderEmptyNoDocuments() {
        return html`
            <div class="empty">
                <div class="empty-icon"><platform-icon name="folder" size="64"></platform-icon></div>
                <div class="empty-title">${this.t('list.emptyStateTitle')}</div>
                <div class="empty-hint">${this.t('list.emptyStateHint')}</div>
                <div class="head-actions">
                    <button class="btn btn-primary" @click=${this._openCreateEmpty}>
                        ${this.t('list.newEmpty')}
                    </button>
                    <button class="btn" @click=${this._openUpload}>
                        ${this.t('list.upload')}
                    </button>
                </div>
            </div>
        `;
    }

    _renderEmptyNoCatalogs() {
        return html`
            <div class="empty">
                <div class="empty-icon"><platform-icon name="folder" size="64"></platform-icon></div>
                <div class="empty-title">${this.t('list.noCatalogsStateTitle')}</div>
                <div class="empty-hint">${this.t('list.noCatalogsStateHint')}</div>
                <button class="btn btn-primary" @click=${() => this.navigate('documents_catalogs')}>
                    ${this.t('list.noCatalogsCta')}
                </button>
            </div>
        `;
    }

    render() {
        const cats = this._availableCatalogs();
        const noCatalogs = !this._catalogs.loading && cats.length === 0;
        const docs = this._documents.state.items;
        const docsLoading = this._documents.busy;
        return html`
            <office-integration-banner></office-integration-banner>
            <page-header
                title=${this.t('list.heading')}
                actions-overflow="visible"
            >
                ${noCatalogs ? '' : html`
                    <div slot="actions" class="head-actions">
                        <button class="btn btn-primary"
                                ?disabled=${!this._activeCatalogId()}
                                @click=${this._openCreateEmpty}>
                            ${this.t('list.newEmpty')}
                        </button>
                        <button class="btn"
                                ?disabled=${!this._activeCatalogId()}
                                @click=${this._openUpload}>
                            ${this.t('list.upload')}
                        </button>
                    </div>
                `}
            </page-header>

            <div class="page-body">
            ${noCatalogs ? this._renderEmptyNoCatalogs() : html`
                ${this._renderCatalogFilter()}
                ${docsLoading ? html`<div class="loading">${this.t('list.loading')}</div>` : ''}
                ${!docsLoading && docs.length === 0 ? this._renderEmptyNoDocuments() : ''}
                ${!docsLoading && docs.length > 0 ? html`
                    <div class="docs-grid">
                        ${docs.map((doc) => html`
                            <office-document-row
                                .document=${doc}
                                @open=${this._onOpenDocument}
                                @rename=${this._onRenameDocument}
                                @delete=${this._onDeleteDocument}
                            ></office-document-row>
                        `)}
                    </div>
                ` : ''}
            `}
            </div>
        `;
    }
}

customElements.define('office-documents-list-page', OfficeDocumentsListPage);
