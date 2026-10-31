/**
 * platform-file-attachments — список FileRef с upload/open.
 * layout: stack (колонка) | tiles (горизонтальный ряд равных карточек).
 */

import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { isPlainRecord } from '../events/payload.js';

function fileInput(event: Event): HTMLInputElement {
    const target = event.composedPath()[0];
    if (!(target instanceof HTMLInputElement)) {
        throw new Error('platform-file-attachments: file target must be an input');
    }
    return target;
}
import type { OpController } from '../base/use-resource.js';
import type { FactoryNameOfKind } from '../events/factory-registry.js';
import { formatFileSize } from '../utils/format-file-size.js';
import { resolveFileIconKey } from '../utils/file-icons.js';
import './platform-icon.js';

const LAYOUTS = Object.freeze({
    stack: 'stack',
    tiles: 'tiles',
});
type FileAttachmentLayout = 'stack' | 'tiles';

interface FileAttachmentRef {
    file_id: string;
    original_name: string;
    content_type: string;
    file_size: number;
    url?: string;
    [key: string]: unknown;
}

function _fileRefFromUploadResult(result: unknown): FileAttachmentRef {
    if (!isPlainRecord(result)) {
        throw new Error('platform-file-attachments: upload result must be object');
    }
    const fileId = result.file_id;
    const originalName = result.original_name;
    const contentType = result.content_type;
    const fileSize = result.file_size;
    const url = result.url;
    if (typeof fileId !== 'string' || fileId.length === 0) {
        throw new Error('platform-file-attachments: upload result.file_id required');
    }
    if (typeof originalName !== 'string' || originalName.length === 0) {
        throw new Error('platform-file-attachments: upload result.original_name required');
    }
    if (typeof contentType !== 'string' || contentType.length === 0) {
        throw new Error('platform-file-attachments: upload result.content_type required');
    }
    if (typeof fileSize !== 'number') {
        throw new Error('platform-file-attachments: upload result.file_size required');
    }
    return {
        file_id: fileId,
        original_name: originalName,
        content_type: contentType,
        file_size: fileSize,
        url: typeof url === 'string' ? url : undefined,
    };
}

function _normalizeLayout(value: unknown): FileAttachmentLayout {
    if (value === LAYOUTS.tiles) {
        return LAYOUTS.tiles;
    }
    if (value === LAYOUTS.stack || value === '' || value == null) {
        return LAYOUTS.stack;
    }
    throw new Error(`platform-file-attachments: unknown layout "${String(value)}"`);
}

export class PlatformFileAttachments extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        files: { type: Array, attribute: false },
        readonly: { type: Boolean, reflect: true },
        uploadOpName: { type: String, attribute: 'upload-op-name' },
        uploadSpec: { type: String, attribute: 'upload-spec' },
        openSource: { type: String, attribute: 'open-source' },
        layout: { type: String, reflect: true },
        compact: { type: Boolean, reflect: true },
        _uploading: { state: true },
    };
    declare files: FileAttachmentRef[];
    declare readonly: boolean;
    declare uploadOpName: FactoryNameOfKind<'async-op'>;
    declare uploadSpec: string;
    declare openSource: string;
    declare layout: string;
    declare compact: boolean;
    declare _uploading: boolean;

    private _uploadOp: OpController | null = null;

    static override styles: CSSResultGroup = css`
        :host {
            display: block;
            --file-attachment-tile-width: var(--mail-attachment-tile, 200px);
        }
        .list {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            gap: var(--space-2);
        }
        .list[data-layout='tiles'] {
            flex-direction: row;
            flex-wrap: wrap;
            align-items: stretch;
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
        .list[data-layout='tiles'] .row {
            display: flex;
            width: var(--file-attachment-tile-width);
            flex: 0 0 var(--file-attachment-tile-width);
            max-width: 100%;
            min-height: 56px;
            padding: var(--space-2);
            gap: var(--space-3);
        }
        .list[data-layout='tiles'] .row > platform-icon {
            flex-shrink: 0;
        }
        .meta {
            flex: 0 1 auto;
            min-width: 0;
            max-width: min(320px, 100%);
        }
        .list[data-layout='tiles'] .meta {
            flex: 1 1 auto;
            max-width: none;
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
        .list[data-layout='tiles'] .attach-btn {
            align-self: center;
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
        this.layout = LAYOUTS.stack;
        this.compact = false;
        this._uploading = false;
        this._uploadOp = null;
    }

    get _layout(): FileAttachmentLayout {
        return _normalizeLayout(this.layout);
    }

    _ensureUploadOp(): OpController {
        if (this._uploadOp) {
            return this._uploadOp;
        }
        if (typeof this.uploadOpName !== 'string' || this.uploadOpName.length === 0) {
            throw new Error('platform-file-attachments: uploadOpName required when not readonly');
        }
        this._uploadOp = this.useOp(this.uploadOpName);
        return this._uploadOp;
    }

    _emitFilesChange(nextFiles: FileAttachmentRef[]): void {
        this.emit('files-change', { files: nextFiles });
    }

    _open(fileRef: FileAttachmentRef): void {
        this.openFile(fileRef, { source: this.openSource });
    }

    _remove(fileId: string): void {
        const rows = Array.isArray(this.files) ? this.files : [];
        const nextFiles = rows.filter((row) => row && row.file_id !== fileId);
        this._emitFilesChange(nextFiles);
    }

    async _onFileSelected(event: Event): Promise<void> {
        const input = fileInput(event);
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
        if (!(input instanceof HTMLInputElement)) {
            return;
        }
        input.click();
    }

    _renderRow(fileRef: FileAttachmentRef): TemplateResult {
        const fileId = fileRef && typeof fileRef.file_id === 'string' ? fileRef.file_id : '';
        const originalName = fileRef && typeof fileRef.original_name === 'string' ? fileRef.original_name : fileId;
        const contentType = fileRef && typeof fileRef.content_type === 'string' ? fileRef.content_type : '';
        const fileSize = fileRef && typeof fileRef.file_size === 'number' ? fileRef.file_size : 0;
        const iconSize = this._layout === LAYOUTS.tiles ? 32 : 20;
        return html`
            <div class="row">
                <platform-icon
                    file-icon
                    name=${resolveFileIconKey(originalName, contentType)}
                    size=${iconSize}
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

    override render(): TemplateResult {
        const rows = Array.isArray(this.files) ? this.files : [];
        const layout = this._layout;
        return html`
            <div class="list" data-layout=${layout}>
                ${rows.length === 0 && this.readonly
                    ? html`<div class="empty">${this.t('file_attachments.empty')}</div>`
                    : rows.map((fileRef) => this._renderRow(fileRef))}
                ${this.readonly ? nothing : html`
                    <input type="file" @change=${(e: Event) => this._onFileSelected(e)} />
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
