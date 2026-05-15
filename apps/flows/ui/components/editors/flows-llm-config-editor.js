/**
 * flows-llm-config-editor — единая форма LLM-конфига.
 *
 * Используется в:
 *   - LLM ноде (`NodeLLMOverride`, `cfg.llm_override`)
 *   - LLM ресурсе (`LLMResourceConfig`, `resource.config`)
 *
 * Поля точно соответствуют [NodeLLMOverride / LLMResourceConfig]
 * (apps/flows/src/models/node_config.py, apps/flows/src/models/resource.py):
 *   provider, model, fallback_models, temperature, max_tokens, api_key, folder_id, base_url,
 *   top_p, top_k, frequency_penalty, presence_penalty, seed,
 *   reasoning_effort, extra_request_body, extra_request_headers.
 *   Для `llm_node` слой базы из resources: закрепление одного LLM из каталога в
 *   `flows-base-node-editor` выставляет `llm_resource_key`; при одном LLM в merge ветки
 *   и пустом ключе база выводится в рантайме (`infer_unique_llm_resource_key_from_merged_maps`).
 *   Поле `llm_resource_key` в этой форме не редактируется.
 *
 * Property API:
 *   - config: object  // текущее значение
 *   - readOnly: boolean  // только просмотр (без запросов списков и change)
 *
 * Events (emit):
 *   - 'change' { config }  // полный объект (мерж с предыдущим)
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import './flows-json-field-editor.js';
import { asString } from '../../_helpers/flows-resolvers.js';

const REASONING_LEVELS = Object.freeze(['', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh']);

/** Синхронно с `core/clients/llm/model_routing.LLM_ROUTING_PROVIDER_SLUGS` */
const LLM_ROUTING_PROVIDER_SLUGS = new Set(['openrouter', 'openai', 'bothub', 'provider_litserve', 'yandex']);

