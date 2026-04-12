/**
 * LLMConfigEditor — компактный остров (как loop-config): модель, sampling, провайдер,
 * раскрываемый Advanced и JSON extra_request_body (мержится поверх на бэкенде).
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './json-field-editor.js';

const REASONING_UNSET = '';

export class LLMConfigEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .llm-island {
                margin-top: var(--space-2);
                padding: var(--space-3);
                background: var(--glass-tint-subtle);
                border-radius: var(--radius-md);
            }

            .row-2 {
                display: flex;
                flex-direction: row;
                align-items: flex-end;
                gap: var(--space-3);
                margin-bottom: var(--space-2);
            }

            .row-2:last-of-type {
                margin-bottom: 0;
            }

            .grow {
                flex: 1;
                min-width: 0;
            }

            .col-temp {
                flex: 0 0 9.5rem;
                min-width: 0;
            }

            .col-maxtok {
                flex: 0 0 6.5rem;
                min-width: 0;
            }

            @media (max-width: 520px) {
                .row-2 {
                    flex-direction: column;
                    align-items: stretch;
                }

                .col-temp,
                .col-maxtok {
                    flex: 1 1 auto;
                }
            }

            .config-label {
                display: block;
                margin-bottom: var(--space-1);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }

            .config-select,
            .config-input {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                outline: none;
                transition: border-color var(--duration-fast) var(--easing-default);
            }

            .config-select:focus,
            .config-input:focus {
                border-color: var(--accent);
            }

            .config-select {
                appearance: none;
                cursor: pointer;
                padding-right: var(--space-6);
                background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%23999' viewBox='0 0 16 16'%3E%3Cpath d='M4 6l4 4 4-4'/%3E%3C/svg%3E");
                background-repeat: no-repeat;
                background-position: right 8px center;
            }

            .config-input[type='number'] {
                -moz-appearance: textfield;
            }

            .config-input[type='number']::-webkit-outer-spin-button,
            .config-input[type='number']::-webkit-inner-spin-button {
                -webkit-appearance: none;
                margin: 0;
            }

            .temp-slider {
                width: 100%;
                height: 4px;
                background: var(--border-subtle);
                border-radius: 2px;
                appearance: none;
                cursor: pointer;
            }

            .temp-slider::-webkit-slider-thumb {
                appearance: none;
                width: 14px;
                height: 14px;
                background: var(--accent);
                border-radius: 50%;
                cursor: pointer;
            }

            .loading {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .credentials-section {
                margin-top: var(--space-2);
                padding: var(--space-2);
                background: var(--glass-tint-medium);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
            }

            .credentials-title {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }

            .config-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }

            .advanced-toggle {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-top: var(--space-2);
                padding: var(--space-1) 0;
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--accent);
                background: none;
                border: none;
                cursor: pointer;
                font-family: inherit;
            }

            .advanced-toggle:hover {
                color: var(--text-primary);
            }

            .chevron {
                display: inline-block;
                transition: transform var(--duration-fast) ease;
            }

            .chevron.open {
                transform: rotate(90deg);
            }

            .advanced-panel {
                margin-top: var(--space-2);
                padding-top: var(--space-2);
                border-top: 1px solid var(--border-subtle);
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }

            .advanced-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: var(--space-2);
            }

            @media (max-width: 480px) {
                .advanced-grid {
                    grid-template-columns: 1fr;
                }
            }

            .json-block {
                margin-top: var(--space-2);
            }

            .json-block json-field-editor {
                display: block;
            }
        `,
    ];

    static properties = {
        model: { type: String },
        temperature: { type: Number },
        maxTokens: { type: Number, attribute: 'max-tokens' },
        provider: { type: String },
        apiKey: { type: String, attribute: 'api-key' },
        baseUrl: { type: String, attribute: 'base-url' },
        models: { type: Array },
        loading: { type: Boolean },
        advancedOpen: { type: Boolean },
        topP: { type: Number },
        topK: { type: Number },
        frequencyPenalty: { type: Number },
        presencePenalty: { type: Number },
        seed: { type: String },
        reasoningEffort: { type: String },
        extraBodyJson: { type: String },
    };

    constructor() {
        super();
        this.model = 'gpt-4o';
        this.temperature = 0.2;
        this.maxTokens = null;
        this.provider = '';
        this.apiKey = '';
        this.baseUrl = '';
        this.models = [];
        this.loading = true;
        this.advancedOpen = false;
        this.topP = null;
        this.topK = null;
        this.frequencyPenalty = null;
        this.presencePenalty = null;
        this.seed = '';
        this.reasoningEffort = REASONING_UNSET;
        this.extraBodyJson = '{}';
        this._extraJsonValid = true;
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadModels();
    }

    async _loadModels(provider = null) {
        this.loading = true;

        if (this.a2a) {
            const models = await this.a2a.getAvailableModels(provider || this.provider || null);
            if (Array.isArray(models) && models.length > 0) {
                this.models = models.map((m) => ({ id: m, name: m }));
            } else {
                this.models = [];
            }
        } else {
            this.models = [];
        }

        this.loading = false;
    }

    _parseExtraBodyObject() {
        const editor = this.shadowRoot?.querySelector('#llm-extra-json');
        const text = (editor ? editor.getValue() : this.extraBodyJson || '').trim() || '{}';
        let parsed;
        try {
            parsed = JSON.parse(text);
        } catch (e) {
            return { ok: false, error: e.message };
        }
        if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
            return { ok: false, error: this.i18n.t('llm_config_editor.err_extra_not_object') };
        }
        return { ok: true, value: parsed, text };
    }

    getValue() {
        const extra = this._parseExtraBodyObject();
        if (!extra.ok) {
            throw new Error(extra.error || this.i18n.t('llm_config_editor.err_extra_json'));
        }
        if (this.model && this.models.length > 0) {
            const modelExists = this.models.some((item) => item.id === this.model);
            if (!modelExists) {
                throw new Error(this.i18n.t('llm_config_editor.err_model_not_available'));
            }
        }

        const config = {
            model: this.model,
            temperature: this.temperature,
        };
        if (this.maxTokens != null && this.maxTokens > 0) {
            config.max_tokens = this.maxTokens;
        }
        if (this.provider) {
            config.provider = this.provider;
        }
        if (this.apiKey && this.provider !== 'provider_litserve') {
            config.api_key = this.apiKey;
        }
        if (this.baseUrl && this.provider !== 'provider_litserve') {
            config.base_url = this.baseUrl;
        }
        if (this.topP != null && !Number.isNaN(this.topP)) {
            config.top_p = this.topP;
        }
        if (this.topK != null && this.topK > 0) {
            config.top_k = this.topK;
        }
        if (this.frequencyPenalty != null && !Number.isNaN(this.frequencyPenalty)) {
            config.frequency_penalty = this.frequencyPenalty;
        }
        if (this.presencePenalty != null && !Number.isNaN(this.presencePenalty)) {
            config.presence_penalty = this.presencePenalty;
        }
        const seedNum = this.seed === '' || this.seed === undefined ? null : parseInt(String(this.seed), 10);
        if (seedNum != null && !Number.isNaN(seedNum)) {
            config.seed = seedNum;
        }
        if (this.reasoningEffort && this.reasoningEffort !== REASONING_UNSET) {
            config.reasoning_effort = this.reasoningEffort;
        }
        if (extra.value && Object.keys(extra.value).length > 0) {
            config.extra_request_body = extra.value;
        }
        return config;
    }

    setValue(config) {
        if (!config || typeof config !== 'object') {
            return;
        }
        this.model = config.model || 'gpt-4o';
        this.temperature =
            config.temperature !== undefined && config.temperature !== null
                ? Number(config.temperature)
                : 0.2;
        this.maxTokens = config.max_tokens != null && config.max_tokens !== '' ? config.max_tokens : null;
        if (config.provider !== undefined) this.provider = config.provider || '';
        if (config.api_key !== undefined) this.apiKey = config.api_key || '';
        if (config.base_url !== undefined) this.baseUrl = config.base_url || '';
        this.topP = config.top_p != null ? config.top_p : null;
        this.topK = config.top_k != null ? config.top_k : null;
        this.frequencyPenalty = config.frequency_penalty != null ? config.frequency_penalty : null;
        this.presencePenalty = config.presence_penalty != null ? config.presence_penalty : null;
        this.seed = config.seed != null && config.seed !== '' ? String(config.seed) : '';
        this.reasoningEffort = config.reasoning_effort || REASONING_UNSET;
        const erb = config.extra_request_body;
        if (erb && typeof erb === 'object' && !Array.isArray(erb)) {
            this.extraBodyJson = JSON.stringify(erb, null, 2);
        } else {
            this.extraBodyJson = '{}';
        }
        this._extraJsonValid = true;
        this.requestUpdate();
        queueMicrotask(() => {
            const ed = this.shadowRoot?.querySelector('#llm-extra-json');
            if (ed) {
                ed.setValue(this.extraBodyJson);
            }
        });
    }

    _emitChangeSafe() {
        if (!this._extraJsonValid) {
            return;
        }
        try {
            this.getValue();
        } catch (err) {
            this.error(String(err.message || err));
            return;
        }
        this.emit('change', { value: this.getValue() });
    }

    _onModelChange(e) {
        this.model = e.target.value;
        this._emitChangeSafe();
    }

    _onTemperatureChange(e) {
        this.temperature = parseFloat(e.target.value);
        this._emitChangeSafe();
    }

    _onMaxTokensChange(e) {
        const value = e.target.value.trim();
        this.maxTokens = value ? parseInt(value, 10) : null;
        this._emitChangeSafe();
    }

    _onProviderChange(e) {
        this.provider = e.target.value;
        if (this.provider === 'provider_litserve') {
            this.apiKey = '';
            this.baseUrl = '';
        }
        this._loadModels(this.provider || null);
        this._emitChangeSafe();
    }

    _onApiKeyChange(e) {
        this.apiKey = e.target.value;
        this._emitChangeSafe();
    }

    _onBaseUrlChange(e) {
        this.baseUrl = e.target.value;
        this._emitChangeSafe();
    }

    _onTopPChange(e) {
        const v = e.target.value.trim();
        this.topP = v === '' ? null : parseFloat(v);
        this._emitChangeSafe();
    }

    _onTopKChange(e) {
        const v = e.target.value.trim();
        this.topK = v === '' ? null : parseInt(v, 10);
        this._emitChangeSafe();
    }

    _onFreqPenChange(e) {
        const v = e.target.value.trim();
        this.frequencyPenalty = v === '' ? null : parseFloat(v);
        this._emitChangeSafe();
    }

    _onPresPenChange(e) {
        const v = e.target.value.trim();
        this.presencePenalty = v === '' ? null : parseFloat(v);
        this._emitChangeSafe();
    }

    _onSeedChange(e) {
        this.seed = e.target.value.trim();
        this._emitChangeSafe();
    }

    _onReasoningChange(e) {
        this.reasoningEffort = e.target.value;
        this._emitChangeSafe();
    }

    _onExtraJsonChange(e) {
        const { valid } = e.detail;
        if (!valid) {
            this._extraJsonValid = false;
            this.error(this.i18n.t('llm_config_editor.err_extra_json'));
            return;
        }
        const text = e.detail.value.trim() || '{}';
        let parsed;
        try {
            parsed = JSON.parse(text);
        } catch (err) {
            this._extraJsonValid = false;
            this.error(this.i18n.t('llm_config_editor.err_extra_json'));
            return;
        }
        if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
            this._extraJsonValid = false;
            this.error(this.i18n.t('llm_config_editor.err_extra_not_object'));
            return;
        }
        this._extraJsonValid = true;
        this.extraBodyJson = text;
        this.emit('change', { value: this.getValue() });
    }

    _toggleAdvanced() {
        this.advancedOpen = !this.advancedOpen;
    }

    _buildModelOptions() {
        const options = [...this.models];
        if (!this.model) {
            return options;
        }
        const exists = options.some((item) => item.id === this.model);
        if (!exists) {
            options.unshift({
                id: this.model,
                name: `${this.model} ${this.i18n.t('llm_config_editor.model_missing_suffix')}`,
            });
        }
        return options;
    }

    render() {
        const showCredentials = this.provider !== '' && this.provider !== 'provider_litserve';
        const modelOptions = this._buildModelOptions();

        return html`
            <div class="llm-island">
                <div class="row-2">
                    <div class="grow">
                        <label class="config-label">${this.i18n.t('llm_config_editor.label_model')}</label>
                        ${this.loading
                            ? html`<span class="loading">${this.i18n.t('llm_config_editor.loading')}</span>`
                            : html`
                                  <select class="config-select" .value=${this.model} @change=${this._onModelChange}>
                                      ${modelOptions.map(
                                          (m) => html`
                                              <option value=${m.id} ?selected=${m.id === this.model}>${m.name}</option>
                                          `,
                                      )}
                                  </select>
                              `}
                    </div>
                    <div class="col-temp">
                        <label class="config-label"
                            >${this.i18n.t('llm_config_editor.label_temperature')}
                            ${this.temperature.toFixed(1)}</label
                        >
                        <input
                            type="range"
                            class="temp-slider"
                            min="0"
                            max="2"
                            step="0.1"
                            .value=${String(this.temperature)}
                            @input=${this._onTemperatureChange}
                        />
                    </div>
                </div>

                <div class="row-2">
                    <div class="col-maxtok">
                        <label class="config-label">${this.i18n.t('llm_config_editor.label_max_tokens')}</label>
                        <input
                            type="number"
                            class="config-input"
                            placeholder=${this.i18n.t('llm_config_editor.placeholder_auto')}
                            .value=${this.maxTokens != null ? String(this.maxTokens) : ''}
                            @input=${this._onMaxTokensChange}
                        />
                    </div>
                    <div class="grow">
                        <label class="config-label">${this.i18n.t('llm_config_editor.label_provider')}</label>
                        <select class="config-select" .value=${this.provider} @change=${this._onProviderChange}>
                            <option value="">${this.i18n.t('llm_config_editor.option_system_default')}</option>
                            <option value="openai" ?selected=${this.provider === 'openai'}>${this.i18n.t('llm_config_editor.provider_openai')}</option>
                            <option value="openrouter" ?selected=${this.provider === 'openrouter'}>${this.i18n.t('llm_config_editor.provider_openrouter')}</option>
                            <option value="bothub" ?selected=${this.provider === 'bothub'}>${this.i18n.t('llm_config_editor.provider_bothub')}</option>
                            <option value="provider_litserve" ?selected=${this.provider === 'provider_litserve'}>${this.i18n.t('llm_config_editor.provider_humanitec')}</option>
                        </select>
                    </div>
                </div>
                <div class="config-hint">${this.i18n.t('llm_config_editor.hint_provider')}</div>

                <button type="button" class="advanced-toggle" @click=${this._toggleAdvanced}>
                    <span class="chevron ${this.advancedOpen ? 'open' : ''}">&#9654;</span>
                    ${this.i18n.t('llm_config_editor.advanced_toggle')}
                </button>

                ${this.advancedOpen
                    ? html`
                          <div class="advanced-panel">
                              <div class="config-hint">${this.i18n.t('llm_config_editor.advanced_hint')}</div>
                              <div class="advanced-grid">
                                  <div>
                                      <label class="config-label">top_p</label>
                                      <input
                                          type="number"
                                          class="config-input"
                                          min="0"
                                          max="1"
                                          step="0.01"
                                          placeholder=${this.i18n.t('llm_config_editor.placeholder_top_p_default')}
                                          .value=${this.topP != null ? String(this.topP) : ''}
                                          @input=${this._onTopPChange}
                                      />
                                  </div>
                                  <div>
                                      <label class="config-label">top_k</label>
                                      <input
                                          type="number"
                                          class="config-input"
                                          min="1"
                                          step="1"
                                          placeholder=${this.i18n.t('llm_config_editor.placeholder_top_k_example')}
                                          .value=${this.topK != null ? String(this.topK) : ''}
                                          @input=${this._onTopKChange}
                                      />
                                  </div>
                                  <div>
                                      <label class="config-label">${this.i18n.t('llm_config_editor.label_freq_penalty')}</label>
                                      <input
                                          type="number"
                                          class="config-input"
                                          min="-2"
                                          max="2"
                                          step="0.1"
                                          placeholder=${this.i18n.t('llm_config_editor.placeholder_penalty_default')}
                                          .value=${this.frequencyPenalty != null ? String(this.frequencyPenalty) : ''}
                                          @input=${this._onFreqPenChange}
                                      />
                                  </div>
                                  <div>
                                      <label class="config-label">${this.i18n.t('llm_config_editor.label_pres_penalty')}</label>
                                      <input
                                          type="number"
                                          class="config-input"
                                          min="-2"
                                          max="2"
                                          step="0.1"
                                          placeholder=${this.i18n.t('llm_config_editor.placeholder_penalty_default')}
                                          .value=${this.presencePenalty != null ? String(this.presencePenalty) : ''}
                                          @input=${this._onPresPenChange}
                                      />
                                  </div>
                                  <div>
                                      <label class="config-label">${this.i18n.t('llm_config_editor.label_seed')}</label>
                                      <input
                                          type="number"
                                          class="config-input"
                                          step="1"
                                          placeholder=${this.i18n.t('llm_config_editor.placeholder_seed_example')}
                                          .value=${this.seed}
                                          @input=${this._onSeedChange}
                                      />
                                  </div>
                                  <div>
                                      <label class="config-label">${this.i18n.t('llm_config_editor.label_reasoning')}</label>
                                      <select
                                          class="config-select"
                                          .value=${this.reasoningEffort}
                                          @change=${this._onReasoningChange}
                                      >
                                          <option value="">${this.i18n.t('llm_config_editor.reasoning_unset')}</option>
                                          <option value="none">none</option>
                                          <option value="minimal">minimal</option>
                                          <option value="low">low</option>
                                          <option value="medium">medium</option>
                                          <option value="high">high</option>
                                          <option value="xhigh">xhigh</option>
                                      </select>
                                  </div>
                              </div>
                              <div class="json-block">
                                  <label class="config-label">${this.i18n.t('llm_config_editor.label_extra_json')}</label>
                                  <div class="config-hint">${this.i18n.t('llm_config_editor.hint_extra_json')}</div>
                                  <json-field-editor
                                      id="llm-extra-json"
                                      bounded
                                      .value=${this.extraBodyJson}
                                      min-height="220"
                                      @change=${this._onExtraJsonChange}
                                  ></json-field-editor>
                              </div>
                          </div>
                      `
                    : ''}

                ${showCredentials
                    ? html`
                          <div class="credentials-section">
                              <div class="credentials-title">
                                  ${this.i18n.t('llm_config_editor.credentials_for', { provider: this.provider })}
                              </div>
                              <div>
                                  <label class="config-label">${this.i18n.t('llm_config_editor.label_api_key')}</label>
                                  <input
                                      type="text"
                                      class="config-input"
                                      placeholder=${this.i18n.t('llm_config_editor.placeholder_api_key')}
                                      .value=${this.apiKey}
                                      @input=${this._onApiKeyChange}
                                  />
                                  <div class="config-hint">${this.i18n.t('llm_config_editor.hint_api_key')}</div>
                              </div>
                              <div style="margin-top: var(--space-2);">
                                  <label class="config-label">${this.i18n.t('llm_config_editor.label_base_url')}</label>
                                  <input
                                      type="text"
                                      class="config-input"
                                      placeholder=${this.i18n.t('llm_config_editor.placeholder_base_url')}
                                      .value=${this.baseUrl}
                                      @input=${this._onBaseUrlChange}
                                  />
                              </div>
                          </div>
                      `
                    : ''}
            </div>
        `;
    }
}

customElements.define('llm-config-editor', LLMConfigEditor);
