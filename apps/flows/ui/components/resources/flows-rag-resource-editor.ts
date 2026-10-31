/**
 * flows-rag-resource-editor — ресурс type=rag (bind к platform Namespace).
 *
 * DX: понятные labels/hints/placeholders; создание namespace — в том же
 * field-pill (suffix +), без отдельной громоздкой формы.
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController, SliceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/rag/platform-rag-retrieval-panel.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import { formatPlatformDate } from '@platform/lib/utils/format-platform-date.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import {
    buildAdvancedRetrievalPayloadFromPanel,
    panelValueFromSearchOptions,
} from '@platform/lib/rag/pack_search_request_options.js';
import './flows-base-resource-editor.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';

function recordCopy(value: unknown): Record<string, unknown> {
    if (!isPlainObject(value)) return {};
    return { ...value };
}

function configText(cfg: Record<string, unknown>, key: string): string {
    const value = cfg[key];
    return typeof value === 'string' ? value : '';
}

function configNumber(cfg: Record<string, unknown>, key: string): number | null {
    const value = cfg[key];
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

const NAMESPACE_NAME_PATTERN = /^[a-z][a-z0-9_-]{0,62}[a-z0-9]$|^[a-z]$/;
const DEFAULT_TOP_K = 5;
const DEFAULT_CHUNK_SIZE = 512;
const DEFAULT_CHUNK_OVERLAP = 50;

export class FlowsRagResourceEditor extends PlatformElement {
    static override properties: PropertyDeclarations = {
        resourceId: { type: String },
        resource: { type: Object },
        nodeId: { type: String },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
        _showCreate: { state: true },
        _createName: { state: true },
        _createDescription: { state: true },
        _dragOver: { state: true },
    }
    declare resourceId: string;
    declare resource: Record<string, unknown> | null;
    declare nodeId: string;
    declare compactHeader: boolean;
    declare _showCreate: boolean;
    declare _createName: string;
    declare _createDescription: string;
    declare _dragOver: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .hint {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.45;
                margin: 0 0 var(--space-3);
            }
            .section {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                margin-bottom: var(--space-4);
            }
            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            .ns-card {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
            }
            .enum-suffix-actions {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                flex: 0 0 auto;
                padding-right: var(--space-1);
            }
            .grid-2 {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
                gap: var(--space-2);
            }
            .docs-toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .docs-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .doc-row {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
            }
            .doc-main {
                display: flex;
                flex-direction: column;
                gap: 2px;
                min-width: 0;
            }
            .doc-name {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                min-width: 0;
            }
            .doc-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .doc-error {
                font-size: var(--text-xs);
                color: var(--error);
            }
            .drop-zone {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                padding: var(--space-4);
                border: 1px dashed var(--border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .drop-zone.drag-over {
                border-color: var(--accent);
                background: var(--glass-solid-medium);
            }
            .drop-zone[aria-disabled='true'] {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .hidden-file {
                display: none;
            }
            .result-card {
                padding: var(--space-3);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            .result-header {
                display: flex;
                justify-content: space-between;
                gap: var(--space-2);
                align-items: flex-start;
            }
            .result-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .result-meta {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .result-score {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--accent);
                flex: 0 0 auto;
            }
            .result-content {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                white-space: pre-wrap;
                word-break: break-word;
            }
        `,
    ];
    private _namespaces: ResourceController;
    private _searchDefaults: OpController;
    private _docs: OpController;
    private _upload: OpController;
    private _remove: OpController;
    private _ragNodeTest: ControllerFor<'flows/rag_node_test'>;
    private _locale: SelectController<string>;
    private _pendingCreateName: string;
    private _defaultsLoaded: boolean;
    private _namespacesLoaded: boolean;

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
        this.nodeId = '';
        this.compactHeader = false;
        this._showCreate = false;
        this._createName = '';
        this._createDescription = '';
        this._dragOver = false;
        this._pendingCreateName = '';
        this._namespaces = this.useResource('rag/namespaces');
        this._searchDefaults = this.useOp('rag/search_defaults');
        this._docs = this.useOp('rag/documents');
        this._upload = this.useOp('rag/document_upload');
        this._remove = this.useOp('rag/document_remove');
        this._ragNodeTest = this.useSlice('flows/rag_node_test');
        this._locale = this.select((state) => state.i18n.locale);
        this._defaultsLoaded = false;
        this._namespacesLoaded = false;
        this.useEvent(this._namespaces.resource.events.CREATED, (event) => {
            const payload = isPlainObject(event.payload) ? event.payload : null;
            const item = payload !== null && isPlainObject(payload.item) ? payload.item : null;
            const name = item === null ? undefined : item.name;
            if (typeof name !== 'string' || name.length === 0) {
                throw new Error('flows-rag-resource-editor: created namespace name required');
            }
            if (this._pendingCreateName.length === 0 || name !== this._pendingCreateName) {
                return;
            }
            const description = item !== null && typeof item.description === 'string' && item.description.length > 0
                ? item.description
                : null;
            this._pendingCreateName = '';
            this._emitConfig({
                namespace: name,
                namespace_description: description,
            });
            this._showCreate = false;
            this._createName = '';
            this._createDescription = '';
        });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (!this._defaultsLoaded) {
            this._defaultsLoaded = true;
            void this._searchDefaults.run({});
        }
        if (!this._namespacesLoaded) {
            this._namespacesLoaded = true;
            this._namespaces.load({});
        }
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        const namespace = this._namespaceValue();
        if (namespace.length === 0) {
            return;
        }
        if (this._docs.state.loadedNamespaceId !== namespace) {
            void this._docs.run({ namespace_id: namespace });
        }
    }

    _namespaceValue() {
        const namespace = (this._cfg()).namespace;
        return typeof namespace === 'string' ? namespace.trim() : '';
    }

    _cfg(): Record<string, unknown> {
        if (this.resource === null) return {};
        return recordCopy(this.resource.config);
    }

    _emitConfig(patch: Record<string, unknown>) {
        const base = this._cfg();
        this.emit('change', {
            resourceId: this.resourceId,
            patch: { config: { ...base, ...patch } },
        });
    }

    _namespaceOptions() {
        const items = this._namespaces.items;
        if (!Array.isArray(items)) {
            throw new Error('flows-rag-resource-editor: namespaces.items array required');
        }
        const opts = [];
        for (const item of items) {
            if (!isPlainObject(item)) {
                continue;
            }
            const name = typeof item.name === 'string' ? item.name.trim() : '';
            if (name.length === 0) {
                continue;
            }
            const kind = typeof item.kind === 'string' ? item.kind : '';
            if (kind === 'technical' || kind === 'personal') {
                continue;
            }
            opts.push({ value: name, label: name });
        }
        const current = configText(this._cfg(), 'namespace').trim();
        if (current.length > 0 && !opts.some((o) => o.value === current)) {
            opts.unshift({ value: current, label: current });
        }
        return opts;
    }

    _onNamespaceChange(e: CustomEvent) {
        const d = e.detail;
        if (!isPlainObject(d) || typeof d.value !== 'string') {
            throw new Error('flows-rag-resource-editor: namespace change');
        }
        const namespace = d.value.trim();
        if (namespace.length === 0) {
            throw new Error('flows-rag-resource-editor: namespace required');
        }
        this._emitConfig({ namespace });
    }

    _onTopK(e: CustomEvent) {
        const d = e.detail;
        if (!isPlainObject(d)) {
            throw new Error('flows-rag-resource-editor: top_k change');
        }
        const raw = d.value;
        if (raw === '' || raw === null || raw === undefined) {
            this._emitConfig({ default_top_k: DEFAULT_TOP_K });
            return;
        }
        const n = typeof raw === 'number' ? raw : Number(raw);
        if (!Number.isFinite(n) || n < 1) {
            throw new Error('flows-rag-resource-editor: default_top_k >= 1');
        }
        this._emitConfig({ default_top_k: Math.trunc(n) });
    }

    _onCollectionId(e: CustomEvent) {
        const d = e.detail;
        if (!isPlainObject(d) || typeof d.value !== 'string') {
            throw new Error('flows-rag-resource-editor: collection_id change');
        }
        const collectionId = d.value.trim();
        const prevFilters = recordCopy(this._cfg().filters);
        if (collectionId.length === 0) {
            delete prevFilters.collection_id;
            this._emitConfig({
                filters: Object.keys(prevFilters).length > 0 ? prevFilters : null,
            });
            return;
        }
        this._emitConfig({ filters: { ...prevFilters, collection_id: collectionId } });
    }

    _onTtl(e: CustomEvent) {
        const d = e.detail;
        if (!isPlainObject(d)) {
            throw new Error('flows-rag-resource-editor: ttl change');
        }
        const raw = d.value;
        if (raw === '' || raw === null || raw === undefined) {
            this._emitConfig({ default_ttl_seconds: null });
            return;
        }
        const n = typeof raw === 'number' ? raw : Number(raw);
        if (!Number.isFinite(n) || n < 0) {
            throw new Error('flows-rag-resource-editor: default_ttl_seconds >= 0');
        }
        this._emitConfig({ default_ttl_seconds: Math.trunc(n) });
    }

    _onNamespaceDescription(e: CustomEvent) {
        const d = e.detail;
        if (!isPlainObject(d) || typeof d.value !== 'string') {
            throw new Error('flows-rag-resource-editor: namespace_description change');
        }
        const text = d.value.trim();
        this._emitConfig({ namespace_description: text.length === 0 ? null : text });
        if (this._showCreate) {
            this._createDescription = d.value;
        }
    }

    _onChunkSize(e: CustomEvent) {
        this._patchIndexSplit('chunk_size', e);
    }

    _onChunkOverlap(e: CustomEvent) {
        this._patchIndexSplit('chunk_overlap', e);
    }

    _patchIndexSplit(field: string, e: CustomEvent) {
        const d = e.detail;
        if (!isPlainObject(d)) {
            throw new Error(`flows-rag-resource-editor: ${field} change`);
        }
        const raw = d.value;
        if (raw === '' || raw === null || raw === undefined) {
            const ipc = recordCopy(this._cfg().index_profile_config);
            const split = recordCopy(ipc.split);
            delete split[field];
            if (Object.keys(split).length === 0) {
                delete ipc.split;
            } else {
                ipc.split = split;
            }
            this._emitConfig({
                index_profile_config: Object.keys(ipc).length > 0 ? ipc : null,
            });
            return;
        }
        const n = typeof raw === 'number' ? raw : Number(raw);
        if (!Number.isFinite(n) || n < 0) {
            throw new Error(`flows-rag-resource-editor: ${field} invalid`);
        }
        const ipc = recordCopy(this._cfg().index_profile_config);
        const split = recordCopy(ipc.split);
        split[field] = Math.trunc(n);
        ipc.split = split;
        this._emitConfig({ index_profile_config: ipc });
    }

    _onRetrievalPanelChange(e: CustomEvent) {
        const d = e.detail;
        if (!isPlainObject(d) || !isPlainObject(d.value)) {
            throw new Error('flows-rag-resource-editor: retrieval panel change');
        }
        const packed = buildAdvancedRetrievalPayloadFromPanel(d.value);
        this._emitConfig({
            search_options: Object.keys(packed).length > 0 ? packed : null,
        });
    }

    _platformDefaults() {
        const result = this._searchDefaults.lastResult;
        return isPlainObject(result) ? result : null;
    }

    _collectionId() {
        const filters = (this._cfg()).filters;
        if (!isPlainObject(filters)) {
            return '';
        }
        return typeof filters.collection_id === 'string' ? filters.collection_id : '';
    }

    _chunkField(field: string) {
        const ipc = (this._cfg()).index_profile_config;
        if (!isPlainObject(ipc) || !isPlainObject(ipc.split)) {
            return '';
        }
        const raw = ipc.split[field];
        return typeof raw === 'number' && Number.isFinite(raw) ? String(raw) : '';
    }

    _enterCreate() {
        const current = configText(this._cfg(), 'namespace');
        this._createName = current.startsWith('kb-') ? current : '';
        this._createDescription = configText(this._cfg(), 'namespace_description');
        this._showCreate = true;
    }

    _cancelCreate() {
        this._showCreate = false;
        this._createName = '';
        this._createDescription = '';
        this._pendingCreateName = '';
    }

    _createNamespace() {
        const name = (this._createName.trim());
        if (!NAMESPACE_NAME_PATTERN.test(name)) {
            this.toast('rag_resource_editor.namespace_name_invalid', { type: 'error' });
            return;
        }
        const description = (this._createDescription.trim());
        const descriptionValue = description.length === 0 ? null : description;
        this._pendingCreateName = name;
        const requested = this._namespaces.create({
            name,
            description: descriptionValue,
        });
        if (requested === undefined) {
            this._pendingCreateName = '';
        }
    }

    _statusLabel(status: string) {
        if (status === 'pending') {
            return this.t('rag_resource_editor.status_pending');
        }
        if (status === 'processing') {
            return this.t('rag_resource_editor.status_processing');
        }
        if (status === 'completed') {
            return this.t('rag_resource_editor.status_completed');
        }
        if (status === 'failed') {
            return this.t('rag_resource_editor.status_failed');
        }
        throw new Error(`flows-rag-resource-editor: unknown document status ${status}`);
    }

    _uploadMetadata() {
        const metadata: Record<string, unknown> = {};
        const ttl = (this._cfg()).default_ttl_seconds;
        if (typeof ttl === 'number' && Number.isFinite(ttl)) {
            metadata.ttl_seconds = Math.trunc(ttl);
        }
        const collectionId = this._collectionId();
        if (collectionId.length > 0) {
            metadata.collection_id = collectionId;
        }
        return metadata;
    }

    _uploadFile(file: File) {
        const namespace = this._namespaceValue();
        if (namespace.length === 0) {
            throw new Error('flows-rag-resource-editor: namespace required for upload');
        }
        if (!(file instanceof File)) {
            throw new Error('flows-rag-resource-editor: File required');
        }
        void this._upload.run({
            namespace_id: namespace,
            file,
            metadata: this._uploadMetadata(),
        });
    }

    _triggerFileInput() {
        if (this._namespaceValue().length === 0) {
            throw new Error('flows-rag-resource-editor: namespace required for upload');
        }
        const input = this.renderRoot.querySelector('input[type="file"]');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('flows-rag-resource-editor: file input missing');
        }
        input.click();
    }

    _onFileInputChange(e: Event) {
        const input = e.target;
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('flows-rag-resource-editor: file input change');
        }
        const selected = input.files === null || input.files.length === 0 ? undefined : input.files[0];
        input.value = '';
        if (selected === undefined) return;
        this._uploadFile(selected);
    }

    _onDragOver(e: Event) {
        e.preventDefault();
        e.stopPropagation();
        if (this._namespaceValue().length === 0) {
            return;
        }
        this._dragOver = true;
    }

    _onDragLeave(e: Event) {
        e.preventDefault();
        e.stopPropagation();
        this._dragOver = false;
    }

    _onDrop(e: Event) {
        e.preventDefault();
        e.stopPropagation();
        this._dragOver = false;
        if (this._namespaceValue().length === 0) {
            throw new Error('flows-rag-resource-editor: namespace required for upload');
        }
        if (!(e instanceof DragEvent)) {
            throw new Error('flows-rag-resource-editor: drop event required');
        }
        const transfer = e.dataTransfer;
        const files = transfer === null ? null : transfer.files;
        const dropped = files === null || files.length === 0 ? undefined : files[0];
        if (dropped === undefined) return;
        this._uploadFile(dropped);
    }

    async _removeDocument(documentId: unknown) {
        if (typeof documentId !== 'string' || documentId.length === 0) {
            throw new Error('flows-rag-resource-editor: documentId required');
        }
        const namespace = this._namespaceValue();
        if (namespace.length === 0) {
            throw new Error('flows-rag-resource-editor: namespace required for remove');
        }
        const confirmed = await platformConfirm(this.t('rag_resource_editor.documents_remove_confirm'), {
            title: this.t('rag_resource_editor.documents_remove_confirm_title'),
            variant: 'danger',
            confirmVariant: 'danger',
        });
        if (!confirmed) {
            return;
        }
        await this._remove.run({ namespace_id: namespace, document_id: documentId });
    }

    _docCreatedAt(doc: unknown) {
        if (!isPlainObject(doc)) return null;
        if (typeof doc.created_at === 'string' && doc.created_at.length > 0) return doc.created_at;
        if (isPlainObject(doc.metadata) && typeof doc.metadata.created_at === 'string') return doc.metadata.created_at;
        return null;
    }

    _onTestQueryChange(e: CustomEvent) {
        if (typeof this.nodeId !== 'string' || this.nodeId.length === 0) {
            throw new Error('flows-rag-resource-editor: nodeId required for test query');
        }
        const d = e.detail;
        if (!isPlainObject(d) || typeof d.value !== 'string') {
            throw new Error('flows-rag-resource-editor: test query change');
        }
        (this._ragNodeTest.setQuery({ nodeId: this.nodeId, query: d.value }));
    }

    _testQueryValue() {
        if (typeof this.nodeId !== 'string' || this.nodeId.length === 0) {
            return '';
        }
        const map = this._ragNodeTest.value.queryByNodeId;
        if (!isPlainObject(map)) {
            throw new Error('flows-rag-resource-editor: queryByNodeId object required');
        }
        if (!Object.prototype.hasOwnProperty.call(map, this.nodeId)) {
            return '';
        }
        const query = (map)[this.nodeId];
        if (typeof query !== 'string') {
            throw new Error('flows-rag-resource-editor: query must be string');
        }
        return query;
    }

    _testSearchResult() {
        if (typeof this.nodeId !== 'string' || this.nodeId.length === 0) {
            return null;
        }
        const byId = this._ragNodeTest.value.resultByNodeId;
        if (!isPlainObject(byId)) {
            throw new Error('flows-rag-resource-editor: resultByNodeId object required');
        }
        if (!Object.prototype.hasOwnProperty.call(byId, this.nodeId)) {
            return null;
        }
        return (byId)[this.nodeId];
    }

    _localeValue() {
        const locale = this._locale.value;
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('flows-rag-resource-editor: i18n.locale required');
        }
        return locale;
    }

    _renderDocumentsSection(namespace: string) {
        const enabled = namespace.length > 0;
        const items = this._docs.state.items;
        if (!Array.isArray(items)) {
            throw new Error('flows-rag-resource-editor: documents items array required');
        }
        const uploading = this._upload.busy === true;
        const loading = this._docs.busy === true;
        return html`
            <div class="section">
                <div class="docs-toolbar">
                    <div class="section-title">${this.t('rag_resource_editor.section_documents')}</div>
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="dense"
                        title=${this.t('rag_resource_editor.documents_upload')}
                        aria-label=${this.t('rag_resource_editor.documents_upload')}
                        ?disabled=${!enabled || uploading}
                        @click=${() => this._triggerFileInput()}
                    >
                        ${uploading
                            ? html`<platform-spinner size="sm" aria-hidden="true"></platform-spinner>`
                            : html`<platform-icon name="paperclip" size="16"></platform-icon>`}
                    </platform-button>
                </div>
                <input
                    class="hidden-file"
                    type="file"
                    @change=${this._onFileInputChange}
                    ?disabled=${!enabled || uploading}
                />
                ${!enabled
                    ? html`<p class="hint">${this.t('rag_resource_editor.documents_disabled')}</p>`
                    : loading
                        ? html`<p class="hint"><platform-spinner size="xs"></platform-spinner> ${this.t('rag_resource_editor.documents_loading')}</p>`
                        : items.length === 0
                            ? html`
                                <div
                                    class="drop-zone ${this._dragOver ? 'drag-over' : ''}"
                                    role="button"
                                    tabindex="0"
                                    aria-disabled="false"
                                    @click=${() => this._triggerFileInput()}
                                    @keydown=${(e: KeyboardEvent) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            this._triggerFileInput();
                                        }
                                    }}
                                    @dragover=${this._onDragOver}
                                    @dragleave=${this._onDragLeave}
                                    @drop=${this._onDrop}
                                >
                                    <platform-icon name="cloud" size="20"></platform-icon>
                                    <span>${uploading
                                        ? this.t('rag_resource_editor.uploading')
                                        : this.t('rag_resource_editor.documents_drop')}</span>
                                </div>
                            `
                            : html`
                                <div
                                    class="docs-list"
                                    @dragover=${this._onDragOver}
                                    @dragleave=${this._onDragLeave}
                                    @drop=${this._onDrop}
                                >
                                    ${items.map((doc) => this._renderDocumentRow(doc))}
                                </div>
                            `}
            </div>
        `;
    }

    _renderDocumentRow(doc: unknown) {
        if (!isPlainObject(doc) || typeof doc.document_id !== 'string') {
            throw new Error('flows-rag-resource-editor: document_id required');
        }
        if (typeof doc.name !== 'string') {
            throw new Error('flows-rag-resource-editor: document name required');
        }
        if (typeof doc.status !== 'string') {
            throw new Error('flows-rag-resource-editor: document status required');
        }
        const createdAt = this._docCreatedAt(doc);
        const chunks = typeof doc.chunks_count === 'number'
            ? doc.chunks_count
            : (isPlainObject(doc.metadata) && typeof doc.metadata.chunks_count === 'number'
                ? doc.metadata.chunks_count
                : null);
        const errorMessage = isPlainObject(doc.metadata) && typeof doc.metadata.error_message === 'string'
            ? doc.metadata.error_message
            : '';
        return html`
            <div class="doc-row">
                <div class="doc-main">
                    <div class="doc-name">
                        <platform-icon file-icon name=${resolveFileIconKey(doc.name, '')} size="14"></platform-icon>
                        <span>${doc.name}</span>
                    </div>
                    <div class="doc-meta">
                        ${this._statusLabel(doc.status)}
                        ${chunks !== null
                            ? html` · ${this.t('rag_resource_editor.documents_chunks', { count: String(chunks) })}`
                            : nothing}
                        ${createdAt !== null
                            ? html` · ${formatPlatformDate(createdAt, this._localeValue())}`
                            : nothing}
                    </div>
                    ${errorMessage.length > 0
                        ? html`<div class="doc-error">${errorMessage}</div>`
                        : nothing}
                </div>
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    title=${this.t('rag_resource_editor.documents_remove')}
                    aria-label=${this.t('rag_resource_editor.documents_remove')}
                    @click=${() => { void this._removeDocument(doc.document_id); }}
                >
                    <platform-icon name="trash" size="14"></platform-icon>
                </platform-button>
            </div>
        `;
    }

    _renderTestSection() {
        if (typeof this.nodeId !== 'string' || this.nodeId.length === 0) {
            return '';
        }
        const result = this._testSearchResult();
        if (result !== null && !isPlainObject(result)) {
            throw new Error('flows-rag-resource-editor: search result.results array required');
        }
        const hits = result === null ? null : result.results;
        if (hits !== null && !Array.isArray(hits)) {
            throw new Error('flows-rag-resource-editor: search result.results array required');
        }
        return html`
            <div class="section">
                <div class="section-title">${this.t('rag_resource_editor.section_test')}</div>
                <platform-field
                    pill-density="compact"
                    mode="edit"
                    type="text"
                    .label=${this.t('rag_resource_editor.field_test_query')}
                    .hint=${this.t('rag_resource_editor.hint_test_query')}
                    .placeholder=${this.t('rag_resource_editor.test_query_placeholder')}
                    .value=${this._testQueryValue()}
                    @change=${this._onTestQueryChange}
                ></platform-field>
                ${hits === null
                    ? nothing
                    : hits.length === 0
                        ? html`<p class="hint">${this.t('rag_resource_editor.test_results_empty')}</p>`
                        : html`
                            <div class="docs-list">
                                ${hits.map((hit) => this._renderSearchHit(hit))}
                            </div>
                        `}
            </div>
        `;
    }

    _renderSearchHit(hit: unknown) {
        if (!isPlainObject(hit)) {
            throw new Error('flows-rag-resource-editor: search hit object required');
        }
        if (typeof hit.document_name !== 'string' || hit.document_name.length === 0) {
            throw new Error('flows-rag-resource-editor: hit.document_name required');
        }
        if (typeof hit.content !== 'string') {
            throw new Error('flows-rag-resource-editor: hit.content required');
        }
        if (typeof hit.score !== 'number' || !Number.isFinite(hit.score)) {
            throw new Error('flows-rag-resource-editor: hit.score number required');
        }
        const pageLabel = typeof hit.page_label === 'string' && hit.page_label.length > 0
            ? hit.page_label
            : '';
        return html`
            <div class="result-card">
                <div class="result-header">
                    <div>
                        <div class="result-title">${hit.document_name}</div>
                        ${pageLabel.length > 0
                            ? html`<div class="result-meta">${this.t('rag_resource_editor.test_page_label', { label: pageLabel })}</div>`
                            : nothing}
                    </div>
                    <div class="result-score">${(hit.score * 100).toFixed(1)}%</div>
                </div>
                <div class="result-content">${hit.content}</div>
            </div>
        `;
    }

    _renderNamespaceCard(namespace: string, nsDescription: string) {
        if (this._showCreate) {
            return html`
                <div class="ns-card">
                    <platform-field
                        pill-density="compact"
                        mode="edit"
                        type="string"
                        .label=${this.t('rag_resource_editor.field_namespace')}
                        .hint=${this.t('rag_resource_editor.hint_namespace_create')}
                        .placeholder=${this.t('rag_resource_editor.namespace_create_placeholder')}
                        .value=${this._createName}
                        @change=${(e: CustomEvent) => {
                            const d = e.detail;
                            if (!isPlainObject(d) || typeof d.value !== 'string') {
                                throw new Error('create name');
                            }
                            this._createName = d.value;
                        }}
                    >
                        <span class="enum-suffix-actions" slot="suffix">
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="dense"
                                title=${this.t('rag_resource_editor.create_submit')}
                                aria-label=${this.t('rag_resource_editor.create_submit')}
                                ?disabled=${this._namespaces.createInFlight}
                                @click=${() => { void this._createNamespace(); }}
                            >
                                <platform-icon name="check" size="14"></platform-icon>
                            </platform-button>
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="dense"
                                title=${this.t('rag_resource_editor.create_cancel')}
                                aria-label=${this.t('rag_resource_editor.create_cancel')}
                                @click=${this._cancelCreate}
                            >
                                <platform-icon name="close" size="14"></platform-icon>
                            </platform-button>
                        </span>
                    </platform-field>
                    <platform-field
                        pill-density="compact"
                        mode="edit"
                        type="text"
                        .label=${this.t('rag_resource_editor.field_namespace_description')}
                        .hint=${this.t('rag_resource_editor.hint_namespace_description')}
                        .placeholder=${this.t('rag_resource_editor.namespace_description_placeholder')}
                        .value=${this._createDescription}
                        @change=${(e: CustomEvent) => {
                            const d = e.detail;
                            if (!isPlainObject(d) || typeof d.value !== 'string') {
                                throw new Error('create description');
                            }
                            this._createDescription = d.value;
                        }}
                    ></platform-field>
                </div>
            `;
        }
        return html`
            <div class="ns-card">
                <platform-field
                    pill-density="compact"
                    mode="edit"
                    type="enum"
                    .label=${this.t('rag_resource_editor.field_namespace')}
                    .hint=${this.t('rag_resource_editor.hint_namespace')}
                    .placeholder=${this.t('rag_resource_editor.namespace_placeholder')}
                    .value=${namespace}
                    .config=${{ values: this._namespaceOptions() }}
                    @change=${this._onNamespaceChange}
                >
                    <span class="enum-suffix-actions" slot="suffix">
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            title=${this.t('rag_resource_editor.create_toggle')}
                            aria-label=${this.t('rag_resource_editor.create_toggle')}
                            @click=${this._enterCreate}
                        >
                            <platform-icon name="plus" size="14"></platform-icon>
                        </platform-button>
                    </span>
                </platform-field>
                <platform-field
                    pill-density="compact"
                    mode="edit"
                    type="text"
                    .label=${this.t('rag_resource_editor.field_namespace_description')}
                    .hint=${this.t('rag_resource_editor.hint_namespace_description')}
                    .placeholder=${this.t('rag_resource_editor.namespace_description_placeholder')}
                    .value=${nsDescription}
                    @change=${this._onNamespaceDescription}
                ></platform-field>
            </div>
        `;
    }

    override render(): TemplateResult {
        const cfg = this._cfg();
        const namespace = configText(cfg, 'namespace');
        const topKNumber = configNumber(cfg, 'default_top_k');
        const topK = topKNumber === null ? DEFAULT_TOP_K : topKNumber;
        const ttlNumber = configNumber(cfg, 'default_ttl_seconds');
        const ttl = ttlNumber === null ? '' : String(ttlNumber);
        const nsDescription = configText(cfg, 'namespace_description');
        const retrievalValue = panelValueFromSearchOptions(
            isPlainObject(cfg.search_options) ? cfg.search_options : null,
        );
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'rag'}
                .compactHeader=${this.compactHeader}
                @change=${(e: CustomEvent) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <p class="hint">${this.t('rag_resource_editor.what_is_hint')}</p>

                    <div class="section">
                        <div class="section-title">${this.t('rag_resource_editor.section_namespace')}</div>
                        ${this._renderNamespaceCard(namespace, nsDescription)}
                    </div>

                    <div class="section">
                        <div class="section-title">${this.t('rag_resource_editor.section_search')}</div>
                        <div class="grid-2">
                            <platform-field
                                pill-density="compact"
                                mode="edit"
                                type="integer"
                                .label=${this.t('rag_resource_editor.field_default_top_k')}
                                .hint=${this.t('rag_resource_editor.hint_default_top_k')}
                                .placeholder=${String(DEFAULT_TOP_K)}
                                .value=${topK}
                                @change=${this._onTopK}
                            ></platform-field>
                            <platform-field
                                pill-density="compact"
                                mode="edit"
                                type="string"
                                .label=${this.t('rag_resource_editor.field_collection_id')}
                                .hint=${this.t('rag_resource_editor.hint_collection_id')}
                                .placeholder=${this.t('rag_resource_editor.collection_id_placeholder')}
                                .value=${this._collectionId()}
                                @change=${this._onCollectionId}
                            ></platform-field>
                        </div>
                        <platform-rag-retrieval-panel
                            compact
                            .value=${retrievalValue}
                            .platformDefaults=${this._platformDefaults()}
                            @change=${this._onRetrievalPanelChange}
                        ></platform-rag-retrieval-panel>
                    </div>

                    <div class="section">
                        <div class="section-title">${this.t('rag_resource_editor.section_index')}</div>
                        <p class="hint">${this.t('rag_resource_editor.index_hint')}</p>
                        <div class="grid-2">
                            <platform-field
                                pill-density="compact"
                                mode="edit"
                                type="integer"
                                .label=${this.t('rag_resource_editor.field_chunk_size')}
                                .hint=${this.t('rag_resource_editor.hint_chunk_size')}
                                .placeholder=${String(DEFAULT_CHUNK_SIZE)}
                                .value=${this._chunkField('chunk_size')}
                                @change=${this._onChunkSize}
                            ></platform-field>
                            <platform-field
                                pill-density="compact"
                                mode="edit"
                                type="integer"
                                .label=${this.t('rag_resource_editor.field_chunk_overlap')}
                                .hint=${this.t('rag_resource_editor.hint_chunk_overlap')}
                                .placeholder=${String(DEFAULT_CHUNK_OVERLAP)}
                                .value=${this._chunkField('chunk_overlap')}
                                @change=${this._onChunkOverlap}
                            ></platform-field>
                            <platform-field
                                pill-density="compact"
                                mode="edit"
                                type="integer"
                                .label=${this.t('rag_resource_editor.field_default_ttl')}
                                .hint=${this.t('rag_resource_editor.hint_default_ttl')}
                                .placeholder=${this.t('rag_resource_editor.ttl_placeholder')}
                                .value=${ttl}
                                @change=${this._onTtl}
                            ></platform-field>
                        </div>
                    </div>

                    ${this._renderDocumentsSection(configText(cfg, 'namespace').trim())}
                    ${this._renderTestSection()}
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-rag-resource-editor', FlowsRagResourceEditor);
