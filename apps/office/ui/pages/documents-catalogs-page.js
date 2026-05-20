/**
 * OfficeDocumentsCatalogsPage — дашборд каталогов документов.
 *
 * Маршрут `/documents/catalogs` (+ legacy alias `/documents/catalog/:catalogId`,
 * приходящий через `focusCatalogId` prop). Фабрики:
 *   - useResource('office/catalogs', autoload) — список каталогов
 *   - useOp('office/documents')               — `setActiveCatalog` action
 *
 * Карточки рендерятся `<office-catalog-card>`. Эмитят:
 *   - 'open'           → setActiveCatalog + navigate('documents_list')
 *   - 'manage-members' → openModal('office.catalog_members')
 *   - 'edit'           → openModal('office.catalog_edit')
 *   - 'delete'         → подтверждение + useResource('office/catalogs').remove
 *
 * Реакция на смену namespace: `useEvent(UI_DOCUMENTS_RELOAD_REQUESTED)` —
 * перезагружаем список каталогов; новый namespace полностью перерисует grid.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '../components/office-catalog-card.js';

export class OfficeDocumentsCatalogsPage extends PlatformPage {
    static i18nNamespace = 'documents';

    static properties = {
        focusCatalogId: { type: String },
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
                padding: 0;
                flex: 1;
                min-height: 0;
            }
            .breadcrumbs-wrap { margin-bottom: var(--space-3); }
            @media (max-width: 767px) {
                .breadcrumbs-wrap {
                    display: none;
                }
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-4);
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
        this.focusCatalogId = '';
        this._catalogs = this.useResource('office/catalogs', { autoload: true });
        this._documents = this.useOp('office/documents');
        this._focusHandled = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(CoreEvents.UI_DOCUMENTS_RELOAD_REQUESTED, () => this._catalogs.load());
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (!this._focusHandled
            && typeof this.focusCatalogId === 'string'
            && this.focusCatalogId.length > 0) {
            this._focusHandled = true;
            this._documents.setActiveCatalog({ catalogId: this.focusCatalogId });
            this._documents.setFilterCatalogs({ catalogIds: [this.focusCatalogId] });
            this.navigate('documents_list');
        }
    }

    _onCreateCatalog() {
        this.openModal('office.catalog_create');
    }

    _onOpenCatalog(e) {
        const catalogId = e.detail && e.detail.catalogId;
        if (typeof catalogId !== 'string') return;
        this._documents.setActiveCatalog({ catalogId });
        this._documents.setFilterCatalogs({ catalogIds: [catalogId] });
        this.navigate('documents_list');
    }

    _onManageMembers(e) {
        const detail = e.detail;
        if (!detail || typeof detail.catalogId !== 'string') return;
        this.openModal('office.catalog_members', {
            catalogId: detail.catalogId,
            catalogTitle: detail.catalogTitle,
            isPublic: Boolean(detail.isPublic),
        });
    }

    _onEditCatalog(e) {
        const detail = e.detail;
        if (!detail || typeof detail.catalogId !== 'string') return;
        this.openModal('office.catalog_edit', {
            catalogId: detail.catalogId,
            title: detail.title,
            isPublic: Boolean(detail.isPublic),
        });
    }

    _onDeleteCatalog(e) {
        const detail = e.detail;
        if (!detail || typeof detail.catalogId !== 'string') return;
        if (!confirm(this.t('catalogs.deleteConfirm', { title: detail.title }))) return;
        this._catalogs.remove(detail.catalogId);
    }

    _renderEmpty() {
        return html`
            <div class="empty">
                <div class="empty-icon"><platform-icon name="folder" size="64"></platform-icon></div>
                <div class="empty-title">${this.t('catalogs.emptyStateTitle')}</div>
                <div class="empty-hint">${this.t('catalogs.emptyStateHint')}</div>
                <button class="btn btn-primary" @click=${this._onCreateCatalog}>
                    ${this.t('catalogs.create')}
                </button>
            </div>
        `;
    }

    render() {
        const items = this._catalogs.items;
        const loading = this._catalogs.loading;
        const focusedCatalog = typeof this.focusCatalogId === 'string' && this.focusCatalogId.length > 0
            ? items.find((c) => c && c.catalog_id === this.focusCatalogId)
            : null;
        const crumbLabel = focusedCatalog
            && typeof focusedCatalog.title === 'string'
            && focusedCatalog.title.length > 0
            ? focusedCatalog.title
            : '';
        return html`
            <page-header title=${this.t('catalogs.heading')} actions-overflow="visible">
                <div slot="actions">
                    <button class="btn btn-primary" @click=${this._onCreateCatalog}>
                        ${this.t('catalogs.create')}
                    </button>
                </div>
            </page-header>
            <div class="page-body">
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${crumbLabel}></platform-breadcrumbs>
            </div>
            ${loading ? html`<div class="loading">${this.t('list.loading')}</div>` : ''}
            ${!loading && items.length === 0 ? this._renderEmpty() : ''}
            ${!loading && items.length > 0 ? html`
                <div class="grid">
                    ${items.map((c) => html`
                        <office-catalog-card
                            .catalog=${c}
                            @open=${this._onOpenCatalog}
                            @manage-members=${this._onManageMembers}
                            @edit=${this._onEditCatalog}
                            @delete=${this._onDeleteCatalog}
                        ></office-catalog-card>
                    `)}
                </div>
            ` : ''}
            </div>
        `;
    }
}

customElements.define('office-documents-catalogs-page', OfficeDocumentsCatalogsPage);
