/**
 * flows-rag-resource-editor — ресурс type=rag (bind к platform Namespace).
 *
 * DX: понятные labels/hints/placeholders; создание namespace — в том же
 * field-pill (suffix +), без отдельной громоздкой формы.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/rag/platform-rag-retrieval-panel.js';
import {
    buildAdvancedRetrievalPayloadFromPanel,
    panelValueFromSearchOptions,
} from '@platform/lib/rag/pack_search_request_options.js';
import './flows-base-resource-editor.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';

const NAMESPACE_NAME_PATTERN = /^[a-z][a-z0-9_-]{0,62}[a-z0-9]$|^[a-z]$/;
const DEFAULT_TOP_K = 5;
const DEFAULT_CHUNK_SIZE = 512;
const DEFAULT_CHUNK_OVERLAP = 50;

export class FlowsRagResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
        _showCreate: { state: true },
        _createName: { state: true },
        _createDescription: { state: true },
    };

    static styles = [
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
        `,
    ];

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
        this.compactHeader = false;
        this._showCreate = false;
        this._createName = '';
        this._createDescription = '';
        this._namespacesList = this.useOp('flows/rag_namespaces_list');
        this._namespacesCreate = this.useOp('flows/rag_namespaces_create');
        this._searchDefaults = this.useOp('flows/rag_search_defaults');
        this._defaultsLoaded = false;
        this._namespacesLoaded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        if (!this._defaultsLoaded) {
            this._defaultsLoaded = true;
            void this._searchDefaults.run({});
        }
        if (!this._namespacesLoaded) {
            this._namespacesLoaded = true;
            void this._namespacesList.run({});
        }
    }

    _cfg() {
        return isPlainObject(this.resource?.config) ? this.resource.config : {};
    }

    _emitConfig(patch) {
        const base = this._cfg();
        this.emit('change', {
            resourceId: this.resourceId,
            patch: { config: { ...base, ...patch } },
        });
    }

    _namespaceOptions() {
        const result = this._namespacesList.lastResult;
        const items = isPlainObject(result) && Array.isArray(result.items) ? result.items : [];
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
        const current = typeof this._cfg().namespace === 'string' ? this._cfg().namespace.trim() : '';
        if (current.length > 0 && !opts.some((o) => o.value === current)) {
            opts.unshift({ value: current, label: current });
        }
        return opts;
    }

    _onNamespaceChange(e) {
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

    _onTopK(e) {
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

    _onCollectionId(e) {
        const d = e.detail;
        if (!isPlainObject(d) || typeof d.value !== 'string') {
            throw new Error('flows-rag-resource-editor: collection_id change');
        }
        const collectionId = d.value.trim();
        const prevFilters = isPlainObject(this._cfg().filters) ? { ...this._cfg().filters } : {};
        if (collectionId.length === 0) {
            delete prevFilters.collection_id;
            this._emitConfig({
                filters: Object.keys(prevFilters).length > 0 ? prevFilters : null,
            });
            return;
        }
        this._emitConfig({ filters: { ...prevFilters, collection_id: collectionId } });
    }

    _onTtl(e) {
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

    _onNamespaceDescription(e) {
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

    _onChunkSize(e) {
        this._patchIndexSplit('chunk_size', e);
    }

    _onChunkOverlap(e) {
        this._patchIndexSplit('chunk_overlap', e);
    }

    _patchIndexSplit(field, e) {
        const d = e.detail;
        if (!isPlainObject(d)) {
            throw new Error(`flows-rag-resource-editor: ${field} change`);
        }
        const raw = d.value;
        if (raw === '' || raw === null || raw === undefined) {
            const ipc = isPlainObject(this._cfg().index_profile_config)
                ? { ...this._cfg().index_profile_config }
                : {};
            const split = isPlainObject(ipc.split) ? { ...ipc.split } : {};
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
        const ipc = isPlainObject(this._cfg().index_profile_config)
            ? { ...this._cfg().index_profile_config }
            : {};
        const split = isPlainObject(ipc.split) ? { ...ipc.split } : {};
        split[field] = Math.trunc(n);
        ipc.split = split;
        this._emitConfig({ index_profile_config: ipc });
    }

    _onRetrievalPanelChange(e) {
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
        const filters = this._cfg().filters;
        if (!isPlainObject(filters)) {
            return '';
        }
        return typeof filters.collection_id === 'string' ? filters.collection_id : '';
    }

    _chunkField(field) {
        const ipc = this._cfg().index_profile_config;
        if (!isPlainObject(ipc) || !isPlainObject(ipc.split)) {
            return '';
        }
        const raw = ipc.split[field];
        return typeof raw === 'number' && Number.isFinite(raw) ? String(raw) : '';
    }

    _enterCreate() {
        const current = typeof this._cfg().namespace === 'string' ? this._cfg().namespace : '';
        this._createName = current.startsWith('kb-') ? current : '';
        this._createDescription = typeof this._cfg().namespace_description === 'string'
            ? this._cfg().namespace_description
            : '';
        this._showCreate = true;
    }

    _cancelCreate() {
        this._showCreate = false;
        this._createName = '';
        this._createDescription = '';
    }

    async _createNamespace() {
        const name = this._createName.trim();
        if (!NAMESPACE_NAME_PATTERN.test(name)) {
            this.toast('rag_resource_editor.namespace_name_invalid', { type: 'error' });
            return;
        }
        const description = this._createDescription.trim();
        const descriptionValue = description.length === 0 ? null : description;
        const created = await this._namespacesCreate.run({
            name,
            description: descriptionValue,
        });
        if (created == null) {
            return;
        }
        this._emitConfig({
            namespace: name,
            namespace_description: descriptionValue,
        });
        this._showCreate = false;
        this._createName = '';
        this._createDescription = '';
        void this._namespacesList.run({});
    }

    _renderNamespaceCard(namespace, nsDescription) {
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
                        @change=${(e) => {
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
                                ?disabled=${this._namespacesCreate.busy}
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
                        @change=${(e) => {
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

    render() {
        const cfg = this._cfg();
        const namespace = typeof cfg.namespace === 'string' ? cfg.namespace : '';
        const topK = typeof cfg.default_top_k === 'number' ? cfg.default_top_k : DEFAULT_TOP_K;
        const ttl = typeof cfg.default_ttl_seconds === 'number' ? String(cfg.default_ttl_seconds) : '';
        const nsDescription = typeof cfg.namespace_description === 'string'
            ? cfg.namespace_description
            : '';
        const retrievalValue = panelValueFromSearchOptions(
            isPlainObject(cfg.search_options) ? cfg.search_options : null,
        );
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'rag'}
                .compactHeader=${this.compactHeader}
                @change=${(e) => this.emit('change', e.detail)}
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
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-rag-resource-editor', FlowsRagResourceEditor);
