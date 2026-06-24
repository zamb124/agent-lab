/**
 * OfficeDocumentUploadModal — загрузка одного или нескольких файлов в каталог.
 *
 * props: { catalogId, openAfterUpload: true }.
 * Название документа — всегда original_name загружаемого файла.
 */

import { html, css, nothing } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-file-card.js';

const UPLOAD_OP_NAME = 'office/document_upload';

export class OfficeDocumentUploadModal extends PlatformFormModal {
    static modalKind = 'office.document_upload';
    static i18nNamespace = 'documents';

    static properties = {
        ...PlatformFormModal.properties,
        catalogId: { type: String },
        openAfterUpload: { type: Boolean },
        _entries: { state: true },
        _dragOver: { state: true },
        _uploading: { state: true },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
            .drop-zone {
                padding: var(--space-8);
                border: 2px dashed var(--glass-border-medium);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                text-align: center;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-2);
            }
            .drop-zone:hover, .drop-zone.drag-over {
                border-color: var(--accent);
                background: var(--glass-solid-medium);
            }
            .drop-text { font-size: var(--text-base); font-weight: 600; color: var(--text-primary); }
            .drop-hint { font-size: var(--text-sm); color: var(--text-tertiary); }
            .file-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
                gap: var(--space-3);
                max-height: 22rem;
                overflow-y: auto;
                padding: var(--space-1);
            }
            .file-cube-wrap {
                min-width: 0;
            }
            .file-cube-wrap.uploading platform-file-card {
                opacity: 0.75;
            }
            .file-cube-wrap.done platform-file-card {
                opacity: 0.55;
            }
            .file-cube-wrap.failed platform-file-card {
                outline: 2px solid var(--danger);
                outline-offset: -1px;
                border-radius: var(--radius-xl);
            }
            .cube-remove {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 1.75rem;
                height: 1.75rem;
                padding: 0;
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .cube-remove:hover {
                color: var(--danger);
                border-color: var(--danger);
            }
            .files-summary {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            input[type="file"] { display: none; }
            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.headerSavePrimary = true;
        this.catalogId = '';
        this.openAfterUpload = true;
        this._entries = [];
        this._dragOver = false;
        this._uploading = false;
        this._upload = this.useOp(UPLOAD_OP_NAME);
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.isDirty = this._pendingEntries().length > 0 || this._uploading;
    }

    _pendingEntries() {
        return this._entries.filter((entry) => entry.status === 'pending');
    }

    _newLocalId() {
        return `upload-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    }

    _addFiles(rawFiles) {
        if (!rawFiles || rawFiles.length === 0) return;
        const next = [...this._entries];
        for (const file of rawFiles) {
            if (!(file instanceof File)) continue;
            next.push({
                localId: this._newLocalId(),
                file,
                status: 'pending',
            });
        }
        this._entries = next;
    }

    _updateEntry(localId, patch) {
        this._entries = this._entries.map((entry) => {
            if (entry.localId !== localId) return entry;
            return { ...entry, ...patch };
        });
    }

    _removeEntry(localId) {
        if (this._uploading) return;
        this._entries = this._entries.filter((entry) => {
            if (entry.localId !== localId) return true;
            return entry.status !== 'pending';
        });
    }

    _entryStatusLabel(status) {
        if (status === 'uploading') return this.t('document_upload_modal.status_uploading');
        if (status === 'done') return this.t('document_upload_modal.status_done');
        if (status === 'failed') return this.t('document_upload_modal.status_failed');
        return '';
    }

    _triggerFileInput() {
        if (this._uploading) return;
        this.shadowRoot.querySelector('input[type="file"]').click();
    }

    _onFileChange(e) {
        const files = e.target.files ? Array.from(e.target.files) : [];
        e.target.value = '';
        this._addFiles(files);
    }

    _onDragOver(e) {
        e.preventDefault();
        if (this._uploading) return;
        this._dragOver = true;
    }

    _onDragLeave(e) {
        e.preventDefault();
        this._dragOver = false;
    }

    _onDrop(e) {
        e.preventDefault();
        this._dragOver = false;
        if (this._uploading) return;
        const files = e.dataTransfer && e.dataTransfer.files
            ? Array.from(e.dataTransfer.files)
            : [];
        this._addFiles(files);
    }

    async _performSave() {
        if (this._uploading) return;
        const pending = this._pendingEntries();
        if (pending.length === 0) return;
        if (typeof this.catalogId !== 'string' || this.catalogId.length === 0) {
            throw new Error('OfficeDocumentUploadModal: catalogId prop required');
        }

        this._uploading = true;
        let doneCount = 0;
        let failedCount = 0;
        let openedEditor = false;

        for (const entry of pending) {
            this._updateEntry(entry.localId, { status: 'uploading' });
            const openAfterUpload = Boolean(this.openAfterUpload)
                && pending.length === 1
                && !openedEditor;
            const result = await this._upload.run({
                file: entry.file,
                catalogId: this.catalogId,
                openAfterUpload,
                localId: entry.localId,
                suppressSuccessToast: pending.length > 1,
                suppressErrorToast: pending.length > 1,
            });
            if (result && typeof result.binding_id === 'string') {
                this._updateEntry(entry.localId, { status: 'done' });
                doneCount += 1;
                if (openAfterUpload) openedEditor = true;
            } else {
                this._updateEntry(entry.localId, { status: 'failed' });
                failedCount += 1;
            }
        }

        this._uploading = false;

        if (pending.length > 1) {
            if (failedCount === 0) {
                this.toast('document_upload_modal.upload_complete', {
                    vars: { count: String(doneCount) },
                });
            } else if (doneCount > 0) {
                this.toast('document_upload_modal.upload_partial', {
                    type: 'warning',
                    vars: { done: String(doneCount), failed: String(failedCount) },
                });
            } else {
                this.toast('document_upload_modal.upload_failed', { type: 'error' });
            }
        }

        if (failedCount === 0) {
            this.closeAfterSave();
        }
    }

    _saveHeaderTitle() {
        if (this._uploading) return this.t('document_upload_modal.saving');
        const count = this._pendingEntries().length;
        if (count > 1) {
            return this.t('document_upload_modal.submit_count', { count: String(count) });
        }
        return this.t('document_upload_modal.submit');
    }

    renderHeader() {
        return this.t('document_upload_modal.header');
    }

    renderSaveHeaderButton() {
        const pendingCount = this._pendingEntries().length;
        return this._renderHeaderSaveIcon({
            onClick: () => void this._performSave(),
            disabled: this._uploading || pendingCount === 0,
            title: this._saveHeaderTitle(),
        });
    }

    _renderFileGrid() {
        if (this._entries.length === 0) return nothing;
        return html`
            <div class="files-summary">
                ${this.t('document_upload_modal.files_count', { count: String(this._entries.length) })}
            </div>
            <div class="file-grid">
                ${this._entries.map((entry) => html`
                    <div class="file-cube-wrap ${entry.status}">
                        <platform-file-card
                            file-name=${entry.file.name}
                            mime-type=${entry.file.type}
                            file-size=${entry.file.size}
                            item-key=${entry.localId}
                            type-label=${this._entryStatusLabel(entry.status)}
                        >
                            ${entry.status === 'pending' && !this._uploading ? html`
                                <button
                                    slot="actions"
                                    type="button"
                                    class="cube-remove"
                                    title=${this.t('document_upload_modal.remove_file')}
                                    @click=${() => this._removeEntry(entry.localId)}
                                >
                                    <platform-icon name="x" size="14"></platform-icon>
                                </button>
                            ` : nothing}
                        </platform-file-card>
                    </div>
                `)}
            </div>
        `;
    }

    renderBody() {
        return html`
            <form class="form-grid" @submit=${(e) => { e.preventDefault(); void this._performSave(); }}>
                <input type="file" multiple @change=${this._onFileChange} />
                <div class="drop-zone ${this._dragOver ? 'drag-over' : ''}"
                     @click=${this._triggerFileInput}
                     @dragover=${this._onDragOver}
                     @dragleave=${this._onDragLeave}
                     @drop=${this._onDrop}>
                    <platform-icon name="cloud" size="32"></platform-icon>
                    <div class="drop-text">${this.t('document_upload_modal.drop_here')}</div>
                    <div class="drop-hint">${this.t('document_upload_modal.drop_or_choose')}</div>
                </div>
                ${this._renderFileGrid()}
            </form>
        `;
    }

    renderFooter() {
        const pendingCount = this._pendingEntries().length;
        const submitLabel = this._uploading
            ? this.t('document_upload_modal.saving')
            : (pendingCount > 1
                ? this.t('document_upload_modal.submit_count', { count: String(pendingCount) })
                : this.t('document_upload_modal.submit'));
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" ?disabled=${this._uploading} @click=${() => this.close()}>
                    ${this.t('document_upload_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._uploading || pendingCount === 0}
                        @click=${() => void this._performSave()}>
                    ${submitLabel}
                </button>
            </div>
        `;
    }
}

customElements.define('office-document-upload-modal', OfficeDocumentUploadModal);
registerModalKind(OfficeDocumentUploadModal.modalKind, 'office-document-upload-modal');
