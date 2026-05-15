/**
 * NamespacePage — детальная страница namespace: список документов + drop-zone.
 *
 * Маршрут `/rag/namespaces/:namespaceId` (router.effect передаёт namespaceId
 * как property). При смене namespaceId вызывает `useOp('rag/documents')` для
 * перезагрузки. Загрузка/удаление документа — отдельные ops; статус
 * индексации обновляется поллингом фабрики `rag/document_status`,
 * после `completed` страница перезагружает список через `useEvent`.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buttonStyles, iconButtonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-breadcrumbs.js';

const ACCEPT_TYPES = '.pdf,.docx,.doc,.txt,.md,.html,.csv,.xlsx,.pptx';
const DOC_STATUS_EVENT = 'rag/document_status/succeeded';

export class NamespacePage extends PlatformPage {
    static i18nNamespace = 'rag';

    static properties = {
        namespaceId: { type: String },
        _dragOver: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        buttonStyles,
        iconButtonStyles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; }
            .breadcrumbs-wrap { flex-shrink: 0; margin-bottom: var(--space-3); }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-8); }
            .header-left { display: flex; align-items: center; gap: var(--space-3); }
            .title { font-size: var(--text-3xl); font-weight: var(--font-bold); color: var(--text-primary); letter-spacing: var(--tracking-tight); }
            .subtitle { font-size: var(--text-base); color: var(--text-secondary); margin-top: var(--space-1); }
            .actions { display: flex; gap: var(--space-2); }
            .documents-list { flex: 1; display: flex; flex-direction: column; gap: var(--space-3); }
            .document-card {
                padding: var(--space-4); background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-lg);
                transition: var(--motion-transition-interactive);
            }
            .document-card:hover { background: var(--glass-solid-medium); border-color: var(--glass-border-medium); }
            .document-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: var(--space-2); }
            .document-name { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--text-primary); }
            .document-meta { display: flex; gap: var(--space-4); font-size: var(--text-sm); color: var(--text-tertiary); }
            .document-actions { display: flex; gap: var(--space-2); }
            .empty {
                flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
                padding: var(--space-12); text-align: center;
            }
            .empty-text { font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--text-primary); margin-bottom: var(--space-2); }
            input[type="file"] { display: none; }
            .drop-zone {
                margin-top: var(--space-6); padding: var(--space-12);
                border: 2px dashed var(--glass-border-medium);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                text-align: center; transition: var(--motion-transition-interactive); cursor: pointer;
            }
            .drop-zone:hover, .drop-zone.drag-over { border-color: var(--accent); background: var(--glass-solid-medium); }
            .drop-zone-content { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); }
            .drop-zone-icon {
                width: 64px; height: 64px; display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-full); background: var(--glass-solid-medium); color: var(--accent);
            }
            .drop-zone-text { font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--text-primary); }
            .drop-zone-hint { font-size: var(--text-sm); color: var(--text-tertiary); }
            .loading-spinner {
                width: 48px; height: 48px;
                border: 4px solid var(--glass-border-subtle);
                border-top: 4px solid var(--accent);
                border-radius: 50%; animation: spin 1s linear infinite;
            }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        `,
    ];

    constructor() {
        super();
        this.namespaceId = '';
        this._dragOver = false;
        this._docs = this.useOp('rag/documents');
        this._upload = this.useOp('rag/document_upload');
        this._remove = this.useOp('rag/document_remove');
        this._namespaces = this.useResource('rag/namespaces', { autoload: true });
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(DOC_STATUS_EVENT, () => {
            if (typeof this.namespaceId === 'string' && this.namespaceId.length > 0) {
                this._docs.run({ namespaceId: this.namespaceId });
            }
        });
    }

    updated(changed) {
        super.updated && super.updated(changed);
        if (changed.has('namespaceId') && typeof this.namespaceId === 'string' && this.namespaceId.length > 0) {
            if (this._docs.state.loadedNamespaceId !== this.namespaceId) {
                this._docs.run({ namespaceId: this.namespaceId });
            }
        }
    }

    _goBack() { this.navigate('namespaces'); }

    _triggerFileInput() {
        this.shadowRoot.querySelector('input[type="file"]')?.click();
    }

    _handleFileSelect(e) {
        const file = e.target.files[0];
        if (!file) return;
        this._uploadFile(file);
    }

    _uploadFile(file) {
        if (!this.namespaceId) {
            throw new Error('NamespacePage: namespaceId is empty, cannot upload');
        }
        this._upload.run({ namespaceId: this.namespaceId, file, metadata: {} });
    }

    _deleteDocument(documentId) {
        if (!this.namespaceId) {
            throw new Error('NamespacePage: namespaceId is empty, cannot delete');
        }
        if (!confirm(this.t('namespace_detail.delete_confirm'))) return;
        this._remove.run({ namespaceId: this.namespaceId, documentId });
    }

    _handleDragOver(e) { e.preventDefault(); e.stopPropagation(); this._dragOver = true; }
    _handleDragLeave(e) { e.preventDefault(); e.stopPropagation(); this._dragOver = false; }
    _handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this._dragOver = false;
        const files = e.dataTransfer && e.dataTransfer.files
            ? Array.from(e.dataTransfer.files)
            : [];
        if (files.length > 0) this._uploadFile(files[0]);
    }

    _findNamespace() {
        for (const ns of this._namespaces.items) {
            if (ns.name === this.namespaceId) return ns;
        }
        return null;
    }

    render() {
        const namespace = this._findNamespace();
        const uploading = this._upload.busy;
        const documents = this._docs.state.items;
        const loading = this._docs.busy;

        if (!namespace && !this._namespaces.loading) {
            return html`
                <div class="empty">
                    <div class="empty-text">${this.t('namespace_detail.not_found')}</div>
                </div>
            `;
        }

        const crumbLabel = namespace && typeof namespace.name === 'string' && namespace.name.length > 0
            ? namespace.name
            : this.namespaceId;
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs current-label=${crumbLabel}></platform-breadcrumbs>
            </div>
            <div class="header">
                <div class="header-left">
                    <button class="btn-icon" @click=${this._goBack} title=${this.t('namespace_detail.back')}>
                        <platform-icon name="chevron-left" size="20"></platform-icon>
                    </button>
                    <div>
                        <h1 class="title">${namespace ? namespace.name : this.namespaceId}</h1>
                        <p class="subtitle">${this.t('namespace_detail.documents_count', { count: documents.length })}</p>
                    </div>
                </div>
                <div class="actions">
                    <button class="btn btn-primary" @click=${this._triggerFileInput} ?disabled=${uploading}>
                        <platform-icon name="plus" size="18"></platform-icon>
                        <span>${uploading
                            ? this.t('namespace_detail.uploading_short')
                            : this.t('namespace_detail.upload_button')}</span>
                    </button>
                </div>
            </div>

            <input type="file" @change=${this._handleFileSelect} accept=${ACCEPT_TYPES} />

            ${loading ? html`
                <div class="empty">
                    <div class="loading-spinner"></div>
                    <div>${this.t('namespace_detail.loading_documents')}</div>
                </div>
            ` : documents.length === 0 ? html`
                <div class="drop-zone ${this._dragOver ? 'drag-over' : ''}"
                     @click=${this._triggerFileInput}
                     @dragover=${this._handleDragOver}
                     @dragleave=${this._handleDragLeave}
                     @drop=${this._handleDrop}>
                    <div class="drop-zone-content">
                        <div class="drop-zone-icon">
                            <platform-icon name=${uploading ? 'refresh' : 'cloud'} size="32"></platform-icon>
                        </div>
                        <div class="drop-zone-text">${uploading
                            ? this.t('namespace_detail.uploading_document')
                            : this.t('namespace_detail.drop_here')}</div>
                        <div class="drop-zone-hint">${this.t('namespace_detail.drop_or_choose')}</div>
                    </div>
                </div>
            ` : html`
                <div class="documents-list">
                    ${documents.map((doc) => html`
                        <div class="document-card">
                            <div class="document-header">
                                <div>
                                    <div class="document-name">
                                        <platform-icon file-icon name=${resolveFileIconKey(doc.name, '')} size="16"></platform-icon>
                                        ${doc.name}
                                    </div>
                                    <div class="document-meta">
                                        <span>${this.t('namespace_detail.created_at_label')} ${new Date(doc.created_at).toLocaleDateString()}</span>
                                        ${typeof doc.pages === 'number' ? html`<span>${this.t('namespace_detail.pages_count', { count: doc.pages })}</span>` : ''}
                                    </div>
                                </div>
                                <div class="document-actions">
                                    <button class="btn-icon danger"
                                            @click=${() => this._deleteDocument(doc.document_id)}
                                            title=${this.t('namespace_detail.delete_button_title')}>
                                        <platform-icon name="trash" size="16"></platform-icon>
                                    </button>
                                </div>
                            </div>
                        </div>
                    `)}
                </div>
            `}
        `;
    }
}

customElements.define('rag-namespace-page', NamespacePage);
