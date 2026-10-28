/**
 * flows-llm-config-editor — единая форма LLM-конфига.
 *
 * Используется в:
 *   - LLM ноде (`NodeLLMConfig`, `cfg.llm`)
 *   - LLM ресурсе (`LLMResourceConfig`, `resource.config`)
 *
 * Поля точно соответствуют [NodeLLMConfig / LLMResourceConfig]
 * (apps/flows/src/models/node_config.py, apps/flows/src/models/resource.py):
 *   provider, model, fallback_models, temperature, max_tokens, api_key, folder_id, base_url,
 *   top_p, top_k, frequency_penalty, presence_penalty, seed,
 *   reasoning_effort, extra_request_body, extra_request_headers.
 *   Для `llm_node` слой базы из resources: закрепление одного LLM из каталога в
 *   `flows-base-node-editor` выставляет `llm_resource_key`; при одном LLM в merge ветки
 *   и пустом ключе база выводится в рантайме (`infer_unique_llm_resource_key_from_merged_maps`).
 *   Поле `llm_resource_key` в этой форме не редактируется.
 *
 * Свойства (API):
 *   - config: object  // текущее значение
 *   - readOnly: boolean  // только просмотр (без запросов списков и change)
 *
 * События (emit):
 *   - 'change' { config }  // полный объект (мерж с предыдущим)
 */

import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-json-editor.js';
import './flows-http-headers-editor.js';
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { formatJsonPretty } from '@platform/lib/utils/json-format.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

