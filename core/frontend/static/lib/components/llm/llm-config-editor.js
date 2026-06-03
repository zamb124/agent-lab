/**
 * <platform-llm-config-editor> — единый core-компонент конфигурации LLM-провайдера.
 *
 * Используется на странице Settings (карточка capability) и в перспективе будет
 * единственной формой LLM-конфига для редактора flows-llm-node / llm-resource.
 *
 * Режимы (mode):
 *   - 'company_capability' — карточка capability на /settings (selector провайдеров с
 *      платформенными + custom; BYOK поля при не-custom; платформенная модель только для чтения;
 *      бейдж cost_origin; кнопка очистки override; никаких advanced полей).
 *   - 'flow_node' / 'flow_resource' — TODO: миграция flows-llm-config-editor сюда.
 *
 * API свойств:
 *   .config           = { provider, api_key, base_url, folder_id, extra_request_headers, model, ... }
 *                       — текущее значение, эмитится через 'change' { config }.
 *   .mode             = 'company_capability' | 'flow_node' | 'flow_resource' (см. выше).
 *   .capability       = строка (для mode=company_capability).
 *   .providerCatalog  = [{ value, label, kind, custom_id?, models?, tooltip_key? }].
 *   .platformModel    = string | null   — платформенная модель только для чтения.
 *   .costOrigin       = 'platform' | 'company' | null.
 *   .keyMasked        = string | null   — текущий замаскированный ключ ('**** abcd').
 *   .clearable        = boolean         — показывать кнопку «Сбросить override».
 *   .readOnly         = boolean.
 *
 * Events:
 *   - 'change'          { config }
 *   - 'clear-override'  {} — родитель шлёт DELETE для capability.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';

const _CUSTOM_REF_PREFIX = 'custom:';
const _HUMANITEC_LLM_PROVIDER = 'humanitec_llm';

export class PlatformLlmConfigEditor extends PlatformElement {
    static i18nNamespace = 'frontend';

    static properties = {
        config: { type: Object },
        mode: { type: String },
        capability: { type: String },
        providerCatalog: { type: Array },
        platformModel: { type: String },
        costOrigin: { type: String },
        keyMasked: { type: String },
        clearable: { type: Boolean },
        readOnly: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; container-type: inline-size; min-width: 0; width: 100%; box-sizing: border-box; }
            .row { display: flex; flex-direction: column; gap: var(--space-3); width: 100%; min-width: 0; }
            .header {
                display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);
                margin-bottom: var(--space-2);
            }
            .badge {
                font-size: var(--text-xs);
                padding: 2px 8px; border-radius: var(--radius-pill);
                background: var(--glass-solid-subtle); color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle);
            }
            .badge[data-kind="company"] { color: var(--success-text, var(--text-primary)); border-color: var(--success-border, var(--glass-border-subtle)); }
            .actions { display: flex; gap: var(--space-2); align-items: center; }
            .help { color: var(--text-tertiary); font-size: var(--text-xs); }
            .fallback-policy {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                min-width: 0;
            }
            .fallback-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                min-width: 0;
            }
            .fallback-title {
                font-size: var(--text-xs);
                font-weight: 700;
                letter-spacing: 0;
                text-transform: uppercase;
                color: var(--text-secondary);
            }
            .fallback-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: 0;
            }
            .fallback-item {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                min-width: 0;
            }
            .fallback-grid {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
                gap: var(--space-2);
                flex: 1;
                min-width: 0;
            }
            .fallback-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
                padding-top: 2px;
            }
            .fallback-empty {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            @container (max-width: 560px) {
                .fallback-item { flex-direction: column; }
                .fallback-grid { grid-template-columns: 1fr; width: 100%; }
                .fallback-actions { padding-top: 0; }
            }
        `,
    ];

    constructor() {
        super();
        this.config = {};
        this.mode = 'company_capability';
        this.capability = '';
        this.providerCatalog = [];
        this.platformModel = '';
        this.costOrigin = null;
        this.keyMasked = null;
        this.clearable = false;
        this.readOnly = false;
    }

    _isCustomProvider(value) {
        return typeof value === 'string' && value.startsWith(_CUSTOM_REF_PREFIX);
    }

    _isHumanitecLlmProvider(value) {
        return value === _HUMANITEC_LLM_PROVIDER;
    }

    _isEmbeddingCapability() {
        return this.capability === 'embedding';
    }

    _supportsModelOverride() {
        return (
            typeof this.capability === 'string'
            && (
                (
                    (
                        this.capability.startsWith('llm_')
                        || this._isEmbeddingCapability()
                        || this.capability === 'image_gen'
                        || this.capability === 'rerank'
                        || this.capability === 'voice_stt'
                        || this.capability === 'voice_tts'
                    )
                )
            )
        );
    }

    _supportsFallbackPolicy() {
        const provider = (this.config && this.config.provider) || '';
        return (
            this.mode === 'company_capability'
            && ((this.capability || '').startsWith('llm_') || this.capability === 'image_gen')
            && provider.length > 0
        );
    }

    _emitChange(patch) {
        const next = { ...(this.config || {}), ...patch };
        this.config = next;
        this.dispatchEvent(new CustomEvent('change', { detail: { config: next }, bubbles: true, composed: true }));
    }

    _onProviderChange(e) {
        if (!e.detail || typeof e.detail.value !== 'string') {
            throw new Error('platform-llm-config-editor: provider change expects detail.value string');
        }
        const value = e.detail.value;
        const currentProvider = (this.config && this.config.provider) || '';
        const patch = { provider: value };
        if (this._isCustomProvider(value)) {
            patch.api_key = null;
            patch.base_url = null;
            patch.extra_request_headers = null;
        }
        if (this._isHumanitecLlmProvider(value)) {
            patch.api_key = null;
            patch.base_url = null;
            patch.folder_id = null;
            patch.extra_request_headers = null;
            patch.model = 'auto';
        }
        if (!this._isHumanitecLlmProvider(value) && value !== currentProvider) {
            patch.model = null;
            patch.dimension = null;
            patch.mrl_output_dimension = null;
        }
        this._emitChange(patch);
    }

    _onApiKeyChange(e) {
        if (!e.detail || typeof e.detail.value !== 'string') {
            throw new Error('platform-llm-config-editor: api_key change expects detail.value string');
        }
        this._emitChange({ api_key: e.detail.value || null });
    }

    _onBaseUrlChange(e) {
        if (!e.detail || typeof e.detail.value !== 'string') {
            throw new Error('platform-llm-config-editor: base_url change expects detail.value string');
        }
        this._emitChange({ base_url: e.detail.value || null });
    }

    _onModelChange(e) {
        if (!e.detail || typeof e.detail.value !== 'string') {
            throw new Error('platform-llm-config-editor: model change expects detail.value string');
        }
        const value = e.detail.value || null;
        const patch = { model: value };
        if (this._isEmbeddingCapability()) {
            const selected = this._selectedProviderModels()
                .find((item) => item && typeof item === 'object' && item.value === value);
            if (selected) {
                patch.dimension = Number.isFinite(selected.dimension) ? selected.dimension : null;
                patch.mrl_output_dimension = Number.isFinite(selected.mrl_output_dimension)
                    ? selected.mrl_output_dimension
                    : null;
            }
        }
        this._emitChange(patch);
    }

    _onDimensionChange(e) {
        if (!e.detail || (e.detail.value !== null && typeof e.detail.value !== 'number')) {
            throw new Error('platform-llm-config-editor: embedding dimension expects numeric detail.value');
        }
        this._emitChange({ dimension: e.detail.value || null });
    }

    _onMrlOutputDimensionChange(e) {
        if (!e.detail || (e.detail.value !== null && typeof e.detail.value !== 'number')) {
            throw new Error('platform-llm-config-editor: embedding mrl_output_dimension expects numeric detail.value');
        }
        this._emitChange({ mrl_output_dimension: e.detail.value || null });
    }

    _onClear() {
        this.dispatchEvent(new CustomEvent('clear-override', { detail: {}, bubbles: true, composed: true }));
    }

    _providerEnumConfig() {
        const items = (this.providerCatalog || []).map((p) => ({
            value: p.value,
            label: p.label || p.value,
        }));
        return { values: items };
    }

    _selectedProviderCatalogItem() {
        const provider = (this.config && this.config.provider) || '';
        return (this.providerCatalog || []).find((p) => p && p.value === provider) || null;
    }

    _selectedProviderModels() {
        return this._providerModelsFor((this.config && this.config.provider) || '');
    }

    _providerModelsFor(provider) {
        const selected = (this.providerCatalog || []).find((p) => p && p.value === provider) || null;
        return Array.isArray(selected?.models) ? selected.models : [];
    }

    _modelOptionsForProvider(provider) {
        return this._providerModelsFor(provider)
            .map((item) => {
                if (typeof item === 'string') {
                    return { value: item, label: item };
                }
                if (!item || typeof item !== 'object') {
                    return null;
                }
                const value = typeof item.value === 'string' && item.value.length > 0
                    ? item.value
                    : (typeof item.id === 'string' ? item.id : '');
                if (!value) {
                    return null;
                }
                const label = typeof item.label === 'string' && item.label.length > 0
                    ? item.label
                    : value;
                return { value, label };
            })
            .filter(Boolean);
    }

    _modelEnumConfig() {
        const values = this._modelOptionsForProvider((this.config && this.config.provider) || '');
        return { values };
    }

    _fallbackModels() {
        const raw = (this.config && Array.isArray(this.config.fallback_models))
            ? this.config.fallback_models
            : [];
        return raw
            .filter((item) => item && typeof item === 'object')
            .map((item) => ({
                provider: typeof item.provider === 'string' ? item.provider : '',
                model: typeof item.model === 'string' ? item.model : '',
            }))
            .filter((item) => item.provider || item.model);
    }

    _updateFallbackModels(items) {
        const next = (items || [])
            .filter((item) => item && typeof item === 'object')
            .map((item) => ({
                provider: typeof item.provider === 'string' ? item.provider.trim() : '',
                model: typeof item.model === 'string' ? item.model.trim() : '',
            }))
            .filter((item) => item.provider || item.model);
        this._emitChange({ fallback_models: next.length > 0 ? next : null });
    }

    _fallbackProviderCatalog() {
        const providers = (this.providerCatalog || []).filter((p) => {
            if (!p || typeof p.value !== 'string' || p.value.length === 0) {
                return false;
            }
            if (this.costOrigin === 'company') {
                return p.kind === 'custom';
            }
            return true;
        });
        return providers;
    }

    _fallbackProviderEnumConfig() {
        return {
            values: this._fallbackProviderCatalog().map((p) => ({
                value: p.value,
                label: p.label || p.value,
            })),
        };
    }

    _fallbackDefaultProvider() {
        const providers = this._fallbackProviderCatalog();
        if (providers.length === 0) {
            return '';
        }
        const currentProvider = (this.config && this.config.provider) || '';
        if (providers.some((p) => p.value === currentProvider)) {
            return currentProvider;
        }
        return providers[0].value;
    }

    _fallbackDefaultModel(provider) {
        if (this._isHumanitecLlmProvider(provider)) {
            return 'auto';
        }
        const first = this._modelOptionsForProvider(provider)[0];
        return first ? first.value : '';
    }

    _fallbackModelEnumConfig(provider) {
        return { values: this._modelOptionsForProvider(provider) };
    }

    _addFallbackModel() {
        const provider = this._fallbackDefaultProvider();
        if (!provider) {
            return;
        }
        const next = [
            ...this._fallbackModels(),
            {
                provider,
                model: this._fallbackDefaultModel(provider),
            },
        ];
        this._updateFallbackModels(next);
    }

    _removeFallbackModel(index) {
        const next = this._fallbackModels();
        next.splice(index, 1);
        this._updateFallbackModels(next);
    }

    _moveFallbackModel(from, to) {
        const next = this._fallbackModels();
        if (from < 0 || from >= next.length || to < 0 || to >= next.length) {
            return;
        }
        const [item] = next.splice(from, 1);
        next.splice(to, 0, item);
        this._updateFallbackModels(next);
    }

    _onFallbackProviderChange(index, e) {
        if (!e.detail || typeof e.detail.value !== 'string') {
            throw new Error('platform-llm-config-editor: fallback provider change expects detail.value string');
        }
        const provider = e.detail.value;
        const next = this._fallbackModels();
        if (!next[index]) {
            return;
        }
        next[index] = {
            provider,
            model: this._fallbackDefaultModel(provider),
        };
        this._updateFallbackModels(next);
    }

    _onFallbackModelChange(index, e) {
        if (!e.detail || typeof e.detail.value !== 'string') {
            throw new Error('platform-llm-config-editor: fallback model change expects detail.value string');
        }
        const next = this._fallbackModels();
        if (!next[index]) {
            return;
        }
        next[index] = {
            ...next[index],
            model: e.detail.value,
        };
        this._updateFallbackModels(next);
    }

    _providerHint(provider) {
        if (this._isHumanitecLlmProvider(provider)) {
            return this.t('settings_page.ai_providers.humanitec_llms_provider_tooltip');
        }
        return '';
    }

    _modelHint(provider, model) {
        if (this._isHumanitecLlmProvider(provider) && (!model || model === 'auto')) {
            return this.t('settings_page.ai_providers.humanitec_llms_auto_tooltip');
        }
        if (!this._isHumanitecLlmProvider(provider) && !this._isCustomProvider(provider)) {
            return this.t('settings_page.ai_providers.model_required_help');
        }
        return this.t('settings_page.ai_providers.model_override_help');
    }

    _selectedEmbeddingModelOption(model) {
        if (!this._isEmbeddingCapability() || !model) {
            return null;
        }
        return this._selectedProviderModels()
            .find((item) => item && typeof item === 'object' && item.value === model) || null;
    }

    render() {
        const provider = (this.config && this.config.provider) || '';
        const isCustom = this._isCustomProvider(provider);
        const isHumanitecLlm = this._isHumanitecLlmProvider(provider);
        const showByok = !isCustom && !isHumanitecLlm && this.mode === 'company_capability';
        const showModelOverride = this._supportsModelOverride();
        const showFallbackPolicy = this._supportsFallbackPolicy();
        const rawModelValue = (this.config && this.config.model) || '';
        const modelValue = isHumanitecLlm && !rawModelValue ? 'auto' : rawModelValue;
        const providerModels = this._selectedProviderModels();
        const modelFieldType = providerModels.length > 0 ? 'enum' : 'string';
        const fallbackModels = this._fallbackModels();
        const fallbackProviderOptions = this._fallbackProviderEnumConfig().values;
        const embeddingModelOption = this._selectedEmbeddingModelOption(modelValue);
        const embeddingDimension = this.config && Number.isFinite(this.config.dimension)
            ? this.config.dimension
            : (embeddingModelOption && Number.isFinite(embeddingModelOption.dimension)
                ? embeddingModelOption.dimension
                : null);
        const embeddingMrlDimension = this.config && Number.isFinite(this.config.mrl_output_dimension)
            ? this.config.mrl_output_dimension
            : (embeddingModelOption && Number.isFinite(embeddingModelOption.mrl_output_dimension)
                ? embeddingModelOption.mrl_output_dimension
                : null);
        const costOriginBadge = this.costOrigin
            ? html`<span class="badge" data-kind=${this.costOrigin}>${
                  this.costOrigin === 'company'
                      ? this.t('settings_page.ai_providers.cost_origin_company')
                      : this.t('settings_page.ai_providers.cost_origin_platform')
              }</span>`
            : null;

        return html`
            <div class="row">
                <div class="header">
                    <div>${costOriginBadge}</div>
                    <div class="actions">
                        ${this.clearable
                            ? html`<glass-button
                                  variant="ghost"
                                  size="sm"
                                  ?disabled=${this.readOnly}
                                  @click=${this._onClear}
                              >${this.t('settings_page.ai_providers.clear_override')}</glass-button>`
                            : ''}
                    </div>
                </div>
                <platform-field
                    type="enum"
                    mode="edit"
                    label=${this.t('settings_page.ai_providers.provider_label')}
                    .hint=${this._providerHint(provider)}
                    ?disabled=${this.readOnly}
                    .value=${provider}
                    .config=${this._providerEnumConfig()}
                    @change=${this._onProviderChange}
                ></platform-field>
                ${this.platformModel
                    ? html`
                          <platform-field
                              type="string"
                              mode="view"
                              label=${this.t('settings_page.ai_providers.platform_model_label')}
                              .value=${this.platformModel}
                          ></platform-field>
                          <small class="help">${this.t('settings_page.ai_providers.platform_model_help')}</small>
                      `
                    : ''}
                ${showModelOverride
                    ? html`
                          <platform-field
                              type=${modelFieldType}
                              mode="edit"
                              label=${this.t('settings_page.ai_providers.model_override_label')}
                              .hint=${this._modelHint(provider, modelValue)}
                              .value=${modelValue}
                              .config=${this._modelEnumConfig()}
                              ?disabled=${this.readOnly}
                              @change=${this._onModelChange}
                          ></platform-field>
                          ${modelFieldType === 'string'
                              ? html`<small class="help">${this._modelHint(provider, modelValue)}</small>`
                              : ''}
                      `
                    : ''}
                ${this._isEmbeddingCapability()
                    ? html`
                          <platform-field
                              type="number"
                              mode=${modelFieldType === 'enum' ? 'view' : 'edit'}
                              label=${this.t('settings_page.ai_providers.embedding_dimension_label')}
                              .value=${embeddingDimension}
                              ?disabled=${this.readOnly || modelFieldType === 'enum'}
                              @change=${this._onDimensionChange}
                          ></platform-field>
                          <platform-field
                              type="number"
                              mode=${modelFieldType === 'enum' ? 'view' : 'edit'}
                              label=${this.t('settings_page.ai_providers.embedding_mrl_dimension_label')}
                              .value=${embeddingMrlDimension}
                              ?disabled=${this.readOnly || modelFieldType === 'enum'}
                              @change=${this._onMrlOutputDimensionChange}
                          ></platform-field>
                          <small class="help">${this.t('settings_page.ai_providers.embedding_dimension_help')}</small>
                      `
                    : ''}
                ${showByok
                    ? html`
                          <platform-field
                              type="password"
                              mode="edit"
                              label=${this.t('settings_page.ai_providers.api_key_label')}
                              .value=${(this.config && this.config.api_key) || ''}
                              .placeholder=${this.keyMasked || ''}
                              ?disabled=${this.readOnly}
                              @change=${this._onApiKeyChange}
                          ></platform-field>
                          <small class="help">${this.t('settings_page.ai_providers.api_key_help')}</small>
                          <platform-field
                              type="string"
                              mode="edit"
                              label=${this.t('settings_page.ai_providers.base_url_label')}
                              .value=${(this.config && this.config.base_url) || ''}
                              ?disabled=${this.readOnly}
                              @change=${this._onBaseUrlChange}
                          ></platform-field>
                      `
                    : ''}
                ${!showModelOverride && !this.platformModel
                    ? html`
                          <platform-field
                              type="string"
                              mode="edit"
                              label=${this.t('settings_page.ai_providers.model_optional_label')}
                              .value=${(this.config && this.config.model) || ''}
                              ?disabled=${this.readOnly}
                              @change=${this._onModelChange}
                          ></platform-field>
                      `
                    : ''}
                ${showFallbackPolicy
                    ? html`
                          <div class="fallback-policy">
                              <div class="fallback-head">
                                  <div class="fallback-title">
                                      ${this.t('settings_page.ai_providers.fallback_models_label')}
                                  </div>
                                  <glass-button
                                      variant="ghost"
                                      size="sm"
                                      ?disabled=${this.readOnly || fallbackProviderOptions.length === 0}
                                      @click=${this._addFallbackModel}
                                  >
                                      <platform-icon name="plus" size="14"></platform-icon>
                                      ${this.t('settings_page.ai_providers.fallback_add')}
                                  </glass-button>
                              </div>
                              ${fallbackModels.length === 0
                                  ? html`
                                        <div class="fallback-empty">
                                            ${this.t('settings_page.ai_providers.fallback_empty')}
                                        </div>
                                    `
                                  : html`
                                        <div class="fallback-list">
                                            ${fallbackModels.map((item, index) => {
                                                const modelOptions = this._fallbackModelEnumConfig(item.provider).values;
                                                const fallbackModelFieldType = modelOptions.length > 0 ? 'enum' : 'string';
                                                return html`
                                                    <div class="fallback-item">
                                                        <div class="fallback-grid">
                                                            <platform-field
                                                                type="enum"
                                                                mode="edit"
                                                                label=${this.t('settings_page.ai_providers.fallback_provider_label')}
                                                                .value=${item.provider}
                                                                .config=${this._fallbackProviderEnumConfig()}
                                                                ?disabled=${this.readOnly}
                                                                @change=${(e) => this._onFallbackProviderChange(index, e)}
                                                            ></platform-field>
                                                            <platform-field
                                                                type=${fallbackModelFieldType}
                                                                mode="edit"
                                                                label=${this.t('settings_page.ai_providers.fallback_model_label')}
                                                                .value=${item.model}
                                                                .config=${this._fallbackModelEnumConfig(item.provider)}
                                                                ?disabled=${this.readOnly}
                                                                @change=${(e) => this._onFallbackModelChange(index, e)}
                                                            ></platform-field>
                                                        </div>
                                                        <div class="fallback-actions">
                                                            <glass-button
                                                                variant="ghost"
                                                                size="sm"
                                                                title=${this.t('settings_page.ai_providers.fallback_move_up')}
                                                                ?disabled=${this.readOnly || index === 0}
                                                                @click=${() => this._moveFallbackModel(index, index - 1)}
                                                            >
                                                                <platform-icon name="chevron-up" size="14"></platform-icon>
                                                            </glass-button>
                                                            <glass-button
                                                                variant="ghost"
                                                                size="sm"
                                                                title=${this.t('settings_page.ai_providers.fallback_move_down')}
                                                                ?disabled=${this.readOnly || index === fallbackModels.length - 1}
                                                                @click=${() => this._moveFallbackModel(index, index + 1)}
                                                            >
                                                                <platform-icon name="chevron-down" size="14"></platform-icon>
                                                            </glass-button>
                                                            <glass-button
                                                                variant="ghost"
                                                                size="sm"
                                                                title=${this.t('settings_page.ai_providers.fallback_remove')}
                                                                ?disabled=${this.readOnly}
                                                                @click=${() => this._removeFallbackModel(index)}
                                                            >
                                                                <platform-icon name="trash" size="14"></platform-icon>
                                                            </glass-button>
                                                        </div>
                                                    </div>
                                                `;
                                            })}
                                        </div>
                                    `}
                          </div>
                          <small class="help">${this.t('settings_page.ai_providers.fallback_models_help')}</small>
                      `
                    : ''}
            </div>
        `;
    }
}

if (!customElements.get('platform-llm-config-editor')) {
    customElements.define('platform-llm-config-editor', PlatformLlmConfigEditor);
}
