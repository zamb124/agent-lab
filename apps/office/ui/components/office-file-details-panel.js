/**
 * office-file-details-panel — metadata, catalog summary, platform links.
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
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';

export class OfficeFileDetailsPanel extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        document: { type: Object },
        catalog: { type: Object },
        catalogTitle: { type: String, attribute: 'catalog-title' },
        subcatalogCount: { type: Number, attribute: 'subcatalog-count' },
        explorerView: { type: String, attribute: 'explorer-view' },
        starred: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        documentsControlHostStyles,
        documentsPanelActionStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: var(--documents-explorer-details-width, 20rem);
                min-width: var(--documents-explorer-details-width, 20rem);
                border-left: 1px solid var(--documents-explorer-divider, var(--glass-border-subtle));
                background: var(--glass-solid-subtle);
                min-height: 0;
                height: 100%;
            }
            .head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--documents-explorer-divider, var(--glass-border-subtle));
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
            .link-row {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .catalog-summary {
                padding: var(--space-3);
                border-radius: var(--radius-lg);
                background: var(--documents-empty-bg, var(--glass-tint-subtle));
                border: 1px solid var(--documents-explorer-divider, var(--glass-border-subtle));
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
        this.catalogTitle = '';
        this.subcatalogCount = 0;
        this.explorerView = 'catalog';
        this.starred = false;
        this._localeSel = this.select((s) => s.i18n.locale);
    }

    _close() { this.emit('close'); }
    _action(action) { this.emit('action', { action }); }

    _docTypeLabel(typeKey) {
        if (typeof typeKey !== 'string' || typeKey.length === 0) return '—';
        return this.t(`list.docType.${typeKey}`);
    }

    _formatDate(iso) {
        const locale = this._localeSel.value;
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('OfficeFileDetailsPanel: i18n locale required');
        }
        return formatPlatformDateTime(iso, locale);
    }

    _renderCatalogSummary() {
        const catalog = this.catalog;
        if (!catalog) {
            return html`
                <div class="catalog-summary">
                    <div class="section-title">${this.t('details.catalogSettings')}</div>
                    <div class="meta-value">${this.catalogTitle}</div>
                </div>
            `;
        }
        const visibilityLabel = catalog.is_public
            ? this.t('details.catalogPublic')
            : this.t('details.catalogPrivate');
        return html`
            <div class="catalog-summary">
                <div class="section-title">${this.t('details.catalogSettings')}</div>
                <div class="meta-value">${catalog.title}</div>
                <div class="meta-grid" style="margin-top: var(--space-3);">
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
                        <span class="meta-label">${this.t('details.fileCount')}</span>
                        <span class="meta-value">${this.t('catalogs.fileCount', { count: catalog.file_count })}</span>
                    </div>
                    <div class="meta-row">
                        <span class="meta-label">${this.t('details.subcatalogCount')}</span>
                        <span class="meta-value">${this.subcatalogCount}</span>
                    </div>
                </div>
            </div>
            <div class="actions">
                <button class="btn btn-primary" type="button" @click=${() => this._action('catalog-edit')}>
                    ${this.t('catalogs.edit')}
                </button>
                <button class="btn" type="button" @click=${() => this._action('catalog-access')}>
                    ${this.t('access.menuShare')}
                </button>
                <button class="btn" type="button" @click=${() => this._action('catalog-members')}>
                    ${this.t('catalogs.members')}
                </button>
                <button class="btn" type="button" @click=${() => this._action('catalog-create-subcatalog')}>
                    ${this.t('tree.newSubcatalog')}
                </button>
                <button class="btn btn-danger" type="button" @click=${() => this._action('catalog-delete')}>
                    ${this.t('catalogs.delete')}
                </button>
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

    _renderDocumentBody(doc) {
        const iconKey = resolveFileIconKey(doc.title, '');
        const sizeLabel = typeof doc.file_size === 'number' && doc.file_size > 0
            ? formatFileSize(doc.file_size)
            : '—';
        const isDeleted = this.explorerView === 'deleted';
        return html`
            <div class="icon-wrap">
                <platform-icon file-icon name=${iconKey} size="48"></platform-icon>
            </div>
            <div class="doc-title">${doc.title}</div>
            <div class="meta-grid">
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.catalog')}</span>
                    <span class="meta-value">${this.catalogTitle}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.type')}</span>
                    <span class="meta-value">${this._docTypeLabel(doc.file_category)}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">${this.t('details.size')}</span>
                    <span class="meta-value">${sizeLabel}</span>
                </div>
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
            <div class="actions">
                ${isDeleted ? html`
                    <button class="btn btn-primary" type="button" @click=${() => this._action('restore')}>
                        ${this.t('trash.restore')}
                    </button>
                    <button class="btn btn-danger" type="button" @click=${() => this._action('delete')}>
                        ${this.t('trash.deletePermanent')}
                    </button>
                ` : html`
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
                    <button class="btn btn-danger" type="button" @click=${() => this._action('delete')}>
                        ${this.t('list.delete')}
                    </button>
                `}
            </div>
        `;
    }

    render() {
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
                    : (this.explorerView === 'catalog' ? this._renderCatalogSummary() : '')}
            </div>
        `;
    }
}

customElements.define('office-file-details-panel', OfficeFileDetailsPanel);