const REASONING_LEVELS = Object.freeze(['', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh']);
const HUMANITEC_LLM_PROVIDER = 'humanitec_llm';
const HUMANITEC_LLM_AUTO_MODEL = 'auto';
const DEFAULT_LLM_CAPABILITY = 'llm_chat';

export class FlowsLlmConfigEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        config: { type: Object },
        capability: { type: String },
        readOnly: { type: Boolean },
        allowFallbacks: { type: Boolean, attribute: 'allow-fallbacks' },
        _showAdvanced: { state: true },
        _draggedFallbackIndex: { state: true },
    }
    declare config: Record<string, any> | null;
    declare capability: string;
    declare readOnly: boolean;
    declare allowFallbacks: boolean;
    declare _showAdvanced: boolean;
    declare _draggedFallbackIndex: any;
;

    static override styles: CSSResultGroup = [
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
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
            }
            .extra-label-wrap {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                font-size: var(--text-sm);
                color: var(--text-secondary);
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
                border-color: var(--accent, var(--focus-ring));
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
    private _models: OpController;
    private _providers: OpController;
    private _loadedModelsKey: any;
    private _loadedProvidersKey: any;
    private _compositeNormalizeConsumed: boolean;

    constructor() {
        super();
        this.config = null;
        this.capability = DEFAULT_LLM_CAPABILITY;
        this.readOnly = false;
        this.allowFallbacks = true;
        this._showAdvanced = false;
        this._draggedFallbackIndex = null;
        this._models = this.useOp('flows/models_list');
        this._providers = this.useOp('flows/providers_list');
        this._loadedModelsKey = null;
        this._loadedProvidersKey = null;
        this._compositeNormalizeConsumed = false;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (this.readOnly) {
            return;
        }
        this._loadProvidersForCapability();
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (changed.has('config')) {
            this._compositeNormalizeConsumed = false;
        }
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (this.readOnly) {
            return;
        }
        this._loadProvidersForCapability();
        const provider = this._readString('provider');
        const capability = this._safeCapability();
        const modelsKey = `${capability}:${provider.length > 0 ? provider : '__default__'}`;
        if (modelsKey !== this._loadedModelsKey) {
            this._loadedModelsKey = modelsKey;
            void this._models.run(provider.length > 0 ? { provider, capability } : { capability });
        }
        this._maybeNormalizeCompositeModel();
    }

    _safeCapability() {
        return typeof this.capability === 'string' && this.capability.length > 0
            ? this.capability
            : DEFAULT_LLM_CAPABILITY;
    }

    _loadProvidersForCapability() {
        const capability = this._safeCapability();
        if (capability === this._loadedProvidersKey) return;
        this._loadedProvidersKey = capability;
        void this._providers.run({ capability });
    }

    _maybeNormalizeCompositeModel() {
        if (this._compositeNormalizeConsumed) return;
        if (this._readString('provider').length > 0) return;
        const model = this._readString('model');
        const idx = model.indexOf(':');
        if (idx <= 0) return;
        const head = model.slice(0, idx);
        const tail = model.slice(idx + 1);
        if (!tail || !this._knownProviderSlugs().has(head)) return;
        this._compositeNormalizeConsumed = true;
        const base = this.config && typeof this.config === 'object' ? this.config : {};
        const next = { ...base, provider: head, model: tail };
        this.emit('change', { config: next });
    }

    _readString(field: any) {
        const cfg = this.config;
        if (!cfg || typeof cfg !== 'object') return '';
        const v = cfg[field];
        return typeof v === 'string' ? v : '';
    }

    _readNumberField(field: any) {
        const cfg = this.config;
        if (!cfg || typeof cfg !== 'object') return null;
        const v = cfg[field];
        return typeof v === 'number' && Number.isFinite(v) ? v : null;
    }

    _emitPatch(patch: any) {
        const base = this.config && typeof this.config === 'object' ? this.config : {};
        const next = { ...base, ...patch };
        this.emit('change', { config: next });
    }

    _onString(field: any, value: unknown) {
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

    _onNumberField(field: any, detailValue: any) {
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

    _onJson(field: any, parsed: any) {
        const base = this.config && typeof this.config === 'object' ? this.config : {};
        const next = { ...base };
        if (parsed === null || parsed === undefined) {
            delete next[field];
        } else {
            next[field] = parsed;
        }
        this.emit('change', { config: next });
    }

    _onExtraHeaders(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object' || !('value' in d)) {
            throw new Error('flows-llm-config-editor: extra_request_headers detail.value');
        }
        const headers = d.value;
        if (!headers || typeof headers !== 'object' || Array.isArray(headers)) {
            throw new Error('flows-llm-config-editor: extra_request_headers must be an object');
        }
        if (Object.keys(headers).length === 0) {
            this._onJson('extra_request_headers', null);
            return;
        }
        this._onJson('extra_request_headers', headers);
    }

    _fallbackModels() {
        const raw = this.config && typeof this.config === 'object' ? this.config.fallback_models : null;
        if (!Array.isArray(raw)) return [];
        return raw.filter((item) => item && typeof item === 'object' && !Array.isArray(item));
    }

    _emitFallbackModels(items: Record<string, any>[]) {
        this._onJson('fallback_models', items.length > 0 ? items : null);
    }

    _addFallbackModel() {
        const items = this._fallbackModels();
        this._emitFallbackModels([...items, {}]);
    }

    _updateFallbackModel(idx: number, nextConfig: any) {
        const items = this._fallbackModels();
        if (idx < 0 || idx >= items.length) return;
        const value = nextConfig && typeof nextConfig === 'object' && !Array.isArray(nextConfig)
            ? nextConfig
            : {};
        this._emitFallbackModels(items.map((item, i) => (i === idx ? value : item)));
    }

    _removeFallbackModel(idx: number) {
        const items = this._fallbackModels();
        this._emitFallbackModels(items.filter((_, i) => i !== idx));
    }

    _isHumanitecLlmProvider(provider: string) {
        return provider === HUMANITEC_LLM_PROVIDER;
    }

    _onProviderChange(value: unknown) {
        const base = this.config && typeof this.config === 'object' && !Array.isArray(this.config)
            ? this.config
            : {};
        if (this._isHumanitecLlmProvider(value as string)) {
            const next = {
                ...base,
                provider: HUMANITEC_LLM_PROVIDER,
                model: HUMANITEC_LLM_AUTO_MODEL,
            };
            for (const field of [
                'api_key',
                'base_url',
                'folder_id',
                'extra_request_body',
                'extra_request_headers',
            ]) {
                delete (next as any)[field];
            }
            this.emit('change', { config: next });
            return;
        }
        const next: Record<string, unknown> = { ...base, provider: value };
        if ((value as any).length === 0) {
            delete next.provider;
        }
        if (base.provider === HUMANITEC_LLM_PROVIDER && next.model === HUMANITEC_LLM_AUTO_MODEL) {
            delete next.model;
        }
        this.emit('change', { config: next });
    }

    _moveFallbackModel(from: any, to: any) {
        const items = this._fallbackModels();
        if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return;
        const next = [...items];
        const [item] = next.splice(from, 1);
        next.splice(to, 0, item);
        this._emitFallbackModels(next);
    }

    _onFallbackDragStart(idx: number, e: Event) {
        if (this.readOnly) return;
        if (!(e instanceof DragEvent) || e.dataTransfer === null) {
            throw new Error('flows-llm-config-editor: drag data required');
        }
        this._draggedFallbackIndex = idx;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(idx));
    }

    _onFallbackDragOver(e: Event) {
        if (this.readOnly) return;
        e.preventDefault();
        if (!(e instanceof DragEvent) || !(e.currentTarget instanceof HTMLElement) || e.dataTransfer === null) {
            throw new Error('flows-llm-config-editor: drag target required');
        }
        e.currentTarget.classList.add('drag-over');
        e.dataTransfer.dropEffect = 'move';
    }

    _onFallbackDragLeave(e: Event) {
        if (!(e.currentTarget instanceof HTMLElement)) {
            throw new Error('flows-llm-config-editor: drag target required');
        }
        e.currentTarget.classList.remove('drag-over');
    }

    _onFallbackDrop(idx: number, e: Event) {
        if (this.readOnly) return;
        e.preventDefault();
        if (!(e instanceof DragEvent) || !(e.currentTarget instanceof HTMLElement) || e.dataTransfer === null) {
            throw new Error('flows-llm-config-editor: drag target required');
        }
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

    _fallbackTitle(item: any, idx: number) {
        const model = item && typeof item.model === 'string' ? item.model.trim() : '';
        return model || this.t('llm_config_editor.fallback_untitled', { index: idx + 1 });
    }

    _fallbackProviderLabel(item: any) {
        const provider = item && typeof item.provider === 'string' ? item.provider.trim() : '';
        return provider || this.t('llm_config_editor.fallback_inherit_provider');
    }

    _modelsList() {
        const result = this._models.lastResult;
        if (result == null) return [];
        if (!isPlainObject(result) || !Array.isArray(result.items)) {
            throw new Error('flows/models_list: result.items must be an array');
        }
        return result.items;
    }

    _providersList() {
        const result = this._providers.lastResult;
        if (result == null) return [];
        if (!isPlainObject(result) || !Array.isArray(result.items)) {
            throw new Error('flows/providers_list: result.items must be an array');
        }
        return result.items;
    }

    _knownProviderSlugs() {
        const out = new Set();
        for (const p of this._providersList()) {
            if (p && typeof p === 'object') {
                if (typeof p.value === 'string' && p.value.length > 0) out.add(p.value);
                continue;
            }
            if (typeof p === 'string' && p.length > 0) out.add(p);
        }
        return out;
    }

    _providerHint(provider: string) {
        if (provider === HUMANITEC_LLM_PROVIDER) {
            return this.t('llm_config_editor.humanitec_llms_provider_tooltip');
        }
        return this.t('llm_config_editor.provider_hint');
    }

    _modelHint(provider: string, model: string) {
        if (provider === HUMANITEC_LLM_PROVIDER && (!model || model === HUMANITEC_LLM_AUTO_MODEL)) {
            return this.t('llm_config_editor.humanitec_llms_auto_tooltip');
        }
        return this.t('llm_config_editor.model_hint');
    }

    _hint(key: string) {
        return this.t(`llm_config_editor.${key}_hint`);
    }

    override render(): TemplateResult {
        const fieldMode = this.readOnly ? 'view' : 'edit';
        const cfg = this.config && typeof this.config === 'object' ? this.config : {};
        const provider = this._readString('provider');
        const rawModel = this._readString('model');
        const fallbackModels = this._fallbackModels();
        const apiKey = this._readString('api_key');
        const folderId = this._readString('folder_id');
        const baseUrl = this._readString('base_url');
        const reasoning = this._readString('reasoning_effort');
        const humanitecLlm = this._isHumanitecLlmProvider(provider);
        const model = humanitecLlm && rawModel.length === 0 ? HUMANITEC_LLM_AUTO_MODEL : rawModel;
        const extraJson = cfg.extra_request_body && typeof cfg.extra_request_body === 'object'
            ? formatJsonPretty(cfg.extra_request_body)
            : '{}';
        const models = this._modelsList();
        const providers = this._providersList();
        const providerEnumValues = [
            { value: '', label: '—' },
            ...providers.map((p: any) => {
                if (p && typeof p === 'object') {
                    const value = typeof p.value === 'string' ? p.value : '';
                    const label = typeof p.label === 'string' && p.label.length > 0 ? p.label : value;
                    return { value, label };
                }
                return { value: p, label: p };
            }).filter((p: any) => typeof p.value === 'string'),
        ];
        const providerViewValues = provider.length > 0
            ? [{ value: provider, label: provider }]
            : [{ value: '', label: '—' }];
        const modelEnumValues = [
            { value: '', label: '—' },
            ...models.map((m: any) => {
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
                .hint=${this._modelHint(provider, model)}
                .value=${model}
            ></platform-field>`
            : (models.length > 0
                ? html`<platform-field
                    type="enum"
                    mode="edit"
                    .label=${this.t('llm_config_editor.model')}
                    .hint=${this._modelHint(provider, model)}
                    .value=${model}
                    .config=${{ values: modelEnumValues }}
                    @change=${(e: CustomEvent) => this._onString('model', typeof e.detail.value === 'string' ? e.detail.value : '')}
                ></platform-field>`
                : html`<platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('llm_config_editor.model')}
                    .hint=${this._modelHint(provider, model)}
                    .placeholder=${this.t('llm_config_editor.placeholder_model')}
                    .value=${model}
                    @change=${(e: CustomEvent) => this._onString('model', typeof e.detail.value === 'string' ? e.detail.value : '')}
                ></platform-field>`);
        return html`
            <div class="llm-config">
                <div class="grid">
                    <div class="field">
                        <platform-field
                            type="enum"
                            mode=${fieldMode}
                            .label=${this.t('llm_config_editor.provider')}
                            .hint=${this._providerHint(provider)}
                            .value=${provider}
                            .config=${this.readOnly
                                ? { values: providerViewValues }
                                : { values: providerEnumValues }}
                            @change=${this.readOnly
                                ? nothing
                                : (e: CustomEvent) => this._onProviderChange(typeof e.detail.value === 'string' ? e.detail.value : '')}
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
                            .hint=${this._hint('temperature')}
                            .placeholder=${this.t('llm_config_editor.placeholder_temperature')}
                            .value=${this._readNumberField('temperature')}
                            @change=${this.readOnly
                                ? nothing
                                : (e: CustomEvent) => this._onNumberField('temperature', e.detail.value)}
                        ></platform-field>
                    </div>
                    <div class="field">
                        <platform-field
                            type="integer"
                            mode=${fieldMode}
                            .label=${this.t('llm_config_editor.max_tokens')}
                            .hint=${this._hint('max_tokens')}
                            .placeholder=${this.t('llm_config_editor.placeholder_max_tokens')}
                            .value=${this._readNumberField('max_tokens')}
                            @change=${this.readOnly
                                ? nothing
                                : (e: CustomEvent) => this._onNumberField('max_tokens', e.detail.value)}
                        ></platform-field>
                    </div>
                </div>

                <div class="advanced-wrap">
                    <details
                        class="advanced"
                        ?open=${this._showAdvanced}
                        @toggle=${(e: Event) => {
                            const target = e.target;
                            if (!(target instanceof HTMLDetailsElement)) {
                                throw new Error('flows-llm-config-editor: details required');
                            }
                            this._showAdvanced = target.open;
                        }}
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
                                                      <platform-help-hint
                                                          .text=${this.t('llm_config_editor.fallback_models_hint')}
                                                      ></platform-help-hint>
                                                  </div>
                                                  ${this.readOnly
                                                      ? ''
                                                      : html`
                                                            <platform-button
                                                                variant="ghost"
                                                                density="compact"
                                                                @click=${() => this._addFallbackModel()}
                                                            >
                                                                <platform-icon name="plus"></platform-icon>
                                                                ${this.t('llm_config_editor.fallback_add')}
                                                            </platform-button>
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
                                                                        @dragover=${(e: Event) => this._onFallbackDragOver(e)}
                                                                        @dragleave=${(e: Event) => this._onFallbackDragLeave(e)}
                                                                        @drop=${(e: Event) => this._onFallbackDrop(idx, e)}
                                                                    >
                                                                        <summary class="fallback-summary">
                                                                            <span
                                                                                class="fallback-drag-handle"
                                                                                title=${this.t('llm_config_editor.fallback_drag')}
                                                                                .draggable=${!this.readOnly}
                                                                                @click=${(e: Event) => e.stopPropagation()}
                                                                                @dragstart=${(e: Event) => this._onFallbackDragStart(idx, e)}
                                                                                @dragend=${() => this._onFallbackDragEnd()}
                                                                            >
                                                                                <platform-icon name="drag-handle"></platform-icon>
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
                                                                                          <platform-button
                                                                                              variant="ghost"
                                                                                              icon-only
                                                                                              density="dense"
                                                                                              title=${this.t('llm_config_editor.fallback_move_up')}
                                                                                              ?disabled=${idx === 0}
                                                                                              @click=${(e: Event) => {
                                                                                                  e.preventDefault();
                                                                                                  e.stopPropagation();
                                                                                                  this._moveFallbackModel(idx, idx - 1);
                                                                                              }}
                                                                                          >
                                                                                              <platform-icon name="arrow-up" .size=${15}></platform-icon>
                                                                                          </platform-button>
                                                                                          <platform-button
                                                                                              variant="ghost"
                                                                                              icon-only
                                                                                              density="dense"
                                                                                              title=${this.t('llm_config_editor.fallback_move_down')}
                                                                                              ?disabled=${idx === fallbackModels.length - 1}
                                                                                              @click=${(e: Event) => {
                                                                                                  e.preventDefault();
                                                                                                  e.stopPropagation();
                                                                                                  this._moveFallbackModel(idx, idx + 1);
                                                                                              }}
                                                                                          >
                                                                                              <platform-icon name="arrow-down" .size=${15}></platform-icon>
                                                                                          </platform-button>
                                                                                          <platform-button
                                                                                              variant="ghost"
                                                                                              icon-only
                                                                                              density="dense"
                                                                                              danger
                                                                                              title=${this.t('llm_config_editor.fallback_remove')}
                                                                                              @click=${(e: CustomEvent) => {
                                                                                                  e.preventDefault();
                                                                                                  e.stopPropagation();
                                                                                                  this._removeFallbackModel(idx);
                                                                                              }}
                                                                                          >
                                                                                              <platform-icon name="trash" .size=${15}></platform-icon>
                                                                                          </platform-button>
                                                                                      </span>
                                                                                  `}
                                                                        </summary>
                                                                        <div class="fallback-body">
                                                                            <flows-llm-config-editor
                                                                                .config=${item}
                                                                                .capability=${this._safeCapability()}
                                                                                .readOnly=${this.readOnly}
                                                                                .allowFallbacks=${false}
                                                                                @change=${(e: CustomEvent) => {
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
                            ${humanitecLlm
                                ? ''
                                : html`
                                      <div class="field full">
                                          <platform-field
                                              type="string"
                                              mode=${fieldMode}
                                              input-type="password"
                                              .label=${this.t('llm_config_editor.api_key')}
                                              .hint=${this._hint('api_key')}
                                              .placeholder="@var:KEY"
                                              .value=${apiKey}
                                              @change=${this.readOnly
                                                  ? nothing
                                                  : (e: CustomEvent) => this._onString('api_key', typeof e.detail.value === 'string' ? e.detail.value : '')}
                                          ></platform-field>
                                      </div>
                                  `}
                            ${provider === 'yandex' && !humanitecLlm
                                ? html`
                                      <div class="field full">
                                          <platform-field
                                              type="string"
                                              mode=${fieldMode}
                                              .label=${this.t('llm_config_editor.folder_id')}
                                              .hint=${this._hint('folder_id')}
                                              .placeholder=${this.t('llm_config_editor.placeholder_folder_id')}
                                              .value=${folderId}
                                              @change=${this.readOnly
                                                  ? nothing
                                                  : (e: CustomEvent) =>
                                                      this._onString(
                                                          'folder_id',
                                                          typeof e.detail.value === 'string' ? e.detail.value : '',
                                                      )}
                                          ></platform-field>
                                      </div>
                                  `
                                : ''}
                            ${humanitecLlm
                                ? ''
                                : html`
                                      <div class="field full">
                                          <platform-field
                                              type="string"
                                              mode=${fieldMode}
                                              .label=${this.t('llm_config_editor.base_url')}
                                              .hint=${this._hint('base_url')}
                                              .placeholder="https://api.example.com/v1"
                                              .value=${baseUrl}
                                              @change=${this.readOnly
                                                  ? nothing
                                                  : (e: CustomEvent) => this._onString('base_url', typeof e.detail.value === 'string' ? e.detail.value : '')}
                                          ></platform-field>
                                      </div>
                                  `}
                            <div class="field">
                                <platform-field
                                    type="number"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.top_p')}
                                    .hint=${this._hint('top_p')}
                                    .placeholder=${this.t('llm_config_editor.placeholder_top_p')}
                                    .value=${this._readNumberField('top_p')}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e: CustomEvent) => this._onNumberField('top_p', e.detail.value)}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="integer"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.top_k')}
                                    .hint=${this._hint('top_k')}
                                    .placeholder=${this.t('llm_config_editor.placeholder_top_k')}
                                    .value=${this._readNumberField('top_k')}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e: CustomEvent) => this._onNumberField('top_k', e.detail.value)}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="number"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.frequency_penalty')}
                                    .hint=${this._hint('frequency_penalty')}
                                    .placeholder=${this.t('llm_config_editor.placeholder_frequency_penalty')}
                                    .value=${this._readNumberField('frequency_penalty')}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e: CustomEvent) => this._onNumberField('frequency_penalty', e.detail.value)}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="number"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.presence_penalty')}
                                    .hint=${this._hint('presence_penalty')}
                                    .placeholder=${this.t('llm_config_editor.placeholder_presence_penalty')}
                                    .value=${this._readNumberField('presence_penalty')}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e: CustomEvent) => this._onNumberField('presence_penalty', e.detail.value)}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="integer"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.seed')}
                                    .hint=${this._hint('seed')}
                                    .placeholder=${this.t('llm_config_editor.placeholder_seed')}
                                    .value=${this._readNumberField('seed')}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e: CustomEvent) => this._onNumberField('seed', e.detail.value)}
                                ></platform-field>
                            </div>
                            <div class="field">
                                <platform-field
                                    type="enum"
                                    mode=${fieldMode}
                                    .label=${this.t('llm_config_editor.reasoning_effort')}
                                    .hint=${this._hint('reasoning_effort')}
                                    .value=${reasoning}
                                    .config=${{ values: reasoningEnumValues }}
                                    @change=${this.readOnly
                                        ? nothing
                                        : (e: CustomEvent) => this._onString('reasoning_effort', typeof e.detail.value === 'string' ? e.detail.value : '')}
                                ></platform-field>
                            </div>
                            ${this.readOnly || humanitecLlm
                                ? ''
                                : html`
                                      <div class="field full extra">
                                          <p class="extra">${this.t('llm_config_editor.merge_layers_hint')}</p>
                                      </div>
                                  `}
                            ${humanitecLlm
                                ? ''
                                : html`
                                      <div class="field full extra">
                                          <span class="extra-label-wrap">
                                              <span>${this.t('llm_config_editor.extra_request_body')}</span>
                                              <platform-help-hint
                                                  .text=${this.t('llm_config_editor.extra_request_body_hint')}
                                              ></platform-help-hint>
                                          </span>
                                          <platform-json-editor validate-json show-toolbar="false"
                                              .value=${extraJson}
                                              .readonly=${this.readOnly}
                                              @change=${this.readOnly
                                                  ? nothing
                                                  : (e: CustomEvent) => {
                                                      if (e.detail && 'parsed' in e.detail) {
                                                          this._onJson('extra_request_body', e.detail.parsed);
                                                      }
                                                  }}
                                          ></platform-json-editor>
                                      </div>
                                      <div class="field full extra">
                                          <span class="extra-label-wrap">
                                              <span>${this.t('llm_config_editor.extra_request_headers')}</span>
                                              <platform-help-hint
                                                  .text=${this.t('llm_config_editor.extra_request_headers_hint')}
                                              ></platform-help-hint>
                                          </span>
                                          <flows-http-headers-editor
                                              .value=${cfg.extra_request_headers && typeof cfg.extra_request_headers === 'object' && !Array.isArray(cfg.extra_request_headers)
                                                  ? cfg.extra_request_headers
                                                  : {}}
                                              ?read-only=${this.readOnly}
                                              @change=${this.readOnly ? nothing : this._onExtraHeaders}
                                          ></flows-http-headers-editor>
                                      </div>
                                  `}
                        </div>
                    </details>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-llm-config-editor', FlowsLlmConfigEditor);
