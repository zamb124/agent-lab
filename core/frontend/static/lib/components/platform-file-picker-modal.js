/**
 * platform.file_picker — выбор файла из Documents или загрузка нового.
 *
 * Props:
 *   acceptMimePrefix — 'image/' | 'application/vnd.sqlite3' | '' (все типы)
 *   uploadOpName, uploadSpec — platform/file_create
 *   catalogsOpName, documentsOpName, searchOpName — browse ops хоста
 *   onSelect(file) — { file_id, original_name, content_type, file_size, file_category?, is_public? }
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { registerModalKind } from '../utils/modal-registry.js';
import { formatPlatformDateTime } from '../utils/format-platform-date.js';
import './platform-icon.js';
import './platform-button.js';
import './platform-file-card.js';
import './fields/platform-field.js';

const IMAGE_CATEGORY = 'image';
const DATA_TABLE_CATEGORY = 'data_table';
const DATA_TABLE_CONTENT_TYPE = 'application/vnd.sqlite3';
const DATA_TABLE_CONTENT_TYPE_LEGACY = 'application/x-sqlite3';

function _asNonEmptyString(value) {
    return typeof value === 'string' && value.length > 0 ? value : '';
}

function _fileMatchesAccept(item, acceptMimePrefix) {
    if (typeof acceptMimePrefix !== 'string' || acceptMimePrefix.length === 0) {
        return true;
    }
    if (acceptMimePrefix === 'image/') {
        return item.file_category === IMAGE_CATEGORY
            || (typeof item.content_type === 'string' && item.content_type.startsWith('image/'));
    }
    if (acceptMimePrefix === DATA_TABLE_CONTENT_TYPE) {
        return item.file_category === DATA_TABLE_CATEGORY
            || item.content_type === DATA_TABLE_CONTENT_TYPE
            || item.content_type === DATA_TABLE_CONTENT_TYPE_LEGACY;
    }
    if (typeof item.content_type === 'string' && item.content_type.startsWith(acceptMimePrefix)) {
        return true;
    }
    return false;
}

function _isSqliteLocalFile(file) {
    const name = typeof file.name === 'string' ? file.name.toLowerCase() : '';
    return file.type === DATA_TABLE_CONTENT_TYPE
        || file.type === DATA_TABLE_CONTENT_TYPE_LEGACY
        || name.endsWith('.sqlite')
        || name.endsWith('.db');
}

function _optionalIsPublic(source) {
    if (!Object.prototype.hasOwnProperty.call(source, 'is_public')) {
        return undefined;
    }
    if (typeof source.is_public !== 'boolean') {
        throw new Error('platform-file-picker: is_public must be boolean when present');
    }
    return source.is_public;
}

function _pickedFromDocument(item) {
    const fileId = _asNonEmptyString(item.file_id);
    if (fileId === '') {
        throw new Error('platform-file-picker: document.file_id required');
    }
    const title = _asNonEmptyString(item.title);
    const contentType = typeof item.content_type === 'string' ? item.content_type : '';
    const fileCategory = typeof item.file_category === 'string' ? item.file_category : '';
    const fileSize = typeof item.file_size === 'number' ? item.file_size : 0;
    const picked = {
        file_id: fileId,
        original_name: title !== '' ? title : fileId,
        content_type: contentType,
        file_size: fileSize,
        file_category: fileCategory,
    };
    const isPublic = _optionalIsPublic(item);
    if (isPublic !== undefined) {
        picked.is_public = isPublic;
    }
    return picked;
}

function _pickedFromUpload(result) {
    if (!result || typeof result !== 'object') {
        throw new Error('platform-file-picker: upload result required');
    }
    const fileId = _asNonEmptyString(result.file_id);
    if (fileId === '') {
        throw new Error('platform-file-picker: upload result.file_id required');
    }
    const originalName = _asNonEmptyString(result.original_name);
    if (originalName === '') {
        throw new Error('platform-file-picker: upload result.original_name required');
    }
    const contentType = _asNonEmptyString(result.content_type);
    if (contentType === '') {
        throw new Error('platform-file-picker: upload result.content_type required');
    }
    if (typeof result.file_size !== 'number') {
        throw new Error('platform-file-picker: upload result.file_size required');
    }
    if (typeof result.is_public !== 'boolean') {
        throw new Error('platform-file-picker: upload result.is_public required');
    }
    return {
        file_id: fileId,
        original_name: originalName,
        content_type: contentType,
        file_size: result.file_size,
        file_category: contentType.startsWith('image/')
            ? IMAGE_CATEGORY
            : (contentType === DATA_TABLE_CONTENT_TYPE || contentType === DATA_TABLE_CONTENT_TYPE_LEGACY
                ? DATA_TABLE_CATEGORY
                : ''),
        is_public: result.is_public,
    };
}

export class PlatformFilePickerModal extends PlatformModal {
    static modalKind = 'platform.file_picker';
    static i18nNamespace = 'platform';

    static properties = {
        ...PlatformModal.properties,
        acceptMimePrefix: { type: String, attribute: 'accept-mime-prefix' },
        uploadOpName: { type: String, attribute: 'upload-op-name' },
        uploadSpec: { type: String, attribute: 'upload-spec' },
        catalogsOpName: { type: String, attribute: 'catalogs-op-name' },
        documentsOpName: { type: String, attribute: 'documents-op-name' },
        searchOpName: { type: String, attribute: 'search-op-name' },
        onSelect: { attribute: false },
        _catalogId: { state: true },
        _catalogs: { state: true },
        _documents: { state: true },
        _searchQuery: { state: true },
        _searchResults: { state: true },
        _uploading: { state: true },
        _dragOver: { state: true },
        _error: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .layout {
                display: grid;
                grid-template-columns: minmax(10rem, 14rem) minmax(0, 1fr);
                gap: var(--space-4);
                min-height: 22rem;
            }
            @media (max-width: 767px) {
                .layout {
                    grid-template-columns: 1fr;
                }
            }
            .catalogs {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                max-height: 28rem;
                overflow-y: auto;
                padding-right: var(--space-1);
            }
            .catalog-btn {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border: 1px solid transparent;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
            }
            .catalog-btn:hover {
                background: var(--glass-tint-subtle);
            }
            .catalog-btn[data-active='true'] {
                background: var(--documents-selected-bg, var(--accent-subtle));
                border-color: var(--accent);
                color: var(--accent);
                font-weight: 600;
            }
            .catalog-count {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .main {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
            }
            .toolbar {
                display: flex;
                flex-wrap: nowrap;
                align-items: stretch;
                gap: var(--space-2);
            }
            .toolbar platform-field {
                flex: 1 1 auto;
                min-width: 0;
            }
            .toolbar .upload-btn {
                flex: 0 0 auto;
                align-self: stretch;
                --platform-button-icon-size: calc(
                    (var(--field-pill-padding-y) * 2)
                    + (var(--field-pill-label-size) * var(--field-pill-label-line))
                    + var(--field-pill-gap)
                    + (var(--field-pill-input-size) * var(--field-pill-input-line))
                );
                --platform-button-icon-radius: var(--field-pill-radius);
            }
            .drop-zone {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                padding: var(--space-5);
                border: 2px dashed var(--glass-border-medium);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .drop-zone:hover,
            .drop-zone[data-drag='true'] {
                border-color: var(--accent);
                background: var(--glass-solid-medium);
            }
            .drop-title {
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
            }
            .drop-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
                gap: var(--space-3);
                max-height: 18rem;
                overflow-y: auto;
                padding: var(--space-1);
            }
            .empty,
            .status,
            .error {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                padding: var(--space-3) 0;
            }
            .error {
                color: var(--error);
            }
            input[type='file'] {
                display: none;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'xl';
        this.acceptMimePrefix = '';
        this.uploadOpName = 'platform/file_create';
        this.uploadSpec = '';
        this.catalogsOpName = '';
        this.documentsOpName = '';
        this.searchOpName = '';
        this.onSelect = null;
        this._catalogId = '';
        this._catalogs = [];
        this._documents = [];
        this._searchQuery = '';
        this._searchResults = null;
        this._uploading = false;
        this._dragOver = false;
        this._error = '';
        this._catalogsOp = null;
        this._documentsOp = null;
        this._searchOp = null;
        this._uploadOp = null;
        this._localeSel = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this.heading = this.t('file_picker.title');
        this._localeSel = this.select((state) => state.i18n.locale);
        this._ensureControllers();
        void this._loadCatalogs();
    }

    _formatDate(iso) {
        if (typeof iso !== 'string' || iso.length === 0) {
            return '';
        }
        const locale = this._localeSel ? this._localeSel.value : '';
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('platform-file-picker: i18n locale required');
        }
        return formatPlatformDateTime(iso, locale);
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('open') && this.open) {
            this._error = '';
            this._searchQuery = '';
            this._searchResults = null;
            this._catalogId = '';
            this._ensureControllers();
            void this._loadCatalogs();
        }
    }

    _ensureControllers() {
        if (typeof this.catalogsOpName !== 'string' || this.catalogsOpName.length === 0) {
            throw new Error('platform-file-picker: catalogsOpName required');
        }
        if (typeof this.documentsOpName !== 'string' || this.documentsOpName.length === 0) {
            throw new Error('platform-file-picker: documentsOpName required');
        }
        if (typeof this.searchOpName !== 'string' || this.searchOpName.length === 0) {
            throw new Error('platform-file-picker: searchOpName required');
        }
        if (typeof this.uploadOpName !== 'string' || this.uploadOpName.length === 0) {
            throw new Error('platform-file-picker: uploadOpName required');
        }
        if (typeof this.uploadSpec !== 'string' || this.uploadSpec.length === 0) {
            throw new Error('platform-file-picker: uploadSpec required');
        }
        if (typeof this.onSelect !== 'function') {
            throw new Error('platform-file-picker: onSelect required');
        }
        if (!this._catalogsOp) {
            this._catalogsOp = this.useOp(this.catalogsOpName);
        }
        if (!this._documentsOp) {
            this._documentsOp = this.useOp(this.documentsOpName);
        }
        if (!this._searchOp) {
            this._searchOp = this.useOp(this.searchOpName);
        }
        if (!this._uploadOp) {
            this._uploadOp = this.useOp(this.uploadOpName);
        }
    }

    async _loadCatalogs() {
        this._ensureControllers();
        const result = await this._catalogsOp.run({});
        if (!result || typeof result !== 'object' || !Array.isArray(result.items)) {
            throw new Error('platform-file-picker: catalogs.items required');
        }
        this._catalogs = result.items;
        if (this._catalogId === '' && this._catalogs.length > 0) {
            const first = this._catalogs[0];
            if (first && typeof first.catalog_id === 'string') {
                await this._selectCatalog(first.catalog_id);
            }
        }
    }

    async _selectCatalog(catalogId) {
        if (typeof catalogId !== 'string' || catalogId.length === 0) {
            throw new Error('platform-file-picker: catalogId required');
        }
        this._catalogId = catalogId;
        this._searchResults = null;
        this._error = '';
        const result = await this._documentsOp.run({ catalog_id: catalogId });
        if (!result || typeof result !== 'object' || !Array.isArray(result.items)) {
            throw new Error('platform-file-picker: documents.items required');
        }
        this._documents = result.items;
    }

    async _onSearchChange(event) {
        const value = event.detail && typeof event.detail.value === 'string'
            ? event.detail.value
            : '';
        this._searchQuery = value;
        if (value.trim() === '') {
            this._searchResults = null;
            return;
        }
        const result = await this._searchOp.run({ q: value.trim() });
        if (!result || typeof result !== 'object' || !Array.isArray(result.items)) {
            throw new Error('platform-file-picker: search.items required');
        }
        this._searchResults = result.items;
    }

    _visibleDocuments() {
        const source = Array.isArray(this._searchResults) ? this._searchResults : this._documents;
        return source.filter((item) => _fileMatchesAccept(item, this.acceptMimePrefix));
    }

    _acceptAttr() {
        if (this.acceptMimePrefix === 'image/') {
            return 'image/*';
        }
        if (this.acceptMimePrefix === DATA_TABLE_CONTENT_TYPE) {
            return '.sqlite,.db,application/vnd.sqlite3,application/x-sqlite3';
        }
        return '*/*';
    }

    _pickLocalFile() {
        const input = this.renderRoot.querySelector('input[type="file"]');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('platform-file-picker: file input missing');
        }
        input.click();
    }

    async _uploadFile(file) {
        if (!(file instanceof File)) {
            throw new Error('platform-file-picker: File required');
        }
        if (this.acceptMimePrefix === 'image/' && !file.type.startsWith('image/')) {
            this._error = this.t('file_picker.error_not_image');
            return;
        }
        if (this.acceptMimePrefix === DATA_TABLE_CONTENT_TYPE && !_isSqliteLocalFile(file)) {
            this._error = this.t('file_picker.error_not_data_table');
            return;
        }
        this._uploading = true;
        this._error = '';
        try {
            const result = await this._uploadOp.run({
                file,
                spec: this.uploadSpec,
            });
            const picked = _pickedFromUpload(result);
            this.onSelect(picked);
            this.close();
        } finally {
            this._uploading = false;
        }
    }

    async _onLocalFileSelected(event) {
        const input = event.target;
        const file = input.files && input.files[0];
        input.value = '';
        if (!file) {
            return;
        }
        await this._uploadFile(file);
    }

    _onDrop(event) {
        event.preventDefault();
        this._dragOver = false;
        const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
        if (!file) {
            return;
        }
        void this._uploadFile(file);
    }

    _selectDocument(item) {
        if (!_fileMatchesAccept(item, this.acceptMimePrefix)) {
            this._error = this.t('file_picker.error_type_mismatch');
            return;
        }
        const picked = _pickedFromDocument(item);
        this.onSelect(picked);
        this.close();
    }

    renderBody() {
        const catalogs = Array.isArray(this._catalogs) ? this._catalogs : [];
        const docs = this._visibleDocuments();
        const searching = typeof this._searchQuery === 'string' && this._searchQuery.trim() !== '';

        return html`
            <div class="layout">
                <aside class="catalogs" aria-label=${this.t('file_picker.catalogs')}>
                    ${catalogs.length === 0
                        ? html`<div class="empty">${this.t('file_picker.no_catalogs')}</div>`
                        : catalogs.map((catalog) => html`
                            <button
                                type="button"
                                class="catalog-btn"
                                data-active=${catalog.catalog_id === this._catalogId ? 'true' : 'false'}
                                @click=${() => void this._selectCatalog(catalog.catalog_id)}
                            >
                                <span>${catalog.title}</span>
                                <span class="catalog-count">${catalog.file_count}</span>
                            </button>
                        `)}
                </aside>
                <div class="main">
                    <div class="toolbar">
                        <platform-field
                            type="string"
                            input-type="search"
                            .label=${this.t('file_picker.search_label')}
                            .placeholder=${this.t('file_picker.search_placeholder')}
                            .value=${this._searchQuery}
                            @change=${(event) => void this._onSearchChange(event)}
                        ></platform-field>
                        <platform-button
                            class="upload-btn"
                            variant="secondary"
                            icon-only
                            ?disabled=${this._uploading}
                            title=${this.t('file_picker.upload')}
                            aria-label=${this.t('file_picker.upload')}
                            @click=${this._pickLocalFile}
                        >
                            <platform-icon name="upload" size="22"></platform-icon>
                        </platform-button>
                    </div>

                    <div
                        class="drop-zone"
                        data-drag=${this._dragOver ? 'true' : 'false'}
                        @click=${this._pickLocalFile}
                        @dragover=${(event) => {
                            event.preventDefault();
                            this._dragOver = true;
                        }}
                        @dragleave=${() => { this._dragOver = false; }}
                        @drop=${(event) => this._onDrop(event)}
                    >
                        <platform-icon name="upload" size="28"></platform-icon>
                        <div class="drop-title">
                            ${this._uploading
                                ? this.t('file_picker.uploading')
                                : this.t('file_picker.drop_title')}
                        </div>
                        <div class="drop-hint">${this.t('file_picker.drop_hint')}</div>
                    </div>

                    ${this._error
                        ? html`<div class="error" role="alert">${this._error}</div>`
                        : nothing}

                    ${this._documentsOp && this._documentsOp.busy && !searching
                        ? html`<div class="status">${this.t('file_picker.loading')}</div>`
                        : nothing}

                    ${docs.length === 0
                        ? html`<div class="empty">${this.t('file_picker.empty')}</div>`
                        : html`
                            <div class="grid">
                                ${docs.map((item) => html`
                                    <platform-file-card
                                        .fileName=${item.title}
                                        .mimeType=${item.file_category === IMAGE_CATEGORY
                                            ? 'image/png'
                                            : ''}
                                        .fileSize=${item.file_size}
                                        .dateLabel=${this._formatDate(
                                            typeof item.updated_at === 'string' ? item.updated_at : '',
                                        )}
                                        .itemKey=${item.file_id}
                                        @open=${() => this._selectDocument(item)}
                                    ></platform-file-card>
                                `)}
                            </div>
                        `}
                </div>
            </div>
            <input
                type="file"
                accept=${this._acceptAttr()}
                @change=${(event) => {
                    event.stopPropagation();
                    void this._onLocalFileSelected(event);
                }}
            />
        `;
    }

    renderFooter() {
        return html`
            <platform-button variant="ghost" @click=${() => this.close()}>
                ${this.t('file_picker.cancel')}
            </platform-button>
        `;
    }
}

customElements.define('platform-file-picker-modal', PlatformFilePickerModal);
registerModalKind(PlatformFilePickerModal.modalKind, 'platform-file-picker-modal');
