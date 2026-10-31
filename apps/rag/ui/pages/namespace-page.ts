/**
 * NamespacePage — детальная страница namespace: список документов + drop-zone.
 *
 * Маршрут `/rag/namespaces/:namespaceId` (router.effect передаёт namespaceId
 * как property). При смене namespaceId вызывает `useOp('rag/documents')` для
 * перезагрузки. Загрузка/удаление документа — отдельные ops; статус
 * индексации и список — через `rag/documents` (`extraReducer` /
 * `extraEffect` на `rag/document/status_updated`).
 */

import { html, css } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { buttonStyles, iconButtonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-empty-state.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';

interface RagDocument {
    name?: string;
    document_id?: string;
    created_at?: string | number | Date;
    pages?: unknown;
    [key: string]: unknown;
}

function isRagDocument(value: unknown): value is RagDocument {
    return isPlainRecord(value);
}

function documentList(value: unknown): RagDocument[] {
    if (value === undefined || value === null) {
        return [];
    }
    if (!Array.isArray(value)) {
        throw new Error('NamespacePage: documents must be an array');
    }
    const rows: RagDocument[] = [];
    for (const item of value) {
        if (!isRagDocument(item)) {
            throw new Error('NamespacePage: document must be an object');
        }
        rows.push(item);
    }
    return rows;
}

const ACCEPT_TYPES = '.pdf,.docx,.doc,.txt,.md,.html,.csv,.xlsx,.pptx';

export class NamespacePage extends PlatformPage {
    static i18nNamespace = 'rag';

    declare namespaceId: string;
    declare _dragOver: boolean;
    private _docs: OpController;
    private _upload: OpController;
    private _remove: OpController;
    private _namespaces: ResourceController;

    static override properties = {
        namespaceId: { type: String },
        _dragOver: { state: true },
    };

    static override styles = [
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
            platform-empty-state { flex: 1; margin-top: var(--space-6); }
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

    override connectedCallback() {
        super.connectedCallback();
    }

    override updated(changed: PropertyValues<this>) {
        super.updated(changed);
        if (changed.has('namespaceId') && typeof this.namespaceId === 'string' && this.namespaceId.length > 0) {
            if (this._docs.state.loadedNamespaceId !== this.namespaceId) {
                this._docs.run({ namespace_id: this.namespaceId });
            }
        }
    }

    private _goBack() { this.navigate('namespaces'); }

    private _fileInput(): HTMLInputElement {
        const field = this.shadowRoot?.querySelector('input[type="file"]');
        if (!(field instanceof HTMLInputElement)) {
            throw new Error('NamespacePage: file input required');
        }
        return field;
    }

    private _triggerFileInput() {
        this._fileInput().click();
    }

    private _handleFileSelect(e: Event) {
        const target = e.target;
        if (!(target instanceof HTMLInputElement)) {
            throw new Error('NamespacePage: file input required');
        }
        const file = target.files === null ? null : target.files.item(0);
        if (file === null) return;
        this._uploadFile(file);
    }

    private _uploadFile(file: File) {
        if (!this.namespaceId) {
            throw new Error('NamespacePage: namespaceId is empty, cannot upload');
        }
        this._upload.run({ namespace_id: this.namespaceId, file, metadata: {} });
    }

    private async _deleteDocument(documentId: string): Promise<void> {
        if (!this.namespaceId) {
            throw new Error('NamespacePage: namespaceId is empty, cannot delete');
        }
        if (!(await platformConfirm(this.t('namespace_detail.delete_confirm')))) return;
        this._remove.run({ namespace_id: this.namespaceId, document_id: documentId });
    }

    private _handleDragOver(e: Event) { e.preventDefault(); e.stopPropagation(); this._dragOver = true; }
    private _handleDragLeave(e: Event) { e.preventDefault(); e.stopPropagation(); this._dragOver = false; }
    private _handleDrop(e: Event) {
        e.preventDefault();
        e.stopPropagation();
        this._dragOver = false;
        if (!(e instanceof DragEvent) || e.dataTransfer === null) {
            return;
        }
        const file = e.dataTransfer.files.item(0);
        if (file !== null) this._uploadFile(file);
    }

    private _findNamespace(): Record<string, unknown> | null {
        for (const ns of this._namespaces.items) {
            if (ns.name === this.namespaceId) return ns;
        }
        return null;
    }

    override render() {
        const namespace = this._findNamespace();
        const uploading = this._upload.busy;
        const documents = documentList(this._docs.state.items);
        const loading = this._docs.busy;

        if (!namespace && !this._namespaces.loading) {
            return html`<platform-empty-state icon="folder" title=${this.t('namespace_detail.not_found')}></platform-empty-state>`;
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
                    <button class="btn-icon" @click=${() => this._goBack()} title=${this.t('namespace_detail.back')}>
                        <platform-icon name="chevron-left" size="20"></platform-icon>
                    </button>
                    <div>
                        <h1 class="title">${namespace ? namespace.name : this.namespaceId}</h1>
                        <p class="subtitle">${this.t('namespace_detail.documents_count', { count: documents.length })}</p>
                    </div>
                </div>
                <div class="actions">
                    <button class="btn btn-primary" @click=${() => this._triggerFileInput()} ?disabled=${uploading}>
                        <platform-icon name="plus" size="18"></platform-icon>
                        <span>${uploading
                            ? this.t('namespace_detail.uploading_short')
                            : this.t('namespace_detail.upload_button')}</span>
                    </button>
                </div>
            </div>

            <input type="file" @change=${(e: Event) => this._handleFileSelect(e)} accept=${ACCEPT_TYPES} />

            ${loading ? html`
                <platform-empty-state loading></platform-empty-state>
            ` : documents.length === 0 ? html`
                <div class="drop-zone ${this._dragOver ? 'drag-over' : ''}"
                     @click=${() => this._triggerFileInput()}
                     @dragover=${(e: Event) => this._handleDragOver(e)}
                     @dragleave=${(e: Event) => this._handleDragLeave(e)}
                     @drop=${(e: Event) => this._handleDrop(e)}>
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
                                        <platform-icon file-icon name=${resolveFileIconKey(doc.name === undefined || doc.name === null ? '' : String(doc.name), '')} size="16"></platform-icon>
                                        ${doc.name}
                                    </div>
                                    <div class="document-meta">
                                        <span>${this.t('namespace_detail.created_at_label')} ${new Date(doc.created_at === undefined || doc.created_at === null ? '' : doc.created_at).toLocaleDateString()}</span>
                                        ${typeof doc.pages === 'number' ? html`<span>${this.t('namespace_detail.pages_count', { count: doc.pages })}</span>` : ''}
                                    </div>
                                </div>
                                <div class="document-actions">
                                    <button class="btn-icon danger"
                                            @click=${() => this._deleteDocument(doc.document_id === undefined || doc.document_id === null ? '' : String(doc.document_id))}
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
