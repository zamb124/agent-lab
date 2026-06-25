/**
 * platform-file-attachments — список FileRef с upload/open.
 */

import { html, css, nothing } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import { formatFileSize } from '../utils/format-file-size.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import './platform-icon.js';

function _fileRefFromUploadResult(result) {
    if (!result || typeof result !== 'object') {
        throw new Error('platform-file-attachments: upload result must be object');
    }
    if (typeof result.file_id !== 'string' || result.file_id.length === 0) {
        throw new Error('platform-file-attachments: upload result.file_id required');
    }
    if (typeof result.original_name !== 'string' || result.original_name.length === 0) {
        throw new Error('platform-file-attachments: upload result.original_name required');
    }
    if (typeof result.content_type !== 'string' || result.content_type.length === 0) {
        throw new Error('platform-file-attachments: upload result.content_type required');
    }
    if (typeof result.file_size !== 'number') {
        throw new Error('platform-file-attachments: upload result.file_size required');
    }
    return {
        file_id: result.file_id,
        original_name: result.original_name,
        content_type: result.content_type,
        file_size: result.file_size,
        url: typeof result.url === 'string' ? result.url : undefined,
    };
}

export class PlatformFileAttachments extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        files: { type: Array, attribute: false },
        readonly: { type: Boolean, reflect: true },
        uploadOpName: { type: String, attribute: 'upload-op-name' },
        uploadSpec: { type: String, attribute: 'upload-spec' },
        openSource: { type: String, attribute: 'open-source' },
        compact: { type: Boolean, reflect: true },
        _uploading: { state: true },
    };

    static styles = css`
        :host {
            display: block;
        }
        .list {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            gap: var(--space-2);
        }
        .row {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            min-width: 0;
            max-width: 100%;
            box-sizing: border-box;
            padding: var(--space-1) var(--space-2);
            border: 1px solid var(--glass-border-subtle);
            border-radius: var(--radius-md);
            background: var(--glass-tint-subtle);
        }
        .meta {
            flex: 0 1 auto;
            min-width: 0;
            max-width: min(320px, 100%);
        }
        .name {
            font-size: var(--text-sm);
            color: var(--text-primary);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .size {
            font-size: var(--text-xs);
            color: var(--text-tertiary);
        }
        .actions {
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            flex-shrink: 0;
        }
        .link-btn,
        .remove-btn,
        .attach-btn {
            border: 0;
            background: transparent;
            padding: var(--space-1);
            color: var(--text-secondary);
            cursor: pointer;
            border-radius: var(--radius-sm);
        }
        .link-btn:hover,
        .remove-btn:hover,
        .attach-btn:hover {
            background: var(--glass-solid-medium);
            color: var(--text-primary);
        }
        .attach-btn {
            display: inline-flex;
            align-items: center;
            gap: var(--space-1);
            font-size: var(--text-sm);
            padding: var(--space-1) var(--space-2);
        }
        .empty {
            font-size: var(--text-sm);
            color: var(--text-tertiary);
        }
        input[type="file"] {
            display: none;
        }
    `;

    constructor() {
        super();
        this.files = [];
        this.readonly = false;
        this.uploadOpName = 'platform/file_create';
        this.uploadSpec = '';
        this.openSource = 'platform_file_attachments';
        this.compact = false;
        this._uploading = false;
        this._uploadOp = null;
    }

    _ensureUploadOp() {
        if (this._uploadOp) {
            return this._uploadOp;
        }
        if (typeof this.uploadOpName !== 'string' || this.uploadOpName.length === 0) {
            throw new Error('platform-file-attachments: uploadOpName required when not readonly');
        }
        this._uploadOp = this.useOp(this.uploadOpName);
        return this._uploadOp;
    }

    _emitFilesChange(nextFiles) {
        this.emit('files-change', { files: nextFiles });
    }

    _open(fileRef) {
        this.openFile(fileRef, { source: this.openSource });
    }

    _remove(fileId) {
        const rows = Array.isArray(this.files) ? this.files : [];
        const nextFiles = rows.filter((row) => row && row.file_id !== fileId);
        this._emitFilesChange(nextFiles);
    }

    async _onFileSelected(event) {
        const input = event.target;
        const selected = input.files && input.files[0];
        input.value = '';
        if (!selected) {
            return;
        }
        this._uploading = true;
        try {
            if (typeof this.uploadSpec !== 'string' || this.uploadSpec.length === 0) {
                throw new Error('platform-file-attachments: upload-spec required when not readonly');
            }
            const uploadOp = this._ensureUploadOp();
            const result = await uploadOp.run({ file: selected, spec: this.uploadSpec });
            const fileRef = _fileRefFromUploadResult(result);
            const rows = Array.isArray(this.files) ? [...this.files] : [];
            rows.push(fileRef);
            this._emitFilesChange(rows);
        } finally {
            this._uploading = false;
        }
    }

    _pickFile() {
        const input = this.renderRoot.querySelector('input[type="file"]');
        if (!input) {
            return;
        }
        input.click();
    }

    _renderRow(fileRef) {
        const fileId = fileRef && typeof fileRef.file_id === 'string' ? fileRef.file_id : '';
        const originalName = fileRef && typeof fileRef.original_name === 'string' ? fileRef.original_name : fileId;
        const contentType = fileRef && typeof fileRef.content_type === 'string' ? fileRef.content_type : '';
        const fileSize = fileRef && typeof fileRef.file_size === 'number' ? fileRef.file_size : 0;
        return html`
            <div class="row">
                <platform-icon
                    file-icon
                    name=${resolveFileIconKey(originalName, contentType)}
                    size="20"
                ></platform-icon>
                <div class="meta">
                    <div class="name">${originalName}</div>
                    ${fileSize > 0 ? html`<div class="size">${formatFileSize(fileSize)}</div>` : nothing}
                </div>
                <div class="actions">
                    ${fileId ? html`
                        <button type="button" class="link-btn" title=${this.t('file_attachments.open')}
                            @click=${() => this._open(fileRef)}>
                            <platform-icon name="external-link" size="16"></platform-icon>
                        </button>
                    ` : nothing}
                    ${this.readonly ? nothing : html`
                        <button type="button" class="remove-btn" title=${this.t('file_attachments.remove')}
                            @click=${() => this._remove(fileId)}>
                            <platform-icon name="close" size="16"></platform-icon>
                        </button>
                    `}
                </div>
            </div>
        `;
    }

    render() {
        const rows = Array.isArray(this.files) ? this.files : [];
        return html`
            <div class="list">
                ${rows.length === 0 && this.readonly
                    ? html`<div class="empty">${this.t('file_attachments.empty')}</div>`
                    : rows.map((fileRef) => this._renderRow(fileRef))}
                ${this.readonly ? nothing : html`
                    <input type="file" @change=${(e) => this._onFileSelected(e)} />
                    <button
                        type="button"
                        class="attach-btn"
                        ?disabled=${this._uploading}
                        @click=${() => this._pickFile()}
                    >
                        <platform-icon name="paperclip" size="16"></platform-icon>
                        ${this.t('file_attachments.attach')}
                    </button>
                `}
            </div>
        `;
    }
}

customElements.define('platform-file-attachments', PlatformFileAttachments);