export class FlowsLlmConfigEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        config: { type: Object },
        readOnly: { type: Boolean },
        allowFallbacks: { type: Boolean, attribute: 'allow-fallbacks' },
        _showAdvanced: { state: true },
        _draggedFallbackIndex: { state: true },
        /** @type {{ name: string, value: string }[]} */
        _headerRows: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                container-type: inline-size;
                min-width: 0;
                width: 100%;
                box-sizing: border-box;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-3, 12px);
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
            @container (max-width: 480px) {
                .grid {
                    grid-template-columns: minmax(0, 1fr);
                }
            }
            .field {
                display: flex;
                flex-direction: column;
                gap: 4px;
                min-width: 0;
                max-width: 100%;
            }
            .full { grid-column: 1 / -1; }
            .llm-config {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
            .advanced-wrap {
                margin: 0;
                padding-top: var(--space-3);
                border-top: 1px solid var(--glass-border-subtle);
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
            details.advanced {
                margin: 0;
                padding: 0;
                border: none;
                border-radius: 0;
                background: transparent;
                width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
            summary.advanced-summary {
                cursor: pointer;
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                letter-spacing: 0.02em;
                text-transform: uppercase;
                color: var(--text-secondary);
                user-select: none;
                padding: 2px 0;
                list-style: none;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            summary.advanced-summary::-webkit-details-marker {
                display: none;
            }
            summary.advanced-summary::before {
                content: '';
                display: inline-block;
                width: 0;
                height: 0;
                margin-top: 1px;
                border-style: solid;
                border-width: 4px 0 4px 6px;
                border-color: transparent transparent transparent var(--text-tertiary);
                transition: transform var(--duration-fast, 120ms) ease;
            }
            details.advanced[open] summary.advanced-summary::before {
                transform: rotate(90deg);
            }
            details.advanced[open] summary.advanced-summary {
                color: var(--text-primary);
                margin-bottom: var(--space-3);
            }
            .extra {
                margin-top: var(--space-1);
            }
            .header-pair-row {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) auto;
                gap: var(--space-2);
                align-items: end;
                padding: var(--space-1) 0;
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .header-pair-row button.del {
                background: none;
                border: none;
                padding: var(--space-1);
                cursor: pointer;
                color: var(--text-tertiary);
                line-height: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                width: 32px;
                height: 32px;
                box-sizing: border-box;
            }
            .header-pair-row button.del platform-icon {
                --icon-size: 16px;
            }
            .header-pair-row button.del:hover {
                color: var(--error);
            }
            .header-pairs-add {
                margin-top: var(--space-2);
            }
            .fallbacks {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
            }
            .fallbacks-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                min-width: 0;
            }
            .fallbacks-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            .fallbacks-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-width: 0;
            }
            .fallback-item {
                border: 1px solid var(--glass-border-subtle);
                border-radius: 8px;
                background: var(--glass-bg-subtle);
                min-width: 0;
                overflow: clip;
            }
            .fallback-item.drag-over {
                border-color: var(--accent, var(--focus-ring, #2563eb));
            }
            .fallback-summary {
                display: grid;
                grid-template-columns: auto auto minmax(0, 1fr) auto;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2);
                cursor: pointer;
                list-style: none;
                min-width: 0;
            }
            .fallback-summary::-webkit-details-marker {
                display: none;
            }
            .fallback-summary::before {
                content: '';
                width: 0;
                height: 0;
                border-style: solid;
                border-width: 4px 0 4px 6px;
                border-color: transparent transparent transparent var(--text-tertiary);
                transition: transform var(--duration-fast, 120ms) ease;
            }
            .fallback-item[open] > .fallback-summary::before {
                transform: rotate(90deg);
            }
            .fallback-drag-handle {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                cursor: grab;
                width: 28px;
                height: 28px;
            }
            .fallback-drag-handle:active {
                cursor: grabbing;
            }
            .fallback-drag-handle platform-icon {
                --icon-size: 16px;
            }
            .fallback-label {
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }
            .fallback-label-main {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .fallback-label-sub {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .fallback-actions {
                display: inline-flex;
                align-items: center;
                gap: 2px;
            }
            .fallback-actions button {
                background: none;
                border: none;
                padding: var(--space-1);
                cursor: pointer;
                color: var(--text-tertiary);
                line-height: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                box-sizing: border-box;
            }
            .fallback-actions button:hover {
                color: var(--text-primary);
            }
            .fallback-actions button.danger:hover {
                color: var(--error);
            }
            .fallback-actions button:disabled {
                cursor: default;
                opacity: 0.35;
            }
            .fallback-body {
                padding: 0 var(--space-2) var(--space-2);
            }
            .fallback-empty {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                padding: var(--space-2) 0;
            }
        `,
    ];

    constructor() {
        super();
        this.config = null;
        this.readOnly = false;
        this.allowFallbacks = true;
        this._showAdvanced = false;
        this._draggedFallbackIndex = null;
        this._headerRows = [];
        this._models = this.useOp('flows/models_list');
        this._providers = this.useOp('flows/providers_list');
        this._loadedModelsKey = null;
        this._compositeNormalizeConsumed = false;
        this._providersLoaded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.readOnly) {
            return;
        }
        if (!this._providersLoaded) {
            this._providersLoaded = true;
            void this._providers.run(null);
        }
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('config')) {
            this._compositeNormalizeConsumed = false;
            const cfgNorm = this._normalizeHeaderObject(this.config?.extra_request_headers);
            const rowsNorm = this._headersObjectFromRows(this._headerRows);
            if (!this._headerDictEqual(cfgNorm, rowsNorm)) {
                this._headerRows = this._pairsFromConfig(this.config);
            }
        }
    }

    updated(changed) {
        super.updated?.(changed);
        if (this.readOnly) {
            return;
        }
        const provider = this._readString('provider');
        const modelsKey = provider.length > 0 ? provider : '__default__';
        if (modelsKey !== this._loadedModelsKey) {
            this._loadedModelsKey = modelsKey;
            void this._models.run(provider.length > 0 ? { provider } : {});
        }
        this._maybeNormalizeCompositeModel();
    }

    _maybeNormalizeCompositeModel() {
        if (this._compositeNormalizeConsumed) return;
        if (this._readString('provider').length > 0) return;
        const model = this._readString('model');
        const idx = model.indexOf(':');
        if (idx <= 0) return;
        const head = model.slice(0, idx);
        const tail = model.slice(idx + 1);
        if (!tail || !LLM_ROUTING_PROVIDER_SLUGS.has(head)) return;
        this._compositeNormalizeConsumed = true;
        const base = this.config && typeof this.config === 'object' ? this.config : {};
        const next = { ...base, provider: head, model: tail };
        this.emit('change', { config: next });
    }

    _readString(field) {
        const cfg = this.config;
        if (!cfg || typeof cfg !== 'object') return '';
        const v = cfg[field];
        return typeof v === 'string' ? v : '';
    }

    _readNumberField(field) {
        const cfg = this.config;
        if (!cfg || typeof cfg !== 'object') return null;
        const v = cfg[field];
        return typeof v === 'number' && Number.isFinite(v) ? v : null;
    }

    _emitPatch(patch) {
        const base = this.config && typeof this.config === 'object' ? this.config : {};
        const next = { ...base, ...patch };
        this.emit('change', { config: next });
    }

    _onString(field, value) {
        const v = typeof value === 'string' ? value : '';
        if (v.length === 0) {
            const base = this.config && typeof this.config === 'object' ? this.config : {};
            const next = { ...base };
            delete next[field];
            this.emit('change', { config: next });
            return;
        }
        this._emitPatch({ [field]: v });
    }

    _onNumberField(field, detailValue) {
        if (detailValue === null || detailValue === undefined) {
            const base = this.config && typeof this.config === 'object' ? this.config : {};
            const next = { ...base };
            delete next[field];
            this.emit('change', { config: next });
            return;
        }
        if (typeof detailValue !== 'number' || !Number.isFinite(detailValue)) return;
        this._emitPatch({ [field]: detailValue });
    }

    _onJson(field, parsed) {
        const base = this.config && typeof this.config === 'object' ? this.config : {};
        const next = { ...base };
        if (parsed === null || parsed === undefined) {
            delete next[field];
        } else {
            next[field] = parsed;
        }
        this.emit('change', { config: next });
    }

    _normalizeHeaderObject(h) {
        if (!h || typeof h !== 'object' || Array.isArray(h)) return {};
        const out = {};
        for (const k of Object.keys(h)) {
            const v = h[k];
            out[k] = typeof v === 'string' ? v : '';
        }
        return out;
    }

    _headerDictEqual(a, b) {
        const ka = Object.keys(a).sort();
        const kb = Object.keys(b).sort();
        if (ka.length !== kb.length) return false;
        for (let i = 0; i < ka.length; i += 1) {
            if (ka[i] !== kb[i]) return false;
            if (a[ka[i]] !== b[kb[i]]) return false;
        }
        return true;
    }

    _pairsFromConfig(cfg) {
        const h = cfg && typeof cfg === 'object' ? cfg.extra_request_headers : null;
        const pairs = [];
        if (h && typeof h === 'object' && !Array.isArray(h)) {
            for (const k of Object.keys(h)) {
                const v = h[k];
                pairs.push({ name: k, value: typeof v === 'string' ? v : '' });
            }
        }
        return pairs;
    }

    _headersObjectFromRows(rows) {
        const out = {};
        if (!Array.isArray(rows)) return out;
        for (const r of rows) {
            if (!r || typeof r !== 'object') continue;
            const n = typeof r.name === 'string' ? r.name.trim() : '';
            if (!n) continue;
            out[n] = typeof r.value === 'string' ? r.value : '';
        }
        return out;
    }

    _emitExtraHeadersFromRows() {
        const built = this._headersObjectFromRows(this._headerRows);
        if (Object.keys(built).length === 0) {
            this._onJson('extra_request_headers', null);
        } else {
            this._onJson('extra_request_headers', built);
        }
    }

    _onHeaderPairName(idx, e) {
        const v = typeof e.detail?.value === 'string' ? e.detail.value : '';
        this._headerRows = this._headerRows.map((r, i) => (i === idx ? { ...r, name: v } : r));
        this._emitExtraHeadersFromRows();
    }

    _onHeaderPairValue(idx, e) {
        const v = typeof e.detail?.value === 'string' ? e.detail.value : '';
        this._headerRows = this._headerRows.map((r, i) => (i === idx ? { ...r, value: v } : r));
        this._emitExtraHeadersFromRows();
    }

    _addHeaderPairRow() {
        this._headerRows = [...this._headerRows, { name: '', value: '' }];
    }

    _removeHeaderPairRow(idx) {
        this._headerRows = this._headerRows.filter((_, i) => i !== idx);
        this._emitExtraHeadersFromRows();
    }

    _fallbackModels() {
        const raw = this.config && typeof this.config === 'object' ? this.config.fallback_models : null;
        if (!Array.isArray(raw)) return [];
        return raw.filter((item) => item && typeof item === 'object' && !Array.isArray(item));
    }

    _emitFallbackModels(items) {
        this._onJson('fallback_models', items.length > 0 ? items : null);
    }

    _addFallbackModel() {
        const items = this._fallbackModels();
        this._emitFallbackModels([...items, {}]);
    }

    _updateFallbackModel(idx, nextConfig) {
        const items = this._fallbackModels();
        if (idx < 0 || idx >= items.length) return;
        const value = nextConfig && typeof nextConfig === 'object' && !Array.isArray(nextConfig)
            ? nextConfig
            : {};
        this._emitFallbackModels(items.map((item, i) => (i === idx ? value : item)));
    }

    _removeFallbackModel(idx) {
        const items = this._fallbackModels();
        this._emitFallbackModels(items.filter((_, i) => i !== idx));
    }

    _moveFallbackModel(from, to) {
        const items = this._fallbackModels();
        if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return;
        const next = [...items];
        const [item] = next.splice(from, 1);
        next.splice(to, 0, item);
        this._emitFallbackModels(next);
    }

    _onFallbackDragStart(idx, e) {
        if (this.readOnly) return;
        this._draggedFallbackIndex = idx;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(idx));
    }

    _onFallbackDragOver(e) {
        if (this.readOnly) return;
        e.preventDefault();
        e.currentTarget.classList.add('drag-over');
        e.dataTransfer.dropEffect = 'move';
    }

    _onFallbackDragLeave(e) {
        e.currentTarget.classList.remove('drag-over');
    }

    _onFallbackDrop(idx, e) {
        if (this.readOnly) return;
        e.preventDefault();
        e.currentTarget.classList.remove('drag-over');
        const raw = e.dataTransfer.getData('text/plain');
        const parsed = Number.parseInt(raw, 10);
        const from = Number.isInteger(parsed) ? parsed : this._draggedFallbackIndex;
        if (Number.isInteger(from)) {
            this._moveFallbackModel(from, idx);
        }
        this._draggedFallbackIndex = null;
    }

    _onFallbackDragEnd() {
        this._draggedFallbackIndex = null;
        for (const el of this.renderRoot.querySelectorAll('.fallback-item.drag-over')) {
            el.classList.remove('drag-over');
        }
    }

    _fallbackTitle(item, idx) {
        const model = item && typeof item.model === 'string' ? item.model.trim() : '';
        return model || this.t('llm_config_editor.fallback_untitled', { index: idx + 1 });
    }

    _fallbackProviderLabel(item) {
        const provider = item && typeof item.provider === 'string' ? item.provider.trim() : '';
        return provider || this.t('llm_config_editor.fallback_inherit_provider');
    }

    _modelsList() {
        const result = this._models.lastResult;
        if (Array.isArray(result?.items)) return result.items;
        if (Array.isArray(result)) return result;
        return [];
    }

    _providersList() {
        const result = this._providers.lastResult;
        if (Array.isArray(result?.items)) return result.items;
        if (Array.isArray(result)) return result;
        return [];
    }

    render() {
        const fieldMode = this.readOnly ? 'view' : 'edit';
        const cfg = this.config && typeof this.config === 'object' ? this.config : {};
        const provider = this._readString('provider');
        const model = this._readString('model');
        const fallbackModels = this._fallbackModels();
        const apiKey = this._readString('api_key');
        const folderId = this._readString('folder_id');
        const baseUrl = this._readString('base_url');
        const reasoning = this._readString('reasoning_effort');
        const extraJson = cfg.extra_request_body && typeof cfg.extra_request_body === 'object'
            ? JSON.stringify(cfg.extra_request_body, null, 2)
            : '{}';
        const models = this._modelsList();
        const providers = this._providersList();
        const providerEnumValues = [
            { value: '', label: '—' },
            ...providers.map((p) => ({ value: p, label: p })),
        ];
        const providerViewValues = provider.length > 0
            ? [{ value: provider, label: provider }]
            : [{ value: '', label: '—' }];
        const modelEnumValues = [
            { value: '', label: '—' },
            ...models.map((m) => {
                const optValue = typeof m === 'string' ? m : asString(typeof m.value === 'string' && m.value.length > 0 ? m.value : m.id);
                let optLabel;
                if (typeof m === 'string') optLabel = m;
                else if (typeof m.label === 'string' && m.label.length > 0) optLabel = m.label;
                else if (typeof m.value === 'string' && m.value.length > 0) optLabel = m.value;
                else optLabel = String(m.id);
                return { value: optValue, label: optLabel };
            }),
        ];
        const reasoningEnumValues = REASONING_LEVELS.map((lv) => (lv === ''
            ? { value: '', label: '—' }
            : { value: lv, label: lv }));
        const modelField = this.readOnly
            ? html`<platform-field
                type="string"
                mode="view"
                .label=${this.t('llm_config_editor.model')}
                .value=${model}
            ></platform-field>`
            : (models.length > 0
                ? html`<platform-field
                    type="enum"
                    mode="edit"
                    .label=${this.t('llm_config_editor.model')}
                    .value=${model}
                    .config=${{ values: modelEnumValues }}
                    @change=${(e) => this._onString('model', typeof e.detail.value === 'string' ? e.detail.value : '')}
                ></platform-field>`
                : html`<platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('llm_config_editor.model')}
                    .placeholder=${this.t('llm_config_editor.placeholder_model')}
                    .value=${model}
                    @change=${(e) => this._onString('model', typeof e.detail.value === 'string' ? e.detail.value : '')}
                ></platform-field>`);
        return html`
            <div class="llm-config">
                <div class="grid">
                    <div class="field">
                        <platform-field
                            type="enum"
                            mode=${fieldMode}
                            .label=${this.t('llm_config_editor.provider')}
                            .value=${provider}
                            .config=${this.readOnly
                                ? { values: providerViewValues }
                                : { values: providerEnumValues }}
                            @change=${this.readOnly
                                ? nothing
                                : (e) => this._onString('provider', typeof e.detail.value === 'string' ? e.detail.value : '')}
                        ></platform-field>
                    </div>
                    <div class="field">
                        ${modelField}
                    </div>
                    <div class="field">
                        <platform-field
                            type="number"
                            mode=${fieldMode}
                            .label=${this.t('llm_config_editor.temperature')}
                            .placeholder=${this.t('llm_config_editor.placeholder_temperature')}
                            .value=${this._readNumberField('temperature')}
                            @change=${this.readOnly
                                ? nothing
                                : (e) => this._onNumberField('temperature', e.detail.value)}
                        ></platform-field>
                    </div>
                    <div class="field">
                        <platform-field
                            type="integer"
                            mode=${fieldMode}
                            .label=${this.t('llm_config_editor.max_tokens')}
                            .placeholder=${this.t('llm_config_editor.placeholder_max_tokens')}
                            .value=${this._readNumberField('max_tokens')}
                            @change=${this.readOnly
                                ? nothing
                                : (e) => this._onNumberField('max_tokens', e.detail.value)}
                        ></platform-field>
                    </div>
                </div>

                <div class="advanced-wrap">
                    <details
                        class="advanced"
                        ?open=${this._showAdvanced}
                        @toggle=${(e) => { this._showAdvanced = e.target.open; }}
                    >
                        <summary class="advanced-summary">${this.t('llm_config_editor.advanced')}</summary>
                        <div class="grid">
                            ${this.allowFallbacks
                                ? html`
                                      <div class="field full">
                                          <div class="fallbacks">
                                              <div class="fallbacks-head">
                                                  <div class="fallbacks-title">
                                                      ${this.t('llm_config_editor.fallback_models')}
                                                  </div>
                                                  ${this.readOnly
                                                      ? ''
                                                      : html`
                                                            <glass-button
                                                                size="sm"
                                                                variant="ghost"
                                                                @click=${() => this._addFallbackModel()}
                                                            >
                                                                <platform-icon name="plus"></platform-icon>
                                                                ${this.t('llm_config_editor.fallback_add')}
                                                            </glass-button>
                                                        `}
                                              </div>
                                              ${fallbackModels.length === 0
                                                  ? html`
                                                        <div class="fallback-empty">
                                                            ${this.t('llm_config_editor.fallback_empty')}
                                                        </div>
                                                    `
                                                  : html`
                                                        <div class="fallbacks-list">
                                                            ${fallbackModels.map(
                                                                (item, idx) => html`
                                                                    <details
                                                                        class="fallback-item"
                                                                        @dragover=${(e) => this._onFallbackDragOver(e)}
                                                                        @dragleave=${(e) => this._onFallbackDragLeave(e)}
                                                                        @drop=${(e) => this._onFallbackDrop(idx, e)}
                                                                    >
                                                                        <summary class="fallback-summary">
                                                                            <span
                                                                                class="fallback-drag-handle"
                                                                                title=${this.t('llm_config_editor.fallback_drag')}
                                                                                .draggable=${!this.readOnly}
                                                                                @click=${(e) => e.stopPropagation()}
                                                                                @dragstart=${(e) => this._onFallbackDragStart(idx, e)}
                                                                                @dragend=${() => this._onFallbackDragEnd()}
                                                                            >
                                                                                <platform-icon name="grip-vertical"></platform-icon>
                                                                            </span>
                                                                            <span class="fallback-label">
                                                                                <span class="fallback-label-main">
                                                                                    ${this._fallbackTitle(item, idx)}
                                                                                </span>
                                                                                <span class="fallback-label-sub">
                                                                                    ${this._fallbackProviderLabel(item)}
                                                                                </span>
                                                                            </span>
                                                                            ${this.readOnly
                                                                                ? ''
                                                                                : html`
                                                                                      <span class="fallback-actions">
                                                                                          <button
                                                                                              type="button"
                                                                                              title=${this.t('llm_config_editor.fallback_move_up')}
                                                                                              ?disabled=${idx === 0}
                                                                                              @click=${(e) => {
                                                                                                  e.preventDefault();
                                                                                                  e.stopPropagation();
                                                                                                  this._moveFallbackModel(idx, idx - 1);
                                                                                              }}
                                                                                          >
                                                                                              <platform-icon name="arrow-up" .size=${15}></platform-icon>
                                                                                          </button>
                                                                                          <button
                                                                                              type="button"
                                                                                              title=${this.t('llm_config_editor.fallback_move_down')}
                                                                                              ?disabled=${idx === fallbackModels.length - 1}
                                                                                              @click=${(e) => {
                                                                                                  e.preventDefault();
                                                                                                  e.stopPropagation();
                                                                                                  this._moveFallbackModel(idx, idx + 1);
                                                                                              }}
                                                                                          >
                                                                                              <platform-icon name="arrow-down" .size=${15}></platform-icon>
                                                                                          </button>
                                                                                          <button
                                                                                              type="button"
                                                                                              class="danger"
                                                                                              title=${this.t('llm_config_editor.fallback_remove')}
                                                                                              @click=${(e) => {
                                                                                                  e.preventDefault();
                                                                                                  e.stopPropagation();
                                                                                                  this._removeFallbackModel(idx);
                                                                                              }}
                                                                                          >
                                                                                              <platform-icon name="trash" .size=${15}></platform-icon>
                                                                                          </button>
                                                                                      </span>
                                                                                  `}
                                                                        </summary>
                                                                        <div class="fallback-body">
                                                                            <flows-llm-config-editor
                                                                                .config=${item}
                                                                                .readOnly=${this.readOnly}
                                                                                .allowFallbacks=${false}
                                                                                @change=${(e) => {
                                                                                    e.stopPropagation();
                                                                                    this._updateFallbackModel(idx, e.detail.config);
                                                                                }}
                                                                            ></flows-llm-config-editor>
                                                                        </div>
                                                                    </details>
                                                                `,
                                                            )}
                                                        </div>
                                                    `}
                                          </div>
                                      </div>
                                  `
                                : ''}
                            <div class="field full">
                                <platform-field
                                    type="string"
                                    mode=${fieldMode}
                                    input-type="password"
                                    .label=${this.t('llm_config_editor.api_key')}
                                    .placeholder="@var:KEY"
                                    .value=${apiKey}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e) => this._onString('api_key', typeof e.detail.value === 'string' ? e.detail.value : '')}
                                ></platform-field>
                            </div>
                            ${provider === 'yandex'
                                ? html`
                                      <div class="field full">
                                          <platform-field
                                              type="string"
                                              mode=${fieldMode}
                                              .label=${this.t('llm_config_editor.folder_id')}
                                              .placeholder=${this.t('llm_config_editor.placeholder_folder_id')}
                                              .value=${folderId}
                                              @change=${this.readOnly
                                                  ? nothing
                                                  : (e) =>
                                                      this._onString(
                                                          'folder_id',
                                                          typeof e.detail.value === 'string' ? e.detail.value : '',
                                                      )}
                                          ></platform-field>
                                      </div>
                                  `
                                : ''}
                            <div class="field full">
                                <platform-field
                                    type="string"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.base_url')}
                                    .placeholder="https://api.example.com/v1"
                                    .value=${baseUrl}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e) => this._onString('base_url', typeof e.detail.value === 'string' ? e.detail.value : '')}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="number"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.top_p')}
                                    .placeholder=${this.t('llm_config_editor.placeholder_top_p')}
                                    .value=${this._readNumberField('top_p')}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e) => this._onNumberField('top_p', e.detail.value)}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="integer"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.top_k')}
                                    .placeholder=${this.t('llm_config_editor.placeholder_top_k')}
                                    .value=${this._readNumberField('top_k')}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e) => this._onNumberField('top_k', e.detail.value)}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="number"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.frequency_penalty')}
                                    .placeholder=${this.t('llm_config_editor.placeholder_frequency_penalty')}
                                    .value=${this._readNumberField('frequency_penalty')}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e) => this._onNumberField('frequency_penalty', e.detail.value)}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="number"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.presence_penalty')}
                                    .placeholder=${this.t('llm_config_editor.placeholder_presence_penalty')}
                                    .value=${this._readNumberField('presence_penalty')}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e) => this._onNumberField('presence_penalty', e.detail.value)}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="integer"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.seed')}
                                    .placeholder=${this.t('llm_config_editor.placeholder_seed')}
                                    .value=${this._readNumberField('seed')}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e) => this._onNumberField('seed', e.detail.value)}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="enum"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.reasoning_effort')}
                                    .value=${reasoning}
                                    .config=${{ values: reasoningEnumValues }}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e) => this._onString('reasoning_effort', typeof e.detail.value === 'string' ? e.detail.value : '')}
                                ></platform-field>
                            </div>
                            ${this.readOnly
                                ? ''
                                : html`
                                      <div class="field full extra">
                                          <p class="extra">${this.t('llm_config_editor.merge_layers_hint')}</p>
                                      </div>
                                  `}
                            <div class="field full extra">
                                <label>${this.t('llm_config_editor.extra_request_body')}</label>
                                <flows-json-field-editor
                                    .value=${extraJson}
                                    .readonly=${this.readOnly}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e) => {
                                            if (e.detail && 'parsed' in e.detail) {
                                                this._onJson('extra_request_body', e.detail.parsed);
                                            }
                                        }}
                                ></flows-json-field-editor>
                            </div>
                            <div class="field full extra">
                                <label>${this.t('llm_config_editor.extra_request_headers')}</label>
                                ${(Array.isArray(this._headerRows) ? this._headerRows : []).map(
                                    (row, idx) => html`
                                        <div class="header-pair-row">
                                            <platform-field
                                                mode=${fieldMode}
                                                type="string"
                                                .label=${this.t('llm_config_editor.extra_header_name')}
                                                .placeholder=${this.t('llm_config_editor.extra_header_name_placeholder')}
                                                .value=${typeof row.name === 'string' ? row.name : ''}
                                                @change=${this.readOnly
                                                    ? nothing
                                                    : (e) => this._onHeaderPairName(idx, e)}
                                            ></platform-field>
                                            <platform-field
                                                mode=${fieldMode}
                                                type="string"
                                                .label=${this.t('llm_config_editor.extra_header_value')}
                                                .placeholder=${this.t('llm_config_editor.extra_header_value_placeholder')}
                                                .value=${typeof row.value === 'string' ? row.value : ''}
                                                @change=${this.readOnly
                                                    ? nothing
                                                    : (e) => this._onHeaderPairValue(idx, e)}
                                            ></platform-field>
                                            ${this.readOnly
                                                ? ''
                                                : html`
                                                      <button
                                                          type="button"
                                                          class="del"
                                                          title=${this.t('llm_config_editor.extra_header_remove')}
                                                          @click=${() => this._removeHeaderPairRow(idx)}
                                                      >
                                                          <platform-icon name="trash" .size=${16}></platform-icon>
                                                      </button>
                                                  `}
                                        </div>
                                    `,
                                )}
                                ${this.readOnly
                                    ? ''
                                    : html`
                                          <glass-button
                                              class="header-pairs-add"
                                              size="sm"
                                              variant="ghost"
                                              @click=${() => this._addHeaderPairRow()}
                                          >
                                              <platform-icon name="plus"></platform-icon>
                                              ${this.t('llm_config_editor.extra_header_add')}
                                          </glass-button>
                                      `}
                            </div>
                        </div>
                    </details>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-llm-config-editor', FlowsLlmConfigEditor);
