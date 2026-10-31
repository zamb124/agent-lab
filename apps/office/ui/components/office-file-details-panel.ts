/**
 * office-file-details-panel — сведения выбранного файла или каталога.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import {
    documentsControlHostStyles,
    documentsPanelActionStyles,
} from '../styles/documents-controls.styles.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import { formatFileSize } from '@platform/lib/utils/format-file-size.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { formatFileRetentionRemaining } from '@platform/lib/utils/format-file-retention.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import type { SelectController } from '@platform/lib/events/select-controller.js';

export class OfficeFileDetailsPanel extends PlatformElement {
    static i18nNamespace = 'documents';

    static override properties: PropertyDeclarations = {
        document: { type: Object },
        catalog: { type: Object },
        selectedCatalog: { type: Object },
        catalogTitle: { type: String, attribute: 'catalog-title' },
        subcatalogCount: { type: Number, attribute: 'subcatalog-count' },
        explorerView: { type: String, attribute: 'explorer-view' },
        namespaceRoot: { type: Boolean, attribute: 'namespace-root' },
        starred: { type: Boolean },
    }
    declare document: Record<string, unknown> | null;
    declare catalog: Record<string, unknown> | null;
    declare selectedCatalog: Record<string, unknown> | null;
    declare catalogTitle: string;
    declare subcatalogCount: number;
    declare explorerView: string;
    declare namespaceRoot: boolean;
    declare starred: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        buttonStyles,
        documentsControlHostStyles,
        documentsPanelActionStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: var(--documents-explorer-details-width);
                min-width: var(--documents-explorer-details-width);
                border-left: 1px solid var(--documents-explorer-divider);
                background: var(--glass-solid-subtle);
                min-height: 0;
                height: 100%;
            }
            .head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--documents-explorer-divider);
            }
            .head-title {
                font-size: var(--text-sm);
                font-weight: 700;
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .close-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 2rem;
                height: 2rem;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
            }
            .close-btn:hover { background: var(--glass-solid-medium); }
            .body {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .section-title {
                font-size: var(--text-xs);
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
                margin-bottom: var(--space-2);
            }
            .icon-wrap {
                display: flex;
                justify-content: center;
                padding: var(--space-2) 0;
            }
            .doc-title {
                font-size: var(--text-lg);
                font-weight: 700;
                color: var(--text-primary);
                word-break: break-word;
            }
            .meta-grid { display: grid; gap: var(--space-3); }
            .meta-row { display: flex; flex-direction: column; gap: var(--space-1); }
            .meta-label {
                font-size: var(--text-xs);
                font-weight: 600;
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .meta-value { font-size: var(--text-sm); color: var(--text-primary); }
            .rag-index-value {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }
            .rag-index-value--ready { color: var(--success); }
            .rag-index-value--pending { color: var(--warning); }
            .rag-index-value--failed { color: var(--error); }
            .rag-index-value--absent { color: var(--text-tertiary); }
            .link-row {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .missing-banner {
                display: flex;
                gap: var(--space-2);
                align-items: flex-start;
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                border: 1px solid color-mix(in srgb, var(--warning) 35%, transparent);
                background: color-mix(in srgb, var(--warning) 12%, transparent);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }
            .missing-banner strong {
                display: block;
                margin-bottom: var(--space-1);
            }
            @media (max-width: 767px) {
                :host {
                    width: 100%;
                    min-width: 0;
                    border-left: none;
                    border-top: 1px solid var(--glass-border-subtle);
                }
            }
        `,
    ];

    constructor() {
        super();
        this.document = null;
        this.catalog = null;
        this.selectedCatalog = null;
        this.catalogTitle = '';
        this.subcatalogCount = 0;
        this.explorerView = 'catalog';
        this.namespaceRoot = false;
        this.starred = false;
        this._localeSel = this.select((state) => state.i18n.locale);
    }

    private _localeSel: SelectController<unknown>;

    private _close() { this.emit('close'); }
    private _action(action: string) { this.emit('action', { action }); }

    private _docTypeLabel(typeKey: unknown) {
        if (typeof typeKey !== 'string' || typeKey.length === 0) return '—';
        return this.t(`list.docType.${typeKey}`);
    }

    private _isFileMissing(doc: Record<string, unknown> | null) {
        return doc && doc.file_availability === 'missing';
    }

    private _formatDate(iso: unknown) {
        const locale = this._localeSel.value;
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('OfficeFileDetailsPanel: i18n locale required');
        }
        return formatPlatformDateTime(iso as string | number | Date, locale);
    }

    private _retentionLabel(doc: Record<string, unknown> | null) {
        const locale = this._localeSel.value;
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('OfficeFileDetailsPanel: i18n locale required');
        }
        if (this._isFileMissing(doc)) {
            return '—';
        }
        const remaining = formatFileRetentionRemaining(doc ? doc.file_expires_at as string | null | undefined : null, locale);
        if (remaining === 'permanent') {
            return this.t('list.retentionPermanent');
        }
        if (remaining === 'expired') {
            return this.t('list.retentionExpired');
        }
        return remaining;
    }

    private _catalogFileCount(catalog: Record<string, unknown>) {
        if (typeof catalog.file_count !== 'number') {
            throw new Error('OfficeFileDetailsPanel: catalog.file_count required');
        }
        return catalog.file_count;
    }

    private _catalogCanDelete(catalog: Record<string, unknown>) {
        if (catalog.is_owner !== true) {
            return false;
        }
        return this._catalogFileCount(catalog) === 0 && this.subcatalogCount === 0;
    }

    private _renderCatalogActions(catalog: Record<string, unknown>, { showOpen }: { showOpen: boolean }) {
        const isOwner = catalog.is_owner === true;
        const showMembers = isOwner && catalog.company_visible !== true;
        const canDelete = this._catalogCanDelete(catalog);
        return html`
            <div class="actions">
                ${showOpen ? html`
                    <button class="btn btn-primary" type="button" @click=${() => this._action('open')}>
                        ${this.t('list.open')}
                    </button>
                ` : ''}
                ${isOwner ? html`
                    <button class="btn ${showOpen ? '' : 'btn-primary'}" type="button" @click=${() => this._action('edit')}>
                        ${this.t('catalogs.edit')}
                    </button>
                    <button class="btn" type="button" @click=${() => this._action('access')}>
                        ${this.t('access.menuShare')}
                    </button>
                ` : ''}
                ${showMembers ? html`
                    <button class="btn" type="button" @click=${() => this._action('members')}>
                        ${this.t('catalogs.members')}
                    </button>
                ` : ''}
                ${isOwner ? html`
                    <button class="btn" type="button" @click=${() => this._action('rag')}>
                        ${this.t('catalog_context_menu.rag')}
                    </button>
                ` : ''}
                <button class="btn" type="button" @click=${() => this._action('create-subcatalog')}>
                    ${this.t('tree.newSubcatalog')}
                </button>
                ${isOwner ? html`
                    <button
                        class="btn btn-danger"
                        type="button"
                        ?disabled=${!canDelete}
                        @click=${() => { if (canDelete) this._action('delete'); }}
                    >
                        ${this.t('catalogs.delete')}
                    </button>
                ` : ''}
            </div>
        `;
    }

    private _renderCatalogBody(catalog: Record<string, unknown>, { showOpen }: { showOpen: boolean }) {
        const visibilityLabel = catalog.company_visible
            ? this.t('details.catalogCompanyVisible')
            : this.t('details.catalogPrivate');
        const fileCount = this._catalogFileCount(catalog);
        return html`
            <div class="icon-wrap">
                <platform-icon file-icon name="folder" size="48"></platform-icon>
            </div>
            <div class="doc-title">${catalog.title}</div>
            ${this._renderCatalogActions(catalog, { showOpen })}
            <div class="meta-grid">
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.type')}</span>
                    <span class="meta-value">${this.t('list.docType.catalog')}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.size')}</span>
                    <span class="meta-value">${this.t('catalogs.fileCount', { count: fileCount })}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.visibility')}</span>
                    <span class="meta-value">${visibilityLabel}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.owner')}</span>
                    <span class="meta-value">
                        <platform-user-chip user-id=${catalog.owner_user_id}></platform-user-chip>
                    </span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.subcatalogCount')}</span>
                    <span class="meta-value">${this.subcatalogCount}</span>
                </div>
                ${catalog.rag_index_enabled === true ? html`
                    <div class="meta-row">
                        <span class="meta-label">${this.t('details.ragIndex')}</span>
                        <span class="meta-value">${this.t('catalog_context_menu.rag')}</span>
                    </div>
                ` : ''}
            </div>
        `;
    }

    _renderPlatformLinks() {
        return html`
            <div>
                <div class="section-title">${this.t('links.section')}</div>
                <div class="link-row">
                    <button class="link-btn" type="button" @click=${() => this._action('create-work-item')}>
                        <platform-icon name="check-square" size="16"></platform-icon>
                        ${this.t('links.createWorkItem')}
                    </button>
                    <button class="link-btn" type="button" @click=${() => this._action('attach-crm')}>
                        <platform-icon name="users" size="16"></platform-icon>
                        ${this.t('links.attachCrm')}
                    </button>
                    <button class="link-btn" type="button" @click=${() => this._action('open-sync')}>
                        <platform-icon name="message" size="16"></platform-icon>
                        ${this.t('links.openSync')}
                    </button>
                </div>
            </div>
        `;
    }

    private _ragIndexIconName(status: string) {
        if (status === 'ready') return 'check';
        if (status === 'pending') return 'hourglass-top';
        if (status === 'failed') return 'alert-triangle';
        if (status === 'absent') return 'database';
        throw new Error(`office-file-details-panel: unknown rag_index_status '${status}'`);
    }

    private _renderRagIndexRow(doc: Record<string, unknown>) {
        const status = doc.rag_index_status;
        if (typeof status !== 'string') {
            return '';
        }
        if (status !== 'ready' && status !== 'pending' && status !== 'failed' && status !== 'absent') {
            throw new Error(`office-file-details-panel: unknown rag_index_status '${status}'`);
        }
        return html`
            <div class="meta-row">
                <span class="meta-label">${this.t('details.ragIndex')}</span>
                <span class="meta-value rag-index-value rag-index-value--${status}">
                    <platform-icon name=${this._ragIndexIconName(status)} size="16"></platform-icon>
                    ${this.t(`rag_index.${status}`)}
                </span>
            </div>
        `;
    }

    private _renderDocumentActions({ fileMissing, isDeleted }: { fileMissing: boolean; isDeleted: boolean }) {
        if (isDeleted) {
            return html`
                <div class="actions">
                    <button class="btn btn-primary" type="button" @click=${() => this._action('restore')}>
                        ${this.t('trash.restore')}
                    </button>
                    <button class="btn btn-danger" type="button" @click=${() => this._action('delete')}>
                        ${this.t('trash.deletePermanent')}
                    </button>
                </div>
            `;
        }
        return html`
            <div class="actions">
                ${fileMissing ? '' : html`
                    <button class="btn btn-primary" type="button" @click=${() => this._action('open')}>
                        ${this.t('list.open')}
                    </button>
                    <button class="btn" type="button" @click=${() => this._action('toggle-starred')}>
                        ${this.starred ? this.t('nav.unstar') : this.t('nav.star')}
                    </button>
                    <button class="btn" type="button" @click=${() => this._action('share')}>
                        ${this.t('access.menuShare')}
                    </button>
                    <button class="btn" type="button" @click=${() => this._action('rename')}>
                        ${this.t('list.rename')}
                    </button>
                `}
                <button class="btn btn-danger" type="button" @click=${() => this._action('delete')}>
                    ${this.t('list.delete')}
                </button>
            </div>
        `;
    }

    private _renderDocumentBody(doc: Record<string, unknown>) {
        const iconKey = resolveFileIconKey(typeof doc.title === 'string' ? doc.title : '', '');
        const fileMissing = this._isFileMissing(doc);
        const sizeLabel = typeof doc.file_size === 'number' && doc.file_size > 0
            ? formatFileSize(doc.file_size)
            : '—';
        const isDeleted = this.explorerView === 'deleted';
        return html`
            <div class="icon-wrap">
                <platform-icon file-icon name=${iconKey} size="48"></platform-icon>
            </div>
            <div class="doc-title">${doc.title}</div>
            ${fileMissing ? html`
                <div class="missing-banner" role="status">
                    <platform-icon name="alert-triangle" size="18"></platform-icon>
                    <div>
                        <strong>${this.t('list.fileMissing')}</strong>
                        ${this.t('list.fileMissingHint')}
                    </div>
                </div>
            ` : ''}
            ${this._renderDocumentActions({ fileMissing: Boolean(fileMissing), isDeleted })}
            <div class="meta-grid">
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.catalog')}</span>
                    <span class="meta-value">${this.catalogTitle}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.type')}</span>
                    <span class="meta-value">${fileMissing ? this.t('list.fileMissing') : this._docTypeLabel(doc.file_category)}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.size')}</span>
                    <span class="meta-value">${sizeLabel}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.retention')}</span>
                    <span class="meta-value">${this._retentionLabel(doc)}</span>
                </div>
                ${this._renderRagIndexRow(doc)}
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.updated')}</span>
                    <span class="meta-value">${this._formatDate(doc.updated_at)}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.created')}</span>
                    <span class="meta-value">${this._formatDate(doc.created_at)}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('list.colAuthor')}</span>
                    <span class="meta-value">
                        <platform-user-chip user-id=${doc.created_by_user_id}></platform-user-chip>
                    </span>
                </div>
            </div>
            ${this._renderPlatformLinks()}
        `;
    }

    _renderNamespaceRoot() {
        return html`
            <div class="icon-wrap">
                <platform-icon file-icon name="folder" size="48"></platform-icon>
            </div>
            <div class="doc-title">${this.t('details.rootTitle')}</div>
            <div class="meta-value">${this.t('details.rootHint')}</div>
        `;
    }

    override render(): TemplateResult {
        return html`
            <div class="head">
                <span class="head-title">${this.t('details.title')}</span>
                <button class="close-btn" type="button" @click=${this._close}>
                    <platform-icon name="close" size="16"></platform-icon>
                </button>
            </div>
            <div class="body">
                ${this.document
                    ? this._renderDocumentBody(this.document)
                    : (this.selectedCatalog
                        ? this._renderCatalogBody(this.selectedCatalog, { showOpen: true })
                        : (this.explorerView === 'catalog' && this.catalog
                            ? this._renderCatalogBody(this.catalog, { showOpen: false })
                            : (this.namespaceRoot ? this._renderNamespaceRoot() : '')))}
            </div>
        `;
    }
}

customElements.define('office-file-details-panel', OfficeFileDetailsPanel);
