/**
 * OfficeDocumentUploadModal — загрузка файла в каталог.
 *
 * props: { catalogId, openAfterUpload: true }.
 * useOp('office/document_upload').run({ file, title?, catalogId,
 * openAfterUpload }) → multipart POST. На SUCCEEDED фабрика навигирует
 * в editor (если openAfterUpload) и перезагружает documentsOp.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

const UPLOAD_OP_NAME = 'office/document_upload';

export class OfficeDocumentUploadModal extends PlatformFormModal {
    static modalKind = 'office.document_upload';
    static i18nNamespace = 'documents';

    static properties = {
        ...PlatformFormModal.properties,
        catalogId: { type: String },
        openAfterUpload: { type: Boolean },
        _file: { state: true },
        _title: { state: true },
        _dragOver: { state: true },
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
                display: flex; flex-direction: column;
                align-items: center; gap: var(--space-2);
            }
            .drop-zone:hover, .drop-zone.drag-over {
                border-color: var(--accent);
                background: var(--glass-solid-medium);
            }
            .drop-text { font-size: var(--text-base); font-weight: 600; color: var(--text-primary); }
            .drop-hint { font-size: var(--text-sm); color: var(--text-tertiary); }
            .selected {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                padding: var(--space-2);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-md);
            }
            input[type="file"] { display: none; }
            .footer-actions {
                display: flex; gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'sm';
        this.headerSavePrimary = true;
        this.catalogId = '';
        this.openAfterUpload = true;
        this._file = null;
        this._title = '';
        this._dragOver = false;
        this._upload = this.useOp(UPLOAD_OP_NAME);
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(this._upload.op.events.SUCCEEDED, () => this.closeAfterSave());
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.isDirty = this._file !== null;
    }

    _triggerFileInput() {
        this.shadowRoot.querySelector('input[type="file"]').click();
    }

    _onFileChange(e) {
        const file = e.target.files[0];
        if (file) this._file = file;
    }

    _onTitleChange(e) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._title = v;
    }

    _onDragOver(e) { e.preventDefault(); this._dragOver = true; }
    _onDragLeave(e) { e.preventDefault(); this._dragOver = false; }
    _onDrop(e) {
        e.preventDefault();
        this._dragOver = false;
        const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (file) this._file = file;
    }

    async _performSave() {
        if (!this._file) return;
        if (typeof this.catalogId !== 'string' || this.catalogId.length === 0) {
            throw new Error('OfficeDocumentUploadModal: catalogId prop required');
        }
        const payload = {
            file: this._file,
            catalogId: this.catalogId,
            openAfterUpload: Boolean(this.openAfterUpload),
        };
        const trimmed = this._title.trim();
        if (trimmed.length > 0) payload.title = trimmed;
        this._upload.run(payload);
    }

    _saveHeaderTitle() {
        return this._upload.busy
            ? this.t('document_upload_modal.saving')
            : this.t('document_upload_modal.submit');
    }

    renderHeader() { return this.t('document_upload_modal.header'); }

    renderSaveHeaderButton() {
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._upload.busy || this._file === null,
            title: this._saveHeaderTitle(),
        });
    }

    renderBody() {
        return html`
            <form class="form-grid" @submit=${(e) => { e.preventDefault(); this._performSave(); }}>
                <input type="file" @change=${this._onFileChange} />
                <div class="drop-zone ${this._dragOver ? 'drag-over' : ''}"
                     @click=${this._triggerFileInput}
                     @dragover=${this._onDragOver}
                     @dragleave=${this._onDragLeave}
                     @drop=${this._onDrop}>
                    <platform-icon name="cloud" size="32"></platform-icon>
                    <div class="drop-text">${this.t('document_upload_modal.drop_here')}</div>
                    <div class="drop-hint">${this.t('document_upload_modal.drop_or_choose')}</div>
                </div>
                ${this._file ? html`
                    <div class="selected">${this.t('document_upload_modal.selected_file', { name: this._file.name })}</div>
                ` : ''}
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('document_upload_modal.label_title')}
                    .placeholder=${this.t('document_upload_modal.title_placeholder')}
                    .value=${this._title}
                    ?disabled=${this._upload.busy}
                    @change=${this._onTitleChange}
                ></platform-field>
            </form>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('document_upload_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._upload.busy || this._file === null}
                        @click=${() => this._performSave()}>
                    ${this._upload.busy
                        ? this.t('document_upload_modal.saving')
                        : this.t('document_upload_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('office-document-upload-modal', OfficeDocumentUploadModal);
registerModalKind(OfficeDocumentUploadModal.modalKind, 'office-document-upload-modal');
