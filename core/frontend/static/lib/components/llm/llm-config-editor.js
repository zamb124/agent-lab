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

    _supportsModelOverride() {
        return (
            typeof this.capability === 'string'
            && (
                this.capability.startsWith('llm_')
                || this.capability === 'image_gen'
                || this.capability === 'voice_stt'
                || this.capability === 'voice_tts'
            )
        );
    }

    _supportsFallbackPolicy() {
        const provider = (this.config && this.config.provider) || '';
        return (
            this.mode === 'company_capability'
            && (this.capability || '').startsWith('llm_')
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
        this._emitChange({ model: e.detail.value || null });
    }

    _onFallbackModelsChange(e) {
        if (!e.detail) {
            return;
        }
        const value = e.detail.value;
        if (value == null) {
            this._emitChange({ fallback_models: null });
            return;
        }
        if (!Array.isArray(value)) {
            throw new Error('platform-llm-config-editor: fallback_models expects JSON array');
        }
        this._emitChange({ fallback_models: value.length > 0 ? value : null });
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
        const selected = this._selectedProviderCatalogItem();
        return Array.isArray(selected?.models) ? selected.models : [];
    }

    _modelEnumConfig() {
        const values = this._selectedProviderModels()
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
        return { values };
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
        return this.t('settings_page.ai_providers.model_override_help');
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
                              ? html`<small class="help">${this.t('settings_page.ai_providers.model_override_help')}</small>`
                              : ''}
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
                          <platform-field
                              type="object"
                              mode="edit"
                              label=${this.t('settings_page.ai_providers.fallback_models_label')}
                              .value=${(this.config && this.config.fallback_models) || null}
                              ?disabled=${this.readOnly}
                              @change=${this._onFallbackModelsChange}
                          ></platform-field>
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
